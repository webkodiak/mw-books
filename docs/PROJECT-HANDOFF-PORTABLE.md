# MW Books & MW Group — Portable Project Handoff

**Purpose of this file:** a self-contained brief you can paste into a brand-new
cloud account / AI project so it can pick up the MW Group work cold. It assumes
zero prior context. Last updated 2026-08-14.

> If you are the new account reading this: start by getting access to the repos
> (see §2), clone `mw-books`, then read `docs/HANDOFF.md` inside it — that is the
> *living* build log and always supersedes this file where they differ.

---

## 1. What this project is

**MW Books** is a self-hosted bookkeeping system that holds *all* the money for
Webster and his wife — both spouses' personal spending plus every MW Group
business — which today is heavily commingled across personal and business
accounts.

The core daily job is **SEPARATION** on two independent dimensions:

- **ENTITY (who owns it):** MW Financial LLC, MW Realty Group Corp, Suncorps
  Construction Inc, MW Development LLC, KML Screen & Painting LLC, a Property
  Management company, or **Personal**. Entity is decided by *which bank account
  the money hit* — never by whether a purchase "feels" business or personal.
- **PROJECT (optional budgeted container):** e.g. Office Renovation, Home
  Renovation. Projects cut across entities, carry budgets, and alert on overage.

Every transaction ultimately lands in exactly one entity (or Personal); nothing
stays in a vague pile. Anything uncertain is **flagged to a review queue, never
guessed.**

