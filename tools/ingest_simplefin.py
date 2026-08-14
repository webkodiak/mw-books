#!/usr/bin/env python3
"""MW Books - ingest SimpleFIN transactions into the Beancount ledger.

Rules (Webster's, non-negotiable):
- Dedup on SimpleFIN's stable transaction id; re-runs never duplicate.
- Transfers between our own accounts are NEVER income/expense. A matched
  out+in pair books as one transfer; if it crosses entities it carries
  due-from/due-to IOU legs so each entity stays internally balanced.
- Anything not auto-matched books against <Entity>:Uncategorized with the
  #unreviewed tag -> that IS the review queue. Nothing is guessed silently:
  ambiguous transfer matches stay unmatched and get #transfer-candidate.
- Accounts with no confirmed entity (flagged rows) are SKIPPED and counted.

Usage: python3 ingest_simplefin.py <simplefin_transactions.json>
Writes entities/txns/<entity>-<year>.beancount, intercompany opens, balance
anchors, an include index, and data/ingest_state.json (dedup memory).
"""
import csv, datetime, json, os, re, sys
from collections import defaultdict
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INV = os.path.join(ROOT, "inventory", "account-inventory.csv")
TXNDIR = os.path.join(ROOT, "entities", "txns")
STATE = os.path.join(ROOT, "data", "ingest_state.json")
DUP_FEED_IDS = {"ACT-3bd1adfa-76a6-4820-9a80-627888a7f1af"}  # WF-2443 duplicate
MATCH_WINDOW_DAYS = 3

# Accounts whose Jan->Jul 2026 history was backfilled from the D1 export
# BEFORE their first feed ingestion (opened 2026-08-14 on Webster's answer to
# inventory flags 1-2). Their FIRST feed pull overlaps that backfill, so a
# feed txn on these accounts matching a #d1-backfill entry (same account,
# same amount, +/-4 days) is skipped as already booked. Only these accounts
# are guarded - everywhere else the feed remains the sole writer.
D1_GUARDED_ACCTS = {
    "Liabilities:Personal:Card:Discover-6368",
    "Liabilities:Personal:Card:WF-Platinum-4965",
}
D1_GUARD_WINDOW_DAYS = 4

def d1_backfill_index():
    """(account, amount) -> [dates] for every #d1-backfill posting on a
    guarded account."""
    import io as _io
    from collections import defaultdict as _dd
    idx = _dd(list)
    post_re = re.compile(r"^\s+((?:Assets|Liabilities)[A-Za-z0-9:\-]+)\s+(-?[\d,]+\.\d{2}|-?\d+)\s+USD")
    for fn in os.listdir(TXNDIR):
        if not fn.endswith(".beancount"):
            continue
        cur_date, is_d1 = None, False
        for line in _io.open(os.path.join(TXNDIR, fn), encoding="utf-8"):
            m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+[*!]\s", line)
            if m:
                cur_date = datetime.date.fromisoformat(m.group(1))
                is_d1 = "#d1-backfill" in line
                continue
            p = post_re.match(line)
            if p and cur_date and is_d1 and p.group(1) in D1_GUARDED_ACCTS:
                idx[(p.group(1), Decimal(p.group(2).replace(",", "")))].append(cur_date)
    return idx

def clean(s):
    s = re.sub(r"[^\x20-\x7E]", " ", s or "")          # strip mojibake
    s = s.replace('"', "'")                            # quotes break beancount strings
    return re.sub(r"\s+", " ", s).strip()

