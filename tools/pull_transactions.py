#!/usr/bin/env python3
"""MW Books - pull ALL transactions since the books start date (2025-01-01).

Run from the folder that contains simplefin_access.txt (e.g. Downloads):
    python pull_transactions.py

Uses curl.exe (Cloudflare-safe, same as step0_v5). Read-only: only GETs data.
Writes simplefin_transactions.json next to this script, then prints how far
back each account's history actually reaches, so we know what needs
statement backfill to cover 2025.
"""
import datetime, json, os, shutil, subprocess, sys

START = "2025-01-01"
EPOCH = 1735689600  # 2025-01-01 00:00 UTC
HERE = os.path.dirname(os.path.abspath(__file__))
ACCESS_FILE = os.path.join(HERE, "simplefin_access.txt")
OUT = os.path.join(HERE, "simplefin_transactions.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def die(msg):
    print("\n" + "=" * 60 + "\n" + msg + "\n" + "=" * 60); sys.exit(1)

if not os.path.exists(ACCESS_FILE):
    die(f"simplefin_access.txt not found next to this script ({HERE}).")
access = open(ACCESS_FILE).read().strip()
scheme, rest = access.split("//", 1)
auth, host = rest.rsplit("@", 1)
url = f"{scheme}//{auth}@{host}/accounts?start-date={EPOCH}"

curl = shutil.which("curl") or shutil.which("curl.exe")
if not curl:
    die("curl not found - it ships with Windows 10/11; something is off.")

print(f"Pulling all transactions since {START} (can take a minute)...")
r = subprocess.run([curl, "-sS", "--max-time", "300", "-A", UA,
                    "-H", "Accept: application/json", "-o", OUT, url],
                   capture_output=True, text=True)
if r.returncode != 0:
    die(f"curl failed: {r.stderr[:300]}")
try:
    data = json.load(open(OUT, encoding="utf-8"))
except Exception as e:
    die(f"Response wasn't valid JSON ({e}) - copy this box to Claude.")

accts = data.get("accounts", [])
total = 0
print("\n" + "=" * 60)
print(f"SUCCESS - {len(accts)} account(s)")
print(f"{'account':38} {'txns':>5}  earliest txn")
for a in accts:
    txns = a.get("transactions", [])
    total += len(txns)
    earliest = (datetime.date.fromtimestamp(min(t["posted"] for t in txns))
                .isoformat() if txns else "-")
    name = f"{(a.get('org') or {}).get('name','?')}: {a.get('name','?')}"[:38]
    print(f"{name:38} {len(txns):>5}  {earliest}")
print(f"\nTOTAL: {total} transactions -> {OUT}")
for e in data.get("errors", []):
    print("  ! " + str(e))
print("=" * 60)
print("\nTell Claude: pull done")
