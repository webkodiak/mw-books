#!/usr/bin/env python3
"""MW Books - walk BACKWARD in 90-day windows to fetch history to 2025-01-01.

SimpleFIN capped our first pull at 90 days. This script requests each 90-day
window separately (2025-01-01 ... 2026-05-17) and merges everything into
simplefin_backfill.json. Institutions keep different amounts of history; the
summary shows exactly how far back each account really goes.

Run from the folder containing simplefin_access.txt:
    python pull_backfill.py
"""
import datetime, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ACCESS_FILE = os.path.join(HERE, "simplefin_access.txt")
OUT = os.path.join(HERE, "simplefin_backfill.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
START = datetime.date(2025, 1, 1)
STOP = datetime.date(2026, 5, 18)   # first pull already covers from here
WINDOW = 85                          # stay safely under the 90-day cap

def die(m): print("\n" + m); sys.exit(1)
if not os.path.exists(ACCESS_FILE): die("simplefin_access.txt not found here.")
access = open(ACCESS_FILE).read().strip()
scheme, rest = access.split("//", 1); auth, host = rest.rsplit("@", 1)
curl = shutil.which("curl") or shutil.which("curl.exe")
if not curl: die("curl not found.")

def epoch(d): return int(time.mktime(d.timetuple()))

merged = {}          # account id -> account dict with merged txn dict
txn_ids = set()
win_start = START
n = 0
while win_start < STOP:
    win_end = min(win_start + datetime.timedelta(days=WINDOW), STOP)
    n += 1
    url = (f"{scheme}//{auth}@{host}/accounts?start-date={epoch(win_start)}"
           f"&end-date={epoch(win_end)}")
    print(f"window {n}: {win_start} .. {win_end} ...", end=" ", flush=True)
    r = subprocess.run([curl, "-sS", "--max-time", "300", "-A", UA,
                        "-H", "Accept: application/json", url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("curl error:", r.stderr[:200]); win_start = win_end; continue
    try:
        data = json.loads(r.stdout)
    except Exception:
        print("bad response:", r.stdout[:120]); win_start = win_end; continue
    got = 0
    for a in data.get("accounts", []):
        acc = merged.setdefault(a["id"], {**{k: v for k, v in a.items()
                                             if k != "transactions"},
                                          "transactions": []})
        for t in a.get("transactions", []):
            if t["id"] not in txn_ids:
                txn_ids.add(t["id"])
                acc["transactions"].append(t)
                got += 1
    errs = data.get("errors", [])
    print(f"{got} new txns" + (f"  (note: {errs})" if errs else ""))
    win_start = win_end

json.dump({"accounts": list(merged.values()), "errors": []},
          open(OUT, "w"), indent=1)
print("\n" + "=" * 60)
print(f"{'account':40} {'txns':>5}  earliest")
for a in sorted(merged.values(), key=lambda x: (x.get('org') or {}).get('name', '')):
    t = a["transactions"]
    e = (datetime.date.fromtimestamp(min(x["posted"] for x in t)).isoformat()
         if t else "-")
    print(f"{((a.get('org') or {}).get('name','?')+': '+a.get('name','?'))[:40]:40} {len(t):>5}  {e}")
print(f"TOTAL {len(txn_ids)} transactions -> {OUT}")
print("=" * 60 + "\nTell Claude: backfill done")
