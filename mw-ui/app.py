#!/usr/bin/env python3
"""MW Books UI v1 - review queue, entity/category assignment, transfers, IOUs.

Runs locally next to the ledger (double-click RUN-MW-BOOKS.bat).
The Beancount files stay the single source of truth: every action rewrites
the entry in place (flag ! -> *, tag removed, reviewed_by recorded) and
git-commits when git is available. Fava remains the statements layer.

Money is read-only: this app never touches a bank, it only edits the ledger.
"""
import datetime, json, os, re, sqlite3, subprocess, sys
from decimal import Decimal

from flask import Flask, jsonify, redirect, render_template_string, request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "main.beancount")
TXNDIR = os.path.join(ROOT, "entities", "txns")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "activity.db")
ENTITIES = ["Personal", "MWFin", "MWRealty", "Suncorps", "MWDev", "KML", "PropMgmt"]
USERS = {"webster": "Webster", "marisel": "Mary"}

app = Flask(__name__)
_cache = {"key": None, "entries": None, "opens": None}


def log_action(user, action, sid, detail):
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS activity (ts TEXT, user TEXT, "
                "action TEXT, sid TEXT, detail TEXT)")
    con.execute("INSERT INTO activity VALUES (?,?,?,?,?)",
                (datetime.datetime.now().isoformat(timespec="seconds"),
                 user, action, sid, detail))
    con.commit(); con.close()


def git_commit(msg):
    try:
        subprocess.run(["git", "add", "-A"], cwd=ROOT, capture_output=True, timeout=20)
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT,
                       capture_output=True, timeout=20)
    except Exception:
        pass  # git optional on this machine; session commits happen later


def load_ledger():
    """Load entries + open directives, cached on ledger file mtimes."""
    key = tuple(sorted((p, os.path.getmtime(os.path.join(dp, p)))
                for dp, _, fns in os.walk(os.path.join(ROOT, "entities"))
                for p in fns))
    if _cache["key"] == key:
        return _cache["entries"], _cache["opens"]
    from beancount import loader
    from beancount.core import data
    entries, errors, _ = loader.load_file(MAIN)
    opens = [e for e in entries if isinstance(e, data.Open)]
    _cache.update(key=key, entries=entries, opens=opens)
    return entries, opens


def categories_by_entity():
    _, opens = load_ledger()
    cats = {e: {"Expenses": [], "Income": []} for e in ENTITIES}
    for o in opens:
        parts = o.account.split(":")
        if parts[0] in ("Expenses", "Income") and len(parts) > 2 and parts[1] in cats:
            if ":Uncategorized" in o.account:
                continue
            cats[parts[1]][parts[0]].append(o.account)
    for e in cats:
        cats[e]["Expenses"].sort(); cats[e]["Income"].sort()
    return cats


def queue_rows():
    from beancount.core import data
    entries, _ = load_ledger()
    rows = []
    for e in entries:
        if not isinstance(e, data.Transaction) or "unreviewed" not in (e.tags or ()):
            continue
        bank = next((p for p in e.postings
                     if not re.match(r"(Expenses|Income):.*:Uncategorized", p.account)), None)
        if bank is None:
            continue
        rows.append(dict(
            sid=e.meta.get("simplefin_id", ""),
            date=str(e.date), payee=e.payee or "", narration=e.narration or "",
            account=bank.account, acct_short=bank.account.split(":")[-1],
            entity=bank.account.split(":")[1],
            amount=float(bank.units.number), mcc=e.meta.get("mcc", ""),
            ambig="transfer-candidate" in (e.tags or ())))
    rows.sort(key=lambda r: (r["date"], r["sid"]), reverse=True)
    return rows


