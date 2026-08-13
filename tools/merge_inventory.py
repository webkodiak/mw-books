#!/usr/bin/env python3
"""MW Books - merge the fresh SimpleFIN survey with Webster's ownership answers.

Inputs:
  1. simplefin_survey.csv   (fresh account list, written by step0_v5.py)
  2. accountinventory.csv   (Webster's filled sheet; YOUR_ANSWER_whose_is_it is
                             AUTHORITATIVE for who owns each account)
  3. A few known accounts that never appear in SimpleFIN (Mercury, Schwab,
     NewRez, Stripe, Amazon store card, PayPal) - carried as manual lanes.

Output: account-inventory.csv - one final inventory, one row per real-world
account, with the entity, the proposed Beancount account name, and a STATUS
flag for anything needing Webster's attention. Nothing is guessed silently.

Usage:  python merge_inventory.py <survey.csv> <answers.csv> <out.csv>
"""
import csv, re, sys

# ---------------------------------------------------------------- entities --
def entity_of(answer):
    """Map Webster's free-text answer to (entity_code, person_owner)."""
    a = (answer or "").strip().lower()
    if not a:
        return "", ""
    if "financial" in a:            return "MWFin", ""
    if "realty" in a:               return "MWRealty", ""
    if "development" in a:          return "MWDev", ""
    if "suncorp" in a:              return "Suncorps", ""
    if "kml" in a:                  return "KML", ""
    if "property" in a or "marine" in a: return "PropMgmt", ""
    if "mary" in a:                 return "Personal", "mary"
    if "web" in a:                  return "Personal", "webster"
    return "CHECK:" + answer, ""    # unrecognized -> flag, never guess

# ------------------------------------------------- institution short names --
INST_SHORT = [
    ("wells fargo", "WF"), ("bank of america", "BofA"), ("chase", "Chase"),
    ("home depot", "HomeDepot"), ("costco", "Costco"), ("best buy", "BestBuy"),
    ("wayfair", "Wayfair"), ("american express", "Amex"),
    ("capital one", "CapOne"), ("m&t", "MT"), ("carecredit", "CareCredit"),
    ("synchrony", "Synchrony"), ("credit one", "CreditOne"),
    ("target", "Target"), ("caesars", "Caesars"), ("apple", "AppleCard"),
    ("amazon", "AmazonStore"), ("paypal", "PayPal"), ("mercury", "Mercury"),
    ("schwab", "Schwab"), ("newrez", "NewRez"), ("stripe", "Stripe"),
    ("citi", "Citi"),
]
def inst_short(name):
    n = (name or "").lower()
    for key, short in INST_SHORT:
        if key in n:
            return short
    return re.sub(r"[^A-Za-z0-9]", "", name or "Unknown")[:12] or "Unknown"

def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def product_hint(account_name):
    """Short product tag to disambiguate multiple cards at one bank."""
    n = (account_name or "").lower()
    for key, tag in [("reflect", "Reflect"), ("platinum card", "Platinum"),
                     ("platinum", "Platinum"), ("sapphire", "Sapphire"),
                     ("ink", "Ink"), ("hilton", "Hilton"),
                     ("cash rewards", "CCR"), ("prime", "Prime")]:
        if key in n:
            return tag
    return ""

def is_liability(row):
    n = (row.get("account_name") or "").lower()
    if "mortgage" in n: return "mortgage"
    if any(w in n for w in ("card", "visa", "amex", "mastercard", "credit",
                            "quicksilver", "circlecard")): return "card"
    try:
        if float(row.get("balance") or 0) < 0: return "card"
    except ValueError:
        pass
    return ""

def bean_name(entity, owner, row, last4):
    inst = inst_short(row.get("institution", ""))
    hint = product_hint(row.get("account_name", ""))
    bits = [b for b in (inst, hint, last4) if b]
    leaf = "-".join(bits)
    kind = is_liability(row)
    if entity.startswith("CHECK") or not entity:
        return ""
    if kind == "mortgage":
        return f"Liabilities:{entity}:Mortgage:{leaf}"
    if kind == "card":
        return f"Liabilities:{entity}:Card:{leaf}"
    return f"Assets:{entity}:Bank:{leaf}"

# --------------------------------------------- accounts SimpleFIN never has --
MANUAL_LANES = [
    dict(institution="Mercury", account_name="Business checking (which entities?)",
         feed_lane="TBD - native Mercury API", status="NEEDS_ANSWER",
         notes="Old inventory says group bank, per-entity breakdown unknown"),
    dict(institution="Charles Schwab", account_name="Futures account", last4="104",
         feed_lane="TBD - maybe out of scope v1", status="NEEDS_ANSWER",
         notes="Investment acct - Webster to confirm in/out of scope"),
    dict(institution="NewRez", account_name="Mortgage", last4="7885",
         feed_lane="statement-parse", status="NEEDS_ANSWER",
         notes="Statement addressed to Asela Acosta - whose property?"),
    dict(institution="Stripe", account_name="Merchant account",
         feed_lane="Stripe reports", status="NEEDS_ANSWER",
         notes="Which entity receives payouts?"),
]