**Superseded predecessor (so you aren't confused by old references):** a
Cloudflare Worker + D1 app called the "MW Group Accounting System"
(`mw-accounting`, deployed 2026-08-01) was briefly the ledger of record.
Webster ruled 2026-08-14: **MW Books supersedes it** — that app is retired from
bookkeeping, nothing new gets built on it, and its Rocket-Money-feed plan died
with it. Any mention of `mw-accounting` or a D1 accounting app means the old
system, not this one.

## 2. GitHub repos (the emphasis of this handoff)

| Repo | URL | Visibility | Role |
|------|-----|-----------|------|
| **mw-books** | `github.com/webkodiak/mw-books` | **Private** | The bookkeeping system itself — the system of record. Beancount ledger, tools, docs, the MW-UI. This is where 95% of the work lives. |
| **broward-lp** | `github.com/webseed50/broward-lp` | **Private** | Lead builder's Broward County *lis pendens* data pipeline (real-estate lead generation). Separate project in the MW ecosystem; owned/maintained by the lead builder. Limited detail on record here. |

Other MW repos exist (the CRM, websites, and marketing pipelines) but are **out
of scope for the books project** — the new account does not need access to any
of them.

**GitHub accounts:** `webkodiak` = Webster's personal account. `webseed50` =
the lead builder's account. Both repos are **private and must stay private** —
they contain account numbers, balances, EINs, and tax figures.

**How the new account gets access:** it cannot clone a private repo without
permission. Pick one:

1. **Add it as a collaborator** (preferred): on each repo, Settings →
   Collaborators → add the new account's GitHub username. It can then clone with
   its own login.
2. **Give it a fine-grained read token:** GitHub → Settings → Developer settings
   → Fine-grained tokens → scope to the specific repo(s), Contents: Read-only.
   Treat as a secret; short expiry; revoke when done.

Then: `git clone https://github.com/webkodiak/mw-books.git`

**Never commit credentials.** `.gitignore` already excludes
`simplefin_access.txt` and all raw feed pulls. Keep it that way.

## 3. Entities & tax profile

- **MW Financial LLC** (dba "MW LOANS") — Webster 100%. EIN 99-0597058. Files
  **1120-S** (S-corp). 2025 loss −$22,168. Accounts: Chase Bus Complete Chk
  ...2320, Chase Ink card ...2559.
- **MW Realty Group Corp** — Marisel 100%. S-corp since 2024-05-14. EIN
  99-3301962. Bank WF ...9114. K-1s: 2024 −$1,346; 2025 +$199,453.
- **Suncorps Construction Inc** — **C-corp**, files **1120**.
- **MW Development LLC** — bank WF ...8627. Tax treatment TBD (not in 2025
  returns).
- **KML Screen & Painting LLC** — tax treatment TBD.
- **Property Management Co** — tax treatment TBD.
- **Personal** — joint **1040**. Includes Marisel's separate REAL ESTATE AGENT
  Schedule C (subtree under Personal) and Webster's 2025 PROJECT MANAGER
  Schedule C (a one-off gig, not an LLC). M&T mortgage ...8801 = personal home
  (no rentals on Schedule E).
- **1099-NEC:** issue to any vendor paid ≥ $600.
- **2025 joint 1040:** total income $196,609; tax $36,658; payments $0.
- **CPA:** Amarilis. MW Books must produce clean, tax-ready packages per entity.

## 4. Users

Two logins; **every categorization records who made it** so disagreements are
visible and settleable.

- `webster` = Alfred Webster Clark Seed
- `marisel` ("Mary") = Marisel Cabrera Morono

## 5. Stack (do NOT rebuild an accounting engine)

- **Beancount v3** — plain-text, double-entry ledger, in git. The source of
  truth. (Ingestion + classification only.)
- **Fava** — open-source web UI for balance sheet, P&L, cash flow, drill-down.
  Reporting layer. Run: `fava main.beancount` → http://localhost:5000.
- **SimpleFIN Bridge** (~$15/yr) — read-only bank/card feed aggregation across
  ~30 accounts.
- **MW-UI** (`mw-ui/app.py`, Flask) — custom MW-branded app built in stages on
  top: two-user categorization, splitting commingled charges, the review queue,
  project budgets. v1 exists (review queue + entity/category filing).
- **Email** — enrichment only (receipts, invoices, Amazon itemization). Email
  *attaches context* to existing feed transactions; it NEVER creates ledger
  entries (double-counting risk).
- **Statement parsers** — for accounts that won't connect to SimpleFIN.
- Explicitly **NOT** QuickBooks / Plaid / Rocket Money.

## 6. Current state (what's done)

- Repo git-initialized, all work committed, pushed to `webkodiak/mw-books`.
  `bean-check main.beancount` passes.
- Books start date **2025-01-01** (Webster's call).
- **First ingestion complete: ~1,169 transactions** (2025-01-01 → present).
  Of these, 94 are auto-matched/cleared transfers (`*`) and ~1,075 are flagged
  (`!`) sitting in the review queue awaiting entity/category confirmation. 39
  cross-entity IOU legs recorded. Balance anchors + dedup state in place.
- Dedup key = SimpleFIN transaction id (`data/ingest_state.json`).
- **MW-UI v1** built: review queue + entity/category assignment + who-decided,
  on the real ledger, with IOU legs and transfer confirmation.
- Account inventory: `inventory/account-inventory.csv` (36 rows; 31 Beancount
  accounts opened with SimpleFIN ids as metadata). Regenerate via
  `tools/merge_inventory.py`.

## 7. Open flags — ASK Webster, do not guess

1. WF PLATINUM card ...4965 — whose? (new in feed)
2. Discover card "Alfred" ...6368 — whose? (new in feed)
3. Schwab futures ...104 — in scope or not?
4. Stripe — which entity receives payouts?
5. WF ...2443 appears **twice** in SimpleFIN (duplicate connection after
   reauth). Ingest ONLY `ACT-65e01920…`; ignore `ACT-3bd1adfa…`. Webster should
   delete the duplicate at the SimpleFIN bridge.
6. Tax treatment for MW Development, KML, Property Mgmt (not in 2025 returns).
7. Suncorps 1120 + MW Financial 1120-S — ask Webster to upload when handy.

**Excluded forever:** NewRez ...7885 (a customer's mortgage — only the refi
commission is MWFin income) and Mercury ("will not use going forward").

## 8. Environment facts (hard-won — don't rediscover)

- The AI sandbox **cannot reach SimpleFIN** (network blocked). Anything that
  hits SimpleFIN runs on **Webster's PC**: scripts live next to
  `simplefin_access.txt` in `%USERPROFILE%\Downloads`; Webster runs
  `python <script>.py` in cmd; outputs land in Downloads for the AI to read.
- Mounted folders for the AI: `C:\Users\webko\mw-books` and
  `C:\Users\webko\Downloads`. Home root is not mountable.
- The sandbox **can** reach `github.com` (git push/pull over HTTPS works) but
  **not** `api.github.com` (blocked) — so repo *creation* must be done by
  Webster in the browser/app; the AI can push once a repo exists and it has a
  token.
- Terminals/IDEs on the PC are view/click only — the AI can't type into them;
  it hands Webster runnable scripts (e.g. `RUN-MW-BOOKS.bat`) instead.
- `bean-check` isn't preinstalled in a fresh sandbox: `pip install beancount
  --break-system-packages`.

## 9. Next steps, in order

1. Work the review queue: confirm entity/category on the ~1,075 flagged txns
   (via MW-UI v1). Trusted patterns file automatically; uncertain → stay flagged.
2. Derive + confirm opening balances per account (current balance − txns back to
   2025-01-01); flag accounts whose feed history starts later than 2025-01-01.
   Webster confirms every number; nothing is locked yet.
3. Resolve the §7 open flags.
4. Statement parsers for gaps (Amazon store card, PayPal, pre-history months).
5. Email enrichment; agent classifier; multi-leg transfer matching (e.g. 3 Zelle
   sends = 1 payment).
6. Grow MW-UI: splitting commingled charges, project budgets w/ overage alerts.
   Fava stays the statements layer (brand later per `docs/branding.md`).
7. Tax-ready packages per entity for CPA Amarilis.

## 10. Standing rules (Webster's — non-negotiable)

- **Never guess silently** — uncertain → review queue.
- **Transfers/reimbursements are IOUs, not income/expense.** Money moves
  constantly between personal and business accounts; record as due-to/due-from
  and clear on payback. Booking them as revenue/expense would inflate P&Ls and
  distort taxes. Match multi-leg transfers into one move; track running
  reimbursement balances between the spouses and each company.
- **Entity = which account the money hit,** not what was bought.
- **Emails enrich, never create entries.** Dedup every pull (stable key +
  rolling re-pull window).
- **Money stays read-only — never move funds.**
- **Explain plainly** (Webster isn't a developer) and **do the work** rather than
  hand over scripts whenever the session can reach his files. Give **direct
  links** when asking him to visit a page.

## 11. How the new cloud account should start

1. Get repo access (§2) and `git clone` `mw-books`.
2. Read `docs/HANDOFF.md` (living log) — it overrides this file where newer.
3. Optionally paste §1–§5 and §10 of this file into the new project's custom
   instructions as the standing brief.
4. Ask Webster to connect the folder(s) so you can work on real files, and to
   run the SimpleFIN pull script on his PC when fresh data is needed.