def transfer_rows():
    from beancount.core import data
    entries, _ = load_ledger()
    rows = []
    for e in entries:
        if not isinstance(e, data.Transaction) or "auto-matched" not in (e.tags or ()):
            continue
        legs = [(p.account, float(p.units.number)) for p in e.postings]
        rows.append(dict(sid=e.meta.get("simplefin_out", ""), date=str(e.date),
                         narration=e.narration, desc=e.meta.get("narration2", ""),
                         legs=legs,
                         amount=max(abs(l[1]) for l in legs),
                         cross=any(":DueFrom:" in a or ":DueTo:" in a for a, _ in legs)))
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def iou_table():
    from beancount.core import data
    entries, _ = load_ledger()
    net = {}
    for e in entries:
        if isinstance(e, data.Transaction):
            for p in e.postings:
                m = re.match(r"Assets:(\w+):DueFrom:(\w+)", p.account)
                if m:
                    k = (m.group(1), m.group(2))
                    net[k] = net.get(k, Decimal(0)) + p.units.number
    rows = []
    done = set()
    for (a, b), amt in net.items():
        if (b, a) in done or (a, b) in done:
            continue
        done.add((a, b))
        back = net.get((b, a), Decimal(0))
        n = amt - back
        if n > 0:
            rows.append(dict(creditor=a, debtor=b, amount=float(n)))
        elif n < 0:
            rows.append(dict(creditor=b, debtor=a, amount=float(-n)))
    rows.sort(key=lambda r: -r["amount"])
    return rows


# ---------------------------------------------------------------- rewriting --
def find_block(sid_key, sid):
    """Locate the file + text block of the entry whose meta contains sid."""
    needle = f'{sid_key}: "{sid}"'
    for fn in os.listdir(TXNDIR):
        if not fn.endswith(".beancount"):
            continue
        p = os.path.join(TXNDIR, fn)
        txt = open(p, encoding="utf-8").read()
        if needle not in txt:
            continue
        blocks = txt.split("\n\n")
        for i, b in enumerate(blocks):
            if needle in b:
                return p, txt, blocks, i
    return None, None, None, None


def ensure_intercompany(ent_a, ent_b):
    """Open DueFrom/DueTo pair if missing. Returns (dfrom, dto)."""
    dfrom = f"Assets:{ent_a}:DueFrom:{ent_b}"
    dto = f"Liabilities:{ent_b}:DueTo:{ent_a}"
    p = os.path.join(TXNDIR, "intercompany.beancount")
    txt = open(p, encoding="utf-8").read() if os.path.exists(p) else \
        ";; Intercompany IOU accounts - GENERATED, append-only\n"
    add = [f"2025-01-01 open {a}  USD" for a in (dfrom, dto)
           if f"open {a} " not in txt and f"open {a}\n" not in txt]
    if add:
        open(p, "a", encoding="utf-8").write("\n".join(add) + "\n")
    return dfrom, dto


@app.post("/api/assign")
def assign():
    d = request.json
    user = d.get("user")
    if user not in USERS:
        return jsonify(error="pick a user first"), 400
    sid, entity, category = d["sid"], d["entity"], d["category"]
    if entity not in ENTITIES or not category.startswith(("Expenses:", "Income:")):
        return jsonify(error="bad entity/category"), 400
    p, txt, blocks, i = find_block("simplefin_id", sid)
    if p is None:
        return jsonify(error="entry not found"), 404
    b = blocks[i]
    m = re.search(r'^(\d{4}-\d{2}-\d{2}) ! "((?:[^"\\]|\\.)*)" "((?:[^"\\]|\\.)*)"', b)
    bank = re.search(r"^  ((?:Assets|Liabilities):[\w:-]+)  (-?[\d.]+) USD$", b, re.M)
    if not m or not bank:
        return jsonify(error="entry already reviewed or malformed"), 409
    date, payee, narr = m.groups()
    bank_acct, amt_s = bank.groups()
    amt = Decimal(amt_s)
    bank_ent = bank_acct.split(":")[1]
    now = datetime.datetime.now().isoformat(timespec="seconds")
    keep_meta = [l for l in b.splitlines()
                 if re.match(r'^  (simplefin_id|mcc):', l)]
    lines = [f'{date} * "{payee}" "{narr}"'] + keep_meta + [
        f'  reviewed_by: "{user}"', f'  reviewed_at: "{now}"',
        f'  {bank_acct}  {amt} USD']
    if entity == bank_ent:
        lines.append(f'  {category}  {-amt} USD')
    else:
        # bank entity fronted money for `entity` -> IOU legs keep both balanced
        dfrom, dto = ensure_intercompany(bank_ent, entity)
        lines += [f'  {dfrom}  {-amt} USD',
                  f'  {category}  {-amt} USD',
                  f'  {dto}  {amt} USD']
    blocks[i] = "\n".join(lines)
    open(p, "w", encoding="utf-8").write("\n\n".join(blocks))
    _cache["key"] = None
    log_action(user, "assign", sid, f"{entity} / {category}")
    git_commit(f"review: {user} filed '{payee[:40]}' -> {category}")
    return jsonify(ok=True)