def main(survey_path, answers_path, out_path):
    survey = list(csv.DictReader(open(survey_path, encoding="utf-8-sig")))
    answers = list(csv.DictReader(open(answers_path, encoding="utf-8-sig")))

    # index answers: by last4, and by (institution, name)
    by_last4, by_name = {}, {}
    for a in answers:
        l4 = (a.get("last4") or "").strip().lstrip("0") or (a.get("last4") or "").strip()
        if (a.get("last4") or "").strip():
            by_last4[(norm(a["institution"]), (a.get("last4") or "").strip())] = a
        by_name[(norm(a["institution"]), norm(a["account_name"]))] = a

    out, used = [], set()
    for s in survey:
        s_inst, s_name = norm(s.get("institution")), norm(s.get("account_name"))
        digits = re.findall(r"\d{4}", (s.get("account_name") or "") + " " + (s.get("account_id") or ""))
        match = None
        for d in digits:
            match = by_last4.get((s_inst, d))
            if match: break
        if not match:
            # institution may be named slightly differently (Citi cards etc.)
            for d in digits:
                cands = [a for (ai, al), a in by_last4.items() if al == d]
                if len(cands) == 1:
                    match = cands[0]; break
        if not match:
            match = by_name.get((s_inst, s_name))
        if not match:
            cands = [a for (ai, an), a in by_name.items()
                     if an == s_name and (ai in s_inst or s_inst in ai)]
            if len(cands) == 1:
                match = cands[0]
        last4 = (match.get("last4").strip() if match else
                 (digits[-1] if digits else ""))
        answer = match.get("YOUR_ANSWER_whose_is_it", "") if match else ""
        entity, owner = entity_of(answer)
        status = "OK" if match and entity and not entity.startswith("CHECK") else \
                 ("CHECK_ANSWER" if match else "NEW_NEEDS_ANSWER")
        if match:
            used.add(id(match))
        out.append(dict(
            status=status, entity=entity, owner=owner,
            institution=s.get("institution", ""),
            account_name=s.get("account_name", ""), last4=last4,
            account_id=s.get("account_id", ""),
            currency=s.get("currency", ""), balance=s.get("balance", ""),
            balance_date=s.get("balance_date", ""), connects="yes",
            needs_reauth="", feed_lane="simplefin",
            beancount_account=bean_name(entity, owner,
                {"institution": s.get("institution"),
                 "account_name": s.get("account_name"),
                 "balance": s.get("balance")}, last4),
            notes=(match.get("note", "") if match else "NEW since Webster's sheet - whose is it?"),
        ))

    # answered rows that the fresh survey did NOT return
    for a in answers:
        if id(a) in used:
            continue
        entity, owner = entity_of(a.get("YOUR_ANSWER_whose_is_it", ""))
        connects = (a.get("connects") or "").strip().lower()
        planned = connects == "no"   # Amazon/PayPal: expected, planned lanes
        out.append(dict(
            status="MANUAL_LANE" if planned else "MISSING_FROM_SURVEY",
            entity=entity, owner=owner, institution=a.get("institution", ""),
            account_name=a.get("account_name", ""), last4=a.get("last4", ""),
            account_id="", currency="USD", balance=a.get("balance_usd", ""),
            balance_date="", connects=a.get("connects", ""),
            needs_reauth=a.get("needs_reauth", ""),
            feed_lane="statement-parse" if planned else "simplefin (was connected - recheck!)",
            beancount_account=bean_name(entity, owner,
                {"institution": a.get("institution"),
                 "account_name": a.get("account_name") or a.get("institution"),
                 "balance": a.get("balance_usd")}, (a.get("last4") or "").strip()),
            notes=a.get("note", ""),
        ))

    # known manual lanes not in either file
    have = {(norm(r["institution"]), r.get("last4", "")) for r in out}
    for m in MANUAL_LANES:
        if (norm(m["institution"]), m.get("last4", "")) in have:
            continue
        out.append(dict(status=m["status"], entity="", owner="",
                        institution=m["institution"],
                        account_name=m["account_name"],
                        last4=m.get("last4", ""), account_id="", currency="USD",
                        balance="", balance_date="", connects="no",
                        needs_reauth="", feed_lane=m["feed_lane"],
                        beancount_account="", notes=m["notes"]))

    cols = ["status", "entity", "owner", "institution", "account_name", "last4",
            "account_id", "currency", "balance", "balance_date", "connects",
            "needs_reauth", "feed_lane", "beancount_account", "notes"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(out)

    flags = [r for r in out if r["status"] not in ("OK", "MANUAL_LANE")]
    print(f"{len(out)} rows written -> {out_path}")
    print(f"{len(flags)} row(s) flagged for Webster:")
    for r in flags:
        print(f"  [{r['status']}] {r['institution']}: {r['account_name']} "
              f"...{r['last4']} -> {r['entity'] or 'entity?'}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: python merge_inventory.py <survey.csv> <answers.csv> <out.csv>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
