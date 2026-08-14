# MW Books — living handoff (updated 2026-08-14)

Start any new chat by reading this file. It supersedes older kickoff notes.

## Remote & phone access (added 2026-08-14)
- GitHub remote: **`github.com/webkodiak/mw-books`** — PRIVATE (holds account
  numbers, balances, EINs, tax figures; must never be public). `origin` on the
  PC points here; `main` tracks `origin/main`.
- Credentials are NEVER committed: `.gitignore` excludes `simplefin_access.txt`
  and all raw feed pulls. The push token was one-off (fine-grained, Contents R/W,
  scoped to this repo) and revoked after use — never stored in `.git/config`.
- Phone workflow: GitHub mobile app (sign in as webkodiak) to browse/read the
  ledger, review diffs, make small text edits. Browser editor: github.dev
  (open the repo, press `.`). Running Fava/the MW-UI from a phone would need a
  server (e.g. Codespaces) — future option, not set up yet.
- Still PC-only: SimpleFIN feed pulls (network + credentials live on Webster's
  PC). Phone is for review/reading/editing text, not pulling new bank data.

## Where the build stands
- Repo `C:\Users\webko\mw-books` IS the system of record, git-initialized, all
  work committed and pushed to GitHub (see Remote & phone access above).
  `bean-check main.beancount` passes.
- **Ledger-of-record ruling (Webster, 2026-08-14): MW Books supersedes the
  earlier "MW Group Accounting System"** — a Cloudflare Worker + D1 app
  (`mw-accounting`, deployed 2026-08-01, repo `C:\Users\webko\mw-accounting`)
  that was briefly stamped ledger of record, along with its Rocket-Money-feed
  plan. That app is retired from bookkeeping; nothing new gets built on it.
  If you encounter references to "mw-accounting" or a D1 accounting app,
  that's the superseded system, not this one.
- **mw-accounting TORN DOWN 2026-08-14** (Webster's order): Worker + D1 deleted
  from Cloudflare. Final export (1,724 txns, all personal cards, CSV/Rocket
  Money, 2026-01-01..2026-08-01): `data/d1-backup/` in this repo.
  **Cross-check run 2026-08-14:** 687 of 1,724 match this ledger; **1,037 do
  not, and ~96% of those fall BEFORE the SimpleFIN history start (~2026-05-18)**
  — i.e. the backup holds Jan→mid-May 2026 for ~12 personal accounts the feed
  never reached. That is the "pre-history months" half of Next-steps §5,
  pre-solved: ingest from `data/d1-backup/` (already normalized, even
  categorized) instead of parsing statements for those months. Unmatched rows:
  `inventory/d1-crosscheck-unmatched-2026-08-14.csv`.
  **BACKFILL INGESTED same day** via `tools/ingest_d1_backup.py` (re-runs are
  no-ops; D1 ids live in `data/ingest_state.json` alongside SimpleFIN ids):
  **935 entries** — 30 auto-matched transfer pairs (2 cross-entity with IOU
  legs, Personal→MWFin card payments on Chase-2559) + **905 to the review
  queue** (`#unreviewed #d1-backfill`, each carrying `d1_id` and the app's
  old category as `d1_category` — a hint for review, not a booking).
  `bean-check` clean. Review queue now ~1,980. Anchors: CapOne-9993 gained
  its pad; Amex-Hilton-1000's pad removed (history now complete from account
  opening — pad was unused). Caveats stand: nothing for 2025 (statements
  still needed there), business accounts not covered.
  **Flag cards RESOLVED same day (Webster: both his):** Discover-6368 and
  WF-Platinum-4965 opened under Personal, inventory rows OK'd, anchors
  added, and the remaining **72 rows ingested** on a re-run (all
  `#unreviewed #d1-backfill`; review queue now ~2,050). ⚠️ IMPORTANT for
  the next feed pull: these two accounts' FIRST SimpleFIN ingestion
  overlaps the backfill (May–Jul), so `ingest_simplefin.py` now carries a
  scoped guard (`D1_GUARDED_ACCTS`) that skips feed txns matching a
  `#d1-backfill` entry on those two accounts only (same amount, ±4 days)
  and records their feed ids in seen. Do not remove it before the first
  post-open pull has run.