@app.post("/api/confirm_transfer")
def confirm_transfer():
    d = request.json
    user, sid, verdict = d.get("user"), d["sid"], d["verdict"]
    if user not in USERS:
        return jsonify(error="pick a user first"), 400
    p, txt, blocks, i = find_block("simplefin_out", sid)
    if p is None:
        return jsonify(error="not found"), 404
    b = blocks[i]
    now = datetime.datetime.now().isoformat(timespec="seconds")
    if verdict == "ok":
        b = b.replace(" #auto-matched", "")
        b = b.replace('\n  narration2:', f'\n  confirmed_by: "{user}"\n  confirmed_at: "{now}"\n  narration2:')
    else:
        b = b.replace(" #auto-matched", " #needs-fix")
        b = b.replace('\n  narration2:', f'\n  rejected_by: "{user}"\n  rejected_at: "{now}"\n  narration2:')
    blocks[i] = b
    open(p, "w", encoding="utf-8").write("\n\n".join(blocks))
    _cache["key"] = None
    log_action(user, f"transfer_{verdict}", sid, "")
    git_commit(f"review: {user} transfer {verdict} ({sid[:12]})")
    return jsonify(ok=True)


@app.get("/api/queue")
def api_queue():
    return jsonify(rows=queue_rows(), cats=categories_by_entity())


@app.get("/api/transfers")
def api_transfers():
    return jsonify(rows=transfer_rows())


