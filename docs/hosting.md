# Hosting — Webster's PC + Cloudflare Tunnel → books.mw.loans

Decision 2026-08-11 (Webster): Fava runs on his Windows machine; Cloudflare Tunnel
publishes it as `books.mw.loans`; Cloudflare Access is the login wall. The ledger
never leaves hardware he owns — Cloudflare only proxies the encrypted tunnel.

## One-time setup (on the PC, ~20 minutes)

1. **Install Python 3.12+** (python.org, check "Add to PATH"), then:
   `pip install beancount fava`
2. **Put the repo somewhere permanent**, e.g. `C:\Users\webko\mw-books`
   (sibling of the old mw-accounting repo). Unzip the scaffold there, or `git clone`
   once a remote exists.
3. **Test locally:** `fava C:\Users\webko\mw-books\main.beancount` → http://localhost:5000
4. **Install cloudflared** (winget: `winget install Cloudflare.cloudflared`), then:
   - `cloudflared tunnel login`  (browser opens; pick the mw.loans zone)
   - `cloudflared tunnel create mw-books`
   - `cloudflared tunnel route dns mw-books books.mw.loans`
   - Config file `%USERPROFILE%\.cloudflared\config.yml`:
     ```yaml
     tunnel: mw-books
     credentials-file: C:\Users\webko\.cloudflared\<tunnel-id>.json
     ingress:
       - hostname: books.mw.loans
         service: http://localhost:5000
       - service: http_status:404
     ```
   - `cloudflared service install`  (runs the tunnel as a Windows service, survives reboots)
5. **Lock the front door — Cloudflare Access** (Zero Trust dashboard → Access → Applications):
   - Add self-hosted app for `books.mw.loans`
   - Policy: Allow → emails: webster@mw.loans (add marisel/marine later, his call)
   - This is mandatory: Fava has NO authentication of its own. Do not route DNS to
     the tunnel before the Access policy exists.
6. **Fava as a startup task:** Task Scheduler → At log on →
   `pythonw -m fava C:\Users\webko\mw-books\main.beancount`
   (or a scheduled `fava` service via nssm if it should run before login).

## Notes

- The PC being off = books unreachable. Acceptable for a monthly-close discipline;
  revisit a VPS only if that starts to hurt.
- The nightly/weekly SimpleFIN pull (Step 1) will run on the same machine via Task
  Scheduler and commit to git — same box, same repo, no sync problem.
- Old `mw-accounting` Worker stays untouched; `books.mw.loans` is a new DNS record
  on the existing zone (this was the "wire on Webster's go" item — go given 2026-08-11).
