# Importers — gated on Step 0

Nothing here gets designed until the connectivity survey exists
(`inventory/account-inventory.csv` with a connects? verdict per account).

Planned, in order:

1. `simplefin_pull.py` — SimpleFIN Bridge → normalized records → Beancount entries.
   Dedup: stable key (account + posted date + amount + fingerprint of description)
   + rolling re-pull window (Broward pipeline pattern). Idempotent by construction.
2. `statements/` — one parser per ISSUER (Synchrony, Citi, …), not per brand.
   Statement close balance = the reconciliation proof for the month.
3. `email_enrich.py` — attaches receipt emails to EXISTING entries.
   Match on amount + date + merchant; one email may match MANY charges.
   Never creates a transaction.
4. PayPal: own transaction API, solved independently of SimpleFIN.
5. Amazon line items: Privacy Center data request → `Retail.OrderHistory` (manual,
   CSV export was killed 3/2023). Use Amazon Business reporting instead if one exists.