- Books start date: **2025-01-01** (Webster's call). Opening balances: Claude
  derives from feed history, Webster confirms every number (nothing locked yet).
- Inventory: `inventory/account-inventory.csv` — 36 rows, final except 5 flags
  (see below). 31 Beancount accounts opened in entity files with simplefin IDs
  as metadata. Regenerate via `tools/merge_inventory.py`.
- Whenever the inventory changes: remind Webster to replace the copy in his
  project Context.

## Confirmed facts (don't re-ask)
- Users: webster = Alfred Webster Clark Seed; marisel ("Mary") = Marisel
  Cabrera Morono. Two logins, every categorization records who.
- MW Realty Group Corp: Marisel 100%, S-corp since 2024-05-14, EIN 99-3301962,
  bank WF ...9114. K-1s: 2024 −1,346; 2025 +199,453.
- MW Financial LLC (MW LOANS): Webster 100% (old "K-1 to Marisel" flag was a
  name mix-up). EIN 99-0597058, 2025 loss −22,168. Chase ...2320 + Ink ...2559.
- WF ...8627 = MW Development. M&T mortgage ...8801 = personal home (no
  rentals on Schedule E). Marisel has a separate REAL ESTATE AGENT Schedule C
  (subtree under Personal). Webster's 2025 PROJECT MANAGER Schedule C was a
  one-off gig (not an LLC).
- EXCLUDED forever: NewRez ...7885 (customer Asela Acosta's mortgage; only the
  refi commission is MWFin income) and Mercury ("will not use going forward").
- 2025 joint 1040: total income 196,609; tax 36,658; payments 0.

## Open flags (ask Webster)
1. ~~WF PLATINUM card ...4965 — whose?~~ **RESOLVED 2026-08-14, Webster's
   word: his.** Opened as `Liabilities:Personal:Card:WF-Platinum-4965`;
   D1 rows ingested.
2. ~~Discover card "Alfred" ...6368 — whose?~~ **RESOLVED 2026-08-14,
   Webster's word: his.** Opened as `Liabilities:Personal:Card:Discover-6368`;
   D1 rows ingested. (Carries the Anthropic/Real Geeks/HighLevel subs.)
3. Schwab futures ...104 — in scope or not?
4. Stripe — which entity receives payouts?
5. WF ...2443 appears TWICE in SimpleFIN (duplicate connection after reauth).
   Webster should delete the duplicate at the SimpleFIN bridge; ingestion must
   use only ACT-65e01920… and ignore ACT-3bd1adfa….
6. Tax treatment for MWDev, KML, PropMgmt (not in 2025 returns).
7. Suncorps 1120 + MWFin 1120-S: ask Webster to upload when handy.

## Environment facts (hard-won, don't rediscover)
- Claude's sandbox CANNOT reach SimpleFIN (network blocked) and terminals can't
  be typed into. Anything hitting SimpleFIN runs on Webster's PC: scripts live
  next to `simplefin_access.txt` in `%USERPROFILE%\Downloads`, Webster runs
  `python <script>.py` in cmd, outputs land in Downloads where Claude reads.
- Mounted folders: `C:\Users\webko\mw-books` and `C:\Users\webko\Downloads`.
  Home root is NOT mountable. File deletion needed one-time permission (granted).
- bean-check lives at `~/.local/bin/bean-check` in the sandbox.
- Chrome extension not connected. Tax return TXT extracts cached in sandbox
  /tmp (ephemeral).

## Next steps, in order
1. Webster runs `tools/pull_transactions.py` (copy in Downloads) → 
   `simplefin_transactions.json` (all txns since 2025-01-01 + history depth).
2. Ingest: normalize → dedup (stable key: simplefin txn id) → Beancount entries
   under per-entity monthly files; transfers/reimbursements as IOUs
   (due-to/due-from), NEVER income/expense. Skip duplicate WF-2443 feed ID.
3. Derive opening balances per account (current balance − txns back to
   2025-01-01); flag accounts whose history starts later; Webster confirms all.
4. UI v1 (Webster wants ASAP, real data first): review queue + entity/category
   assignment + who-decided, on the real ledger. Then splitting, budgets.
   Fava stays the statements layer (brand later per docs/branding.md).
5. Statement parsers for gaps (Amazon store card, PayPal, pre-history months).
6. Email enrichment; agent classifier; transfer matching (multi-leg Zelle).

## Standing rules (Webster's, non-negotiable)
- Never guess silently — uncertain → review queue. Never book transfers as
  income/expense. Money stays read-only. Explain plainly (not a developer).
- Entity assignment = which account the money hit, not what was bought.
- Emails enrich, never create entries. Dedup every pull.
