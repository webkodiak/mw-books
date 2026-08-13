# MW Books

Self-hosted bookkeeping for the MW Group + personal. Ledger of record for the numbers;
Google Drive keeps the paper. Supersedes the Cloudflare `mw-accounting` app (zero
transactions were ever imported there, so there is nothing to migrate).

**Backbone (non-negotiable, per the 2026-08-09 kickoff doc):**

- Ledger: **Beancount v3** — plain-text double-entry, this repo, in git
- UI: **Fava** — `pip3 install fava`, then `fava main.beancount` → http://localhost:5000
- Feeds: **SimpleFIN Bridge** (~$15/yr) — not Plaid, not Rocket Money
- We build only **ingestion** and **classification**. No debit/credit logic, no
  reporting layer, no retained-earnings math. If you're writing any of those, stop.

## Layout

```
main.beancount        consolidated ledger (options + includes) — run Fava on this
entities/             one file per filing entity + personal, accounts namespaced
                      by entity code (Assets:MWFin:…, Expenses:MWRealty:…)
importers/            Step 1–2: SimpleFIN pull + statement parsers (gated on Step 0)
rules/                Step 4: merchant → entity + account rules; review queue config
inventory/            Step 0: the account inventory / connectivity survey
docs/                 decisions, branding notes, runbooks
```

## Entity codes

| Code | Entity | Return |
|---|---|---|
| MWFin | MW Financial LLC (MW LOANS) | 1120-S |
| MWRealty | MW Realty Group Corp | 1120-S |
| Suncorps | Suncorps Construction, Inc. | 1120 |
| MWDev | MW Development LLC | ⚠ confirm |
| KML | KML Screen & Painting LLC | ⚠ confirm |
| PropMgmt | Property Management Co (Marine) | ⚠ confirm scope |
| Personal | Webster — Personal | — |

Per-entity statements in Fava: filter with `^(Assets|Liabilities|Income|Expenses|Equity):MWFin`
(or open the entity's file directly). Consolidated = `main.beancount` unfiltered.

## Iron rules

1. **Routing key is the bank account, not the person.** A transaction belongs to the
   entity whose account it hit. No "business vs personal" blob.
2. **Intercompany moves are due-to/due-from on both sides** — never income, never
   expense. Pattern: `Assets:<A>:DueFrom:<B>` ↔ `Liabilities:<B>:DueTo:<A>`.
3. **The statement or feed creates the transaction; email only attaches to it.**
   One email may match many charges (Amazon split shipments).
4. **Dedup is ours.** Stable transaction key + rolling re-pull window on every
   SimpleFIN ingest. Fava/Beancount v3 will not do it for us.
5. **~85% automation is the target.** Feed the high-volume accounts, statement-parse
   the stragglers, keep a manual entry path. Review queue gets cleared monthly.

## Build order & status

- [x] Scaffold: entity files, draft chart of accounts, Fava verified
- [ ] **Step 0 — connectivity survey** (BLOCKED on Webster: SimpleFIN signup + account list)
- [ ] Step 1 — SimpleFIN ingestion + dedup
- [ ] Step 2 — statement parsers (one per issuer) for whatever didn't connect
- [ ] Step 3 — email enrichment (match, never create)
- [ ] Step 4 — rules file + review queue
- [ ] Step 5 — intercompany transfer handling
- [ ] Opening balances as of 2026-01-01 (pad + balance assertions per account)
- [ ] MW branding on Fava (light-touch theme extension — see docs/branding.md)

## Chart of accounts

The opens in `entities/*.beancount` are a DRAFT. If Amarilis (CPA) has a chart of
accounts, remap to hers before serious import volume. Bank/card accounts get opened
one-per-real-account as the inventory is confirmed.
