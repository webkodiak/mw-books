#!/usr/bin/env python3
"""MW Books - one-shot backfill from the mw-accounting D1 final export.

The retired D1 app (torn down 2026-08-14) was loaded from a Rocket Money CSV
with full-year history; the SimpleFIN feed only reaches back to ~2026-05-18.
This ingests the D1 rows the ledger does NOT already have - i.e. the
Jan->mid-May 2026 pre-history for the personal accounts - under the exact
same rules as ingest_simplefin.py:

- Dedup two ways: D1 txn id recorded in data/ingest_state.json "seen", AND
  any D1 row whose (account,amount) already exists in the ledger within
  +/-4 days is skipped as feed-covered.
- Transfers between our own accounts book as one transfer (never
  income/expense); cross-entity carries due-from/due-to IOU legs.
- Everything else books against <Entity>:Uncategorized with #unreviewed ->
  the review queue. Nothing guessed silently.
- Accounts with no confirmed beancount_account in the inventory (the open
  NEW_NEEDS_ANSWER flags) are SKIPPED and counted.
- Every entry carries #d1-backfill and its d1_id so the lane is traceable.
- Accounts touched for the first time get a 2025-01-01 pad line in
  anchors.beancount (their balance assertion would otherwise break).

Usage: python3 ingest_d1_backup.py <backup.sql>
Re-runs are no-ops (ids in seen).
"""
import csv, datetime, io, json, os, re, sqlite3, sys
from collections import defaultdict
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INV = os.path.join(ROOT, "inventory", "account-inventory.csv")
TXNDIR = os.path.join(ROOT, "entities", "txns")
STATE = os.path.join(ROOT, "data", "ingest_state.json")
MATCH_WINDOW_DAYS = 3      # transfer pairing, same as ingest_simplefin.py
LEDGER_DEDUP_DAYS = 4      # "already covered by the feed" window

def clean(s):
    s = re.sub(r"[^\x20-\x7E]", " ", s or "")
    s = s.replace('"', "'")
    return re.sub(r"\s+", " ", s).strip()

def parse_ledger_postings():
    """(resolved last4, cents) -> [dates] for every real-account posting."""
    txn_re = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+[*!]\s")
    post_re = re.compile(r"^\s+((?:Assets|Liabilities)[A-Za-z0-9:\-]+)\s+(-?[\d,]+\.\d{2})\s+USD")
    idx = defaultdict(list)
    for fn in os.listdir(TXNDIR):
        if not fn.endswith(".beancount"):
            continue
        cur = None
        for line in io.open(os.path.join(TXNDIR, fn), encoding="utf-8"):
            m = txn_re.match(line)
            if m:
                cur = datetime.date.fromisoformat(m.group(1))
                continue
            p = post_re.match(line)
            if p and cur:
                m4 = re.search(r"(\d{4})$", p.group(1))
                if m4:
                    cents = round(Decimal(p.group(2).replace(",", "")) * 100)
                    idx[(m4.group(1), int(cents))].append(cur)
    return idx

