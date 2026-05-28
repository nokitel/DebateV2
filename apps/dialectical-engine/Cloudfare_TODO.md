# Cloudflare TODO For dezbatere.ro

The filename intentionally follows the requested spelling: `Cloudfare_TODO.md`.

Goal: use Cloudflare DNS plus Cloudflare Tunnel so `https://dezbatere.ro` and `https://www.dezbatere.ro` serve the app running on this Mac at `http://127.0.0.1:3000`.

## 1. Add The Domain To Cloudflare

1. Log in to Cloudflare.
2. Add a new site/domain: `dezbatere.ro`.
3. Choose the Free plan unless you intentionally want a paid Cloudflare plan.
4. Let Cloudflare scan existing DNS records.
5. Review imported records:
   - Keep existing records you recognize and still need.
   - If you use email on this domain, make sure MX/TXT/SPF/DKIM/DMARC records are present before changing nameservers.
   - If there is no hosting/email, it is okay if the DNS zone is mostly empty.
6. Cloudflare will show two assigned nameservers. Copy those exact two names.
7. Go to `Romarg_TODO.md` and change the Romarg nameservers to only those two Cloudflare nameservers. Do not leave any Romarg nameserver in an extra field.

Optional local helper after Cloudflare shows the two nameservers:

```sh
CLOUDFLARE_NAMESERVERS="first.ns.cloudflare.com second.ns.cloudflare.com" make prepare-romarg-nameservers
```

Replace the examples with the exact names Cloudflare shows. This writes
`Romarg_Nameservers_To_Set.md`, a short paste card for the Romarg form.

## 2. Wait For Cloudflare Activation

In Cloudflare, wait until the zone status for `dezbatere.ro` becomes active.

Local check:

```sh
dig +short dezbatere.ro NS
```

Or let the project wait and print the next command when ROTLD sees the
Cloudflare nameservers:

```sh
make wait-dezbatere-dns
```

Expected shape:

```text
<name>.ns.cloudflare.com.
<name>.ns.cloudflare.com.
```

## 3. Log In cloudflared On This Mac

Run this locally in a normal Terminal:

```sh
cloudflared tunnel login
```

This opens a browser. Choose the Cloudflare account and authorize `dezbatere.ro`.
You can also use the guided helper:

```sh
make interactive-manual-setup
```

Expected local file after success:

```text
~/.cloudflared/cert.pem
```

## 4. Create And Configure The Named Tunnel

From the project directory:

```sh
cd "/Users/stefannour/Documents/Debate V2/dialectical-engine"
make local-status
make hosting-status
make manual-setup-checklist
make resume-dezbatere-hosting
```

This helper will:

- stop with clear instructions if the local app status endpoint is not ready,
- stop with clear instructions if ROTLD still shows Romarg nameservers,
- stop with clear instructions if `cloudflared tunnel login` is not complete,
- create or reuse tunnel `dialectical`,
- route `dezbatere.ro` to the tunnel,
- route `www.dezbatere.ro` to the tunnel,
- write `~/.cloudflared/config.yml`,
- write `~/Library/LaunchAgents/com.dialectical.cloudflared.plist`.

The helper now refuses to create named DNS routes while `dezbatere.ro` still
delegates to Romarg or to a mixed nameserver set. Use
`SKIP_DNS_PREFLIGHT=1 make setup-dezbatere-tunnel` only if you intentionally
want to prepare the tunnel before the nameserver change is visible. The
lower-level setup script also checks
`http://127.0.0.1:3000/api/backends/status`; use `SKIP_SERVICE_PREFLIGHT=1`
only if you intentionally want to write tunnel config before the app is
reachable.

`make hosting-status` checks both the API and the web UI/static assets, so it
will catch a tunnel that reaches FastAPI but fails to serve the Next.js site.

## 5. Verify Before Installing The Service

Start the tunnel manually first:

```sh
cloudflared tunnel --config ~/.cloudflared/config.yml run dialectical
```

In another terminal:

```sh
curl -I https://dezbatere.ro/
curl https://dezbatere.ro/api/backends/status
curl -I https://www.dezbatere.ro/
```

Expected:

- `/` returns HTTP 200 or a redirect to HTTPS/200.
- `/api/backends/status` returns JSON with worker `mac-mini` advertising both
  `codex-gpt-5` and `lmstudio:google_gemma-4-e4b-it`.

## 6. Install The Named Tunnel As A Service

After manual verification:

```sh
INSTALL_SERVICE=1 STOP_QUICK_TUNNEL=1 make resume-dezbatere-hosting
```

Then check:

```sh
launchctl print gui/$(id -u)/com.dialectical.cloudflared
curl https://dezbatere.ro/api/backends/status
```

## 7. Final Local Checks

```sh
make local-status
make local-single-machine-acceptance
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib .venv313/bin/python scripts/status_report.py
```

Expected for the simplified phase:

- local coordinator ok,
- local web ok,
- `mac-mini` worker online with `codex-gpt-5`,
- some online local worker, normally `mac-mini`, has
  `lmstudio:google_gemma-4-e4b-it`,
- LM Studio server ok,
- `google_gemma-4-e4b-it` loaded,
- local routing includes `lmstudio:google_gemma-4-e4b-it`,
- public URL should eventually come from named tunnel, not quick tunnel.

## Current Blockers

- Cloudflare is not logged in on this Mac yet: `~/.cloudflared/cert.pem` is missing.
- The named tunnel service is not installed yet.
- The quick tunnel is still running until named tunnel verification succeeds.
- `dezbatere.ro` still delegates to Romarg nameservers, and the current Romarg
  authoritative DNS response is `REFUSED`; moving delegation to Cloudflare
  should fix public DNS once Cloudflare is active.

## Current Local Proof

The simplified local runtime is already working on this Mac:

- coordinator: `http://127.0.0.1:8000`
- web app: `http://127.0.0.1:3000`
- worker `mac-mini`: online with `codex-gpt-5` and
  `lmstudio:google_gemma-4-e4b-it`
- LM Studio has `google_gemma-4-e4b-it` loaded
- `make local-single-machine-acceptance` passes