def main(json_path):
    os.makedirs(TXNDIR, exist_ok=True)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"seen": {}}
    seen = state["seen"]

    acct_map = {}   # simplefin id -> row
    for r in csv.DictReader(open(INV, encoding="utf-8")):
        if r["account_id"] and r["beancount_account"] and r["status"] == "OK":
            acct_map[r["account_id"]] = r

    data = json.load(open(json_path, encoding="utf-8"))
    txns, skipped_unmapped, skipped_dupfeed, skipped_seen = [], 0, 0, 0
    skipped_d1 = 0
    d1_idx = d1_backfill_index()
    balances = []
    for a in data.get("accounts", []):
        aid = a.get("id")
        if aid in DUP_FEED_IDS:
            skipped_dupfeed += len(a.get("transactions", []))
            continue
        row = acct_map.get(aid)
        if not row:
            skipped_unmapped += len(a.get("transactions", []))
            continue
        balances.append((row, a.get("balance"), a.get("balance-date") or a.get("balance_date")))
        for t in a.get("transactions", []):
            tid = t["id"]
            if tid in seen:
                skipped_seen += 1
                continue
            if row["beancount_account"] in D1_GUARDED_ACCTS:
                _d = datetime.datetime.utcfromtimestamp(t["posted"]).date()
                _a = Decimal(t["amount"])
                if any(abs((x - _d).days) <= D1_GUARD_WINDOW_DAYS
                       for x in d1_idx.get((row["beancount_account"], _a), [])):
                    seen[tid] = str(_d)   # booked via d1-backfill; never re-ingest
                    skipped_d1 += 1
                    continue
            txns.append(dict(
                id=tid, acct=row["beancount_account"],
                entity=row["beancount_account"].split(":")[1],
                date=datetime.datetime.utcfromtimestamp(t["posted"]).date(),
                amount=Decimal(t["amount"]),
                payee=clean(t.get("payee") or ""), desc=clean(t.get("description") or ""),
                mcc=t.get("mcc")))

    # cumulative per-account sum of everything ever ingested (for pad logic)
    sums = state.setdefault("acct_sum", {})
    for t in txns:
        sums[t["acct"]] = str(Decimal(sums.get(t["acct"], "0")) + t["amount"])

    # ---- transfer matching: exact amount, opposite sign, different account,
    # ---- within MATCH_WINDOW_DAYS, unique candidate only (never guess) ----
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

    entries = defaultdict(list)   # (entity, year) -> [text]
    inter_opens = set()

    def emit(entity, year, text):
        entries[(entity, year)].append(text)

    for out_t, in_t in pairs:
        d = max(out_t["date"], in_t["date"])
        amt = -out_t["amount"]
        same = out_t["entity"] == in_t["entity"]
        narr = f"Transfer {out_t['acct'].split(':')[-1]} -> {in_t['acct'].split(':')[-1]}"
        desc = out_t["desc"] or in_t["desc"]
        lines = [f'{d} * "{narr}" #transfer #auto-matched',
                 f'  narration2: "{desc[:120]}"',
                 f'  simplefin_out: "{out_t["id"]}"',
                 f'  simplefin_in: "{in_t["id"]}"',
                 f'  {out_t["acct"]}  {out_t["amount"]} USD']
        if not same:
            ef, et = out_t["entity"], in_t["entity"]
            dfrom = f"Assets:{ef}:DueFrom:{et}"
            dto = f"Liabilities:{et}:DueTo:{ef}"
            inter_opens.update([dfrom, dto])
            lines += [f'  {dfrom}  {amt} USD',
                      f'  {in_t["acct"]}  {amt} USD',
                      f'  {dto}  {-amt} USD']
        else:
            lines += [f'  {in_t["acct"]}  {amt} USD']
        emit(out_t["entity"], d.year, "\n".join(lines))
        seen[out_t["id"]] = seen[in_t["id"]] = str(d)

    for t in txns:
        if t["id"] in consumed or t["id"] in seen:
            continue
        cat = "Expenses" if t["amount"] < 0 else "Income"
        counter = f"{cat}:{t['entity']}:Uncategorized"
        tags = "#unreviewed" + (" #transfer-candidate" if t.get("ambig") else "")
        payee = (t["payee"] or t["desc"][:40]).replace('"', "'")
        desc = t["desc"].replace('"', "'")
        lines = [f'{t["date"]} ! "{payee}" "{desc[:120]}" {tags}',
                 f'  simplefin_id: "{t["id"]}"']
        if t.get("mcc"): lines.append(f'  mcc: "{t["mcc"]}"')
        lines += [f'  {t["acct"]}  {t["amount"]} USD',
                  f'  {counter}  {-t["amount"]} USD']
        emit(t["entity"], t["date"].year, "\n".join(lines))
        seen[t["id"]] = str(t["date"])

    # ---- write per-entity-year files (append mode: only new entries) ----
    written = 0
    for (entity, year), texts in sorted(entries.items()):
        p = os.path.join(TXNDIR, f"{entity.lower()}-{year}.beancount")
        new = not os.path.exists(p)
        with open(p, "a", encoding="utf-8") as f:
            if new:
                f.write(f";; {entity} transactions {year} - GENERATED by ingest_simplefin.py, append-only\n")
            f.write("\n" + "\n\n".join(texts) + "\n")
        written += len(texts)

    # ---- intercompany due-to/due-from opens (idempotent regenerate) ----
    iop = os.path.join(TXNDIR, "intercompany.beancount")
    existing = set()
    if os.path.exists(iop):
        existing = {l.split()[2] for l in open(iop, encoding="utf-8")
                    if l.startswith("2025-01-01 open ")}
    with open(iop, "a", encoding="utf-8") as f:
        if not existing:
            f.write(";; Intercompany IOU accounts - GENERATED, append-only\n")
        for acc in sorted(inter_opens - existing):
            f.write(f"2025-01-01 open {acc}  USD\n")

    # ---- balance anchors: pad at start date + assertion at balance date ----
    anch = os.path.join(TXNDIR, "anchors.beancount")
    with open(anch, "w", encoding="utf-8") as f:
        f.write(";; Balance anchors - REGENERATED each ingest run.\n"
                ";; pad 2025-01-01 absorbs pre-history into Opening-Balances\n"
                ";; (PROVISIONAL until statement backfill covers 2025).\n\n")
        for row, bal, bdate in sorted(balances, key=lambda x: x[0]["beancount_account"]):
            if bal in (None, ""):
                continue
            acc = row["beancount_account"]
            ent = acc.split(":")[1]
            d = (datetime.datetime.utcfromtimestamp(int(bdate)).date()
                 + datetime.timedelta(days=1)) if bdate else datetime.date.today()
            remainder = Decimal(bal) - Decimal(sums.get(acc, "0"))
            if remainder != 0:   # pad only if pre-history exists, else unused-pad error
                f.write(f"2025-01-01 pad {acc} Equity:{ent}:Opening-Balances\n")
            f.write(f"{d} balance {acc}  {bal} USD\n\n")

    # ---- include index ----
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
    print(f"  transfer pairs    : {len(pairs)} ({sum(1 for p in pairs if p[0]['entity']!=p[1]['entity'])} cross-entity with IOU legs)")
    print(f"  review queue (#unreviewed): {written - len(pairs)}")
    print(f"skipped - already ingested : {skipped_seen}")
    print(f"skipped - duplicate feed   : {skipped_dupfeed}")
    print(f"skipped - unmapped/flagged : {skipped_unmapped}")
    print(f"skipped - d1-backfilled    : {skipped_d1}")

if __name__ == "__main__":
    main(sys.argv[1])