def main(sql_path):
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"seen": {}}
    seen = state["seen"]

    # inventory: last4 -> beancount account (confirmed rows only)
    l4map = {}
    for r in csv.DictReader(open(INV, encoding="utf-8")):
        if r["status"] == "OK" and r["beancount_account"]:
            prev = l4map.get(r["last4"])
            if prev and prev != r["beancount_account"]:
                sys.exit(f"inventory maps last4 {r['last4']} to two accounts - fix first")
            l4map[r["last4"]] = r["beancount_account"]

    db = sqlite3.connect(":memory:")
    db.executescript(io.open(sql_path, encoding="utf-8").read())
    rows = db.execute(
        """SELECT t.id, a.last4, a.name, t.txn_date, t.amount_cents,
                  t.description, t.category_id
           FROM transactions t JOIN accounts a ON a.id = t.account_id
           ORDER BY t.txn_date, t.id""").fetchall()

    ledger = parse_ledger_postings()

    txns, skipped_unmapped, skipped_covered, skipped_seen = [], 0, 0, 0
    for tid, last4, aname, dstr, cents, desc, cat in rows:
        if tid in seen:
            skipped_seen += 1
            continue
        acct = l4map.get(last4)
        if not acct:
            skipped_unmapped += 1
            continue
        d = datetime.date.fromisoformat(dstr)
        if any(abs((x - d).days) <= LEDGER_DEDUP_DAYS
               for x in ledger.get((last4, cents), [])):
            skipped_covered += 1
            continue
        txns.append(dict(
            id=tid, acct=acct, entity=acct.split(":")[1], date=d,
            amount=Decimal(cents) / 100, desc=clean(desc), cat=cat or ""))

    # cumulative per-account sums (anchors pad logic depends on these)
    sums = state.setdefault("acct_sum", {})
    for t in txns:
        sums[t["acct"]] = str(Decimal(sums.get(t["acct"], "0")) + t["amount"])

    # transfer matching - same rules as ingest_simplefin.py
    by_amt = defaultdict(list)
    for t in txns:
        by_amt[abs(t["amount"])].append(t)
    consumed, pairs = set(), []
    for t in sorted(txns, key=lambda x: (x["date"], x["id"])):
        if t["id"] in consumed or t["amount"] >= 0:
            continue
        cands = [c for c in by_amt[abs(t["amount"])]
                 if c["id"] not in consumed and c["amount"] == -t["amount"]
                 and c["acct"] != t["acct"]
                 and abs((c["date"] - t["date"]).days) <= MATCH_WINDOW_DAYS]
        if len(cands) == 1:
            pairs.append((t, cands[0]))
            consumed.add(t["id"]); consumed.add(cands[0]["id"])
        elif len(cands) > 1:
            t["ambig"] = True
            for c in cands: c["ambig"] = True

    entries = defaultdict(list)
    inter_opens = set()

    for out_t, in_t in pairs:
        d = max(out_t["date"], in_t["date"])
        amt = -out_t["amount"]
        narr = f"Transfer {out_t['acct'].split(':')[-1]} -> {in_t['acct'].split(':')[-1]}"
        desc = out_t["desc"] or in_t["desc"]
        lines = [f'{d} * "{narr}" #transfer #auto-matched #d1-backfill',
                 f'  narration2: "{desc[:120]}"',
                 f'  d1_out: "{out_t["id"]}"',
                 f'  d1_in: "{in_t["id"]}"',
                 f'  {out_t["acct"]}  {out_t["amount"]} USD']
        if out_t["entity"] != in_t["entity"]:
            ef, et = out_t["entity"], in_t["entity"]
            dfrom = f"Assets:{ef}:DueFrom:{et}"
            dto = f"Liabilities:{et}:DueTo:{ef}"
            inter_opens.update([dfrom, dto])
            lines += [f'  {dfrom}  {amt} USD',
                      f'  {in_t["acct"]}  {amt} USD',
                      f'  {dto}  {-amt} USD']
        else:
            lines += [f'  {in_t["acct"]}  {amt} USD']
        entries[(out_t["entity"], d.year)].append("\n".join(lines))
        seen[out_t["id"]] = seen[in_t["id"]] = str(d)

    for t in txns:
        if t["id"] in consumed or t["id"] in seen:
            continue
        cat = "Expenses" if t["amount"] < 0 else "Income"
        counter = f"{cat}:{t['entity']}:Uncategorized"
        tags = "#unreviewed #d1-backfill" + (" #transfer-candidate" if t.get("ambig") else "")
        payee = t["desc"][:40] or "(no description)"
        lines = [f'{t["date"]} ! "{payee}" "{t["desc"][:120]}" {tags}',
                 f'  d1_id: "{t["id"]}"']
        if t["cat"]:
            lines.append(f'  d1_category: "{t["cat"]}"')
        lines += [f'  {t["acct"]}  {t["amount"]} USD',
                  f'  {counter}  {-t["amount"]} USD']
        entries[(t["entity"], t["date"].year)].append("\n".join(lines))
        seen[t["id"]] = str(t["date"])

    written = 0
    for (entity, year), texts in sorted(entries.items()):
        p = os.path.join(TXNDIR, f"{entity.lower()}-{year}.beancount")
        new = not os.path.exists(p)
        with open(p, "a", encoding="utf-8") as f:
            if new:
                f.write(f";; {entity} transactions {year} - GENERATED, append-only\n")
            f.write("\n" + "\n\n".join(texts) + "\n")
        written += len(texts)

    # intercompany opens (append only the missing ones)
    iop = os.path.join(TXNDIR, "intercompany.beancount")
    existing = set()
    if os.path.exists(iop):
        existing = {l.split()[2] for l in open(iop, encoding="utf-8")
                    if l.startswith("2025-01-01 open ")}
    missing = sorted(inter_opens - existing)
    if missing:
        with open(iop, "a", encoding="utf-8") as f:
            for acc in missing:
                f.write(f"2025-01-01 open {acc}  USD\n")

    # anchors: any touched account whose balance assertion has no pad line
    # would now fail - insert the pad in place
    anch = os.path.join(TXNDIR, "anchors.beancount")
    lines = io.open(anch, encoding="utf-8").read().splitlines(keepends=True)
    padded = {l.split()[2] for l in lines if " pad " in l}
    touched = {t["acct"] for t in txns}
    out, added_pads = [], []
    for l in lines:
        parts = l.split()
        if (len(parts) >= 3 and parts[1] == "balance"
                and parts[2] in touched and parts[2] not in padded):
            ent = parts[2].split(":")[1]
            out.append(f"2025-01-01 pad {parts[2]} Equity:{ent}:Opening-Balances\n")
            added_pads.append(parts[2])
        out.append(l)
    if added_pads:
        io.open(anch, "w", encoding="utf-8").writelines(out)

    # include index (in case a new entity-year file appeared)
    idx = os.path.join(TXNDIR, "_index.beancount")
    files = sorted(fn for fn in os.listdir(TXNDIR)
                   if fn.endswith(".beancount") and fn != "_index.beancount")
    with open(idx, "w", encoding="utf-8") as f:
        f.write(";; GENERATED include index - do not edit\n")
        for fn in files:
            f.write(f'include "{fn}"\n')

    state["seen"] = seen
    json.dump(state, open(STATE, "w"), indent=0)

    print(f"new entries written : {written}")
    print(f"  transfer pairs    : {len(pairs)} "
          f"({sum(1 for p in pairs if p[0]['entity'] != p[1]['entity'])} cross-entity with IOU legs)")
    print(f"  review queue (#unreviewed): {written - len(pairs)}")
    print(f"skipped - already in seen  : {skipped_seen}")
    print(f"skipped - feed-covered     : {skipped_covered}")
    print(f"skipped - unmapped/flagged : {skipped_unmapped}")
    if added_pads:
        print(f"pads added in anchors      : {', '.join(added_pads)}")
    if missing:
        print(f"intercompany opens added   : {', '.join(missing)}")

if __name__ == "__main__":
    main(sys.argv[1])