@app.get("/api/iou")
def api_iou():
    return jsonify(rows=iou_table())


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>MW Books</title>
<style>
:root { --navy:#12233d; --gold:#c9a227; --bg:#f6f7f9; --line:#e3e6ea; }
* { box-sizing:border-box; font-family:'Segoe UI',system-ui,sans-serif; }
body { margin:0; background:var(--bg); color:#1c2733; }
header { background:var(--navy); color:#fff; padding:14px 22px; display:flex; align-items:center; gap:18px; }
header h1 { font-size:19px; margin:0; letter-spacing:.4px; }
header h1 b { color:var(--gold); }
.tabs { display:flex; gap:4px; margin-left:24px; }
.tabs button { background:none; border:none; color:#cfd6df; padding:8px 14px; cursor:pointer; font-size:14px; border-radius:6px 6px 0 0; }
.tabs button.on { background:var(--bg); color:var(--navy); font-weight:600; }
.userpick { margin-left:auto; display:flex; gap:6px; align-items:center; font-size:13px; }
.userpick button { border:1px solid #51637f; background:none; color:#cfd6df; padding:6px 12px; border-radius:14px; cursor:pointer; }
.userpick button.on { background:var(--gold); border-color:var(--gold); color:var(--navy); font-weight:700; }
main { padding:18px 22px; max-width:1200px; margin:0 auto; }
.bar { display:flex; gap:10px; margin-bottom:12px; align-items:center; flex-wrap:wrap; }
.bar input,.bar select { padding:7px 10px; border:1px solid var(--line); border-radius:6px; font-size:13px; }
.count { font-size:13px; color:#5b6b7d; }
table { width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius:8px; overflow:hidden; }
th { text-align:left; font-size:12px; text-transform:uppercase; letter-spacing:.4px; color:#5b6b7d; padding:9px 10px; border-bottom:2px solid var(--line); background:#fbfcfd; }
td { padding:8px 10px; border-bottom:1px solid var(--line); font-size:13.5px; vertical-align:middle; }
tr:hover td { background:#fbf8ee; }
.amt { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.neg { color:#b3372b; } .pos { color:#1a7a3c; }
.chip { font-size:11px; padding:2px 8px; border-radius:10px; background:#e8ecf2; color:#37475c; white-space:nowrap; }
.chip.Personal { background:#e6eefc; } .chip.MWRealty { background:#e9f7ee; }
.chip.MWFin { background:#fdf3d9; } .chip.MWDev { background:#f3e9fb; }
select.ent,select.cat { max-width:190px; font-size:12.5px; padding:5px; border:1px solid var(--line); border-radius:5px; }
button.go { background:var(--navy); color:#fff; border:none; padding:6px 13px; border-radius:6px; cursor:pointer; font-size:12.5px; }
button.go:disabled { opacity:.4; cursor:default; }
button.ok { background:#1a7a3c; } button.no { background:#b3372b; }
.desc { color:#5b6b7d; font-size:12px; max-width:340px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.legs { font-size:12px; color:#37475c; font-family:Consolas,monospace; }
.note { background:#fdf3d9; border:1px solid #ecd9a0; padding:10px 14px; border-radius:8px; font-size:13px; margin-bottom:14px; }
.flash { position:fixed; bottom:18px; right:18px; background:var(--navy); color:#fff; padding:10px 18px; border-radius:8px; font-size:13px; opacity:0; transition:opacity .3s; }
</style></head><body>
<header><h1><b>MW</b> Books</h1>
<div class="tabs">
  <button id="t-queue" class="on" onclick="show('queue')">Review queue</button>
  <button id="t-transfers" onclick="show('transfers')">Transfers</button>
  <button id="t-iou" onclick="show('iou')">Who owes who</button>
</div>
<div class="userpick">I am:
  <button id="u-webster" onclick="setUser('webster')">Webster</button>
  <button id="u-marisel" onclick="setUser('marisel')">Mary</button>
</div></header>
<main>
<div class="note" id="usernote">Pick who you are (top right) — every decision records who made it.</div>
<section id="queue">
<div class="bar">
  <select id="f-ent" onchange="render()"><option value="">All entities</option></select>
  <input id="f-q" placeholder="search payee / description…" oninput="render()" size="30">
  <span class="count" id="q-count"></span>
</div>
<table><thead><tr><th>Date</th><th>Account</th><th>Payee / description</th>
<th class="amt">Amount</th><th>File under</th><th></th></tr></thead>
<tbody id="q-body"></tbody></table>
</section>
<section id="transfers" style="display:none">
<div class="note">Matched money moves (one out + one in, same amount, ±3 days). Confirm books it for good; Not a transfer flags it for repair — nothing is silently guessed.</div>
<table><thead><tr><th>Date</th><th>What moved</th><th class="amt">Amount</th><th>Legs</th><th></th></tr></thead>
<tbody id="t-body"></tbody></table>
</section>
<section id="iou" style="display:none">
<div class="note">Net reimbursement balances from matched cross-entity moves and reviewed spending. Provisional until the queue is worked through — and whether a balance is really a loan, a contribution, or a distribution is a call for you + Amarilis.</div>
<table><thead><tr><th>Who is owed</th><th>Who owes</th><th class="amt">Net amount</th></tr></thead>
<tbody id="i-body"></tbody></table>
</section>
</main>
<div class="flash" id="flash"></div>
<script>
let USER = localStorage.getItem('mw_user') || '';
let DATA = {rows:[], cats:{}}, TR = [], IOU = [];
const ENT = ["Personal","MWFin","MWRealty","Suncorps","MWDev","KML","PropMgmt"];
function setUser(u){ USER=u; localStorage.setItem('mw_user',u); paintUser(); }
function paintUser(){
  for (const u of ['webster','marisel'])
    document.getElementById('u-'+u).className = (USER===u?'on':'');
  document.getElementById('usernote').style.display = USER?'none':'block';
}
function show(t){
  for (const s of ['queue','transfers','iou']) {
    document.getElementById(s).style.display = (s===t?'':'none');
    document.getElementById('t-'+s).className = (s===t?'on':'');
  }
}
function money(x){ return (x<0?'-':'') + '$' + Math.abs(x).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function esc(s){ return (s||'').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function flash(m){ const f=document.getElementById('flash'); f.textContent=m; f.style.opacity=1; setTimeout(()=>f.style.opacity=0, 1800); }

async function load(){
  DATA = await (await fetch('/api/queue')).json();
  TR = (await (await fetch('/api/transfers')).json()).rows;
  IOU = (await (await fetch('/api/iou')).json()).rows;
  const fe = document.getElementById('f-ent');
  fe.innerHTML = '<option value="">All entities</option>' + ENT.map(e=>`<option>${e}</option>`).join('');
  render(); renderTr(); renderIou();
}
function catOptions(ent){
  const c = DATA.cats[ent] || {Expenses:[],Income:[]};
  const shorten = a => a.split(':').slice(2).join(':');
  return '<option value="" disabled selected>— category —</option>'
    + '<optgroup label="Expenses">' + c.Expenses.map(a=>`<option value="${a}">${shorten(a)}</option>`).join('') + '</optgroup>'
    + '<optgroup label="Income">' + c.Income.map(a=>`<option value="${a}">${shorten(a)}</option>`).join('') + '</optgroup>';
}
function render(){
  const ent = document.getElementById('f-ent').value;
  const q = document.getElementById('f-q').value.toLowerCase();
  let rows = DATA.rows.filter(r => (!ent || r.entity===ent) &&
    (!q || (r.payee+' '+r.narration+' '+r.acct_short).toLowerCase().includes(q)));
  document.getElementById('q-count').textContent =
    rows.length + ' to review' + (rows.length>200?' (showing 200)':'');
  document.getElementById('q-body').innerHTML = rows.slice(0,200).map(r=>`
   <tr id="row-${r.sid}">
    <td>${r.date}</td>
    <td><span class="chip ${r.entity}">${r.entity}</span><br><small>${esc(r.acct_short)}</small></td>
    <td>${esc(r.payee)}${r.ambig?' <span class="chip">possible transfer</span>':''}<div class="desc" title="${esc(r.narration)}">${esc(r.narration)}</div></td>
    <td class="amt ${r.amount<0?'neg':'pos'}">${money(r.amount)}</td>
    <td>
      <select class="ent" id="e-${r.sid}" onchange="document.getElementById('c-${r.sid}').innerHTML=catOptions(this.value)">
        <option value="" disabled ${''}>— entity —</option>
        ${ENT.map(e=>`<option ${e===r.entity?'selected':''}>${e}</option>`).join('')}
      </select>
      <select class="cat" id="c-${r.sid}">${catOptions(r.entity)}</select>
    </td>
    <td><button class="go" onclick="assign('${r.sid}')">File</button></td>
   </tr>`).join('');
}
async function assign(sid){
  if (!USER) { flash('Pick who you are first (top right)'); return; }
  const entity = document.getElementById('e-'+sid).value;
  const category = document.getElementById('c-'+sid).value;
  if (!entity || !category) { flash('Pick entity and category'); return; }
  const r = await fetch('/api/assign', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({sid, entity, category, user: USER})});
  const j = await r.json();
  if (j.ok) { document.getElementById('row-'+sid).remove();
    DATA.rows = DATA.rows.filter(x=>x.sid!==sid); flash('Filed ✓'); }
  else flash(j.error || 'error');
}
function renderTr(){
  document.getElementById('t-body').innerHTML = TR.slice(0,200).map(r=>`
   <tr id="tr-${r.sid}">
    <td>${r.date}</td>
    <td>${esc(r.narration)}${r.cross?' <span class="chip">cross-entity IOU</span>':''}<div class="desc">${esc(r.desc)}</div></td>
    <td class="amt">${money(r.amount)}</td>
    <td class="legs">${r.legs.map(l=>esc(l[0].split(':').slice(1).join(':'))+' '+money(l[1])).join('<br>')}</td>
    <td><button class="go ok" onclick="verdict('${r.sid}','ok')">Confirm</button>
        <button class="go no" onclick="verdict('${r.sid}','reject')">Not a transfer</button></td>
   </tr>`).join('');
}
async function verdict(sid, v){
  if (!USER) { flash('Pick who you are first (top right)'); return; }
  const r = await fetch('/api/confirm_transfer', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({sid, verdict:v, user:USER})});
  const j = await r.json();
  if (j.ok) { document.getElementById('tr-'+sid).remove(); flash(v==='ok'?'Confirmed ✓':'Flagged for repair'); }
  else flash(j.error || 'error');
}
function renderIou(){
  document.getElementById('i-body').innerHTML = IOU.map(r=>`
   <tr><td><span class="chip ${r.creditor}">${r.creditor}</span> is owed</td>
   <td>by <span class="chip ${r.debtor}">${r.debtor}</span></td>
   <td class="amt">${money(r.amount)}</td></tr>`).join('') ||
   '<tr><td colspan=3>Nothing outstanding.</td></tr>';
}
paintUser(); load();
</script></body></html>"""


@app.get("/")
def index():
    return render_template_string(PAGE)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    print(f"MW Books UI -> http://localhost:{port}   (Ctrl+C stops it)")
    app.run(host="127.0.0.1", port=port, debug=False)
