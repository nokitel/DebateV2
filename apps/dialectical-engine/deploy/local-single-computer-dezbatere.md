# Local Single-Computer Setup For dezbatere.ro

This is the simplified target while Worker B and final two-machine production
acceptance are deferred.

## Scope

- Run coordinator, web, and Worker A on this Mac.
- Use the existing SQLite database at `~/.dialectical/db.sqlite3`.
- Use local/public access through this Mac, not external hosting.
- Expose the site with a Cloudflare Tunnel when `dezbatere.ro` DNS is ready.
- Treat Worker B, physical failover, and two-worker production acceptance as
  deferred.

## Current Local State

- Coordinator listens on `http://127.0.0.1:8000`.
- Web proxy listens on `http://127.0.0.1:3000`.
- Worker `mac-mini` is online and currently advertises `codex-gpt-5` and
  native LM Studio capability `lmstudio:google_gemma-4-e4b-it`.
- Standalone worker `mac-mini-lmstudio` is stopped; it remains available as a
  fallback if the native LM Studio adapter is disabled later.
- Local routing is configured for `codex-gpt-5` plus
  `lmstudio:google_gemma-4-e4b-it`.
- The account-less quick tunnel currently exposes the app through
  `https://evaluations-postage-proceed-happiness.trycloudflare.com`.
- LM Studio is installed. The local server should run on
  `http://127.0.0.1:1234`.
- LM Studio has `google_gemma-4-e4b-it` loaded locally.
- `dezbatere.ro` is registered at Romarg and currently delegates to
  `ns1.romarg.com`, `ns2.romarg.com`, `ns3.romarg.com`, and `ns4.romarg.com`.
- Public DNS currently returns `SERVFAIL` because Romarg authoritative DNS
  returns `REFUSED` for the zone.
- The required local source paths are hydrated enough for the simplified local
  checks and worker restart path.

## Model Plan

Use these in order for the single-machine phase:

1. `codex-gpt-5` through the Codex CLI. This is currently proved
   non-interactive on this Mac.
2. Claude through Claude Code after running an interactive `claude auth login`.
3. Gemini CLI only if Google-account auth is configured. Prefer Google-account
   auth if it is covered by the user's current Google subscription; avoid
   `GEMINI_API_KEY` unless paid API usage is acceptable. The installed worker
   service sets `GOOGLE_GENAI_USE_GCA=true` so the Gemini CLI path stays on
   Google-account auth after OAuth is completed. The local probes and Gemini
   worker adapter also set the same environment flag.
4. LM Studio `google_gemma-4-e4b-it` through the local OpenAI-compatible server,
   preferably through the native worker adapter and with
   `scripts/lmstudio_worker.py` kept as a fallback.

The native LM Studio adapter is now the preferred simplified path because it
keeps Codex and local Gemma under the same `mac-mini` worker. The standalone
LM Studio worker remains as a fallback command, not the default runtime.

## Immediate Commands

Refresh every simplified setup report and rewrite `ManualSetup_TODO.md`:

```sh
make setup-status
```

Start the browser/account login flows from a normal Terminal:

```sh
make interactive-manual-setup
```

Create a clean source archive for repository import:

```sh
make source-snapshot
```

Check the simplified local state:

```sh
make local-status
```

Print only the concise current status and next manual actions without
refreshing the readiness report:

```sh
make local-next-steps
```

Run strict local-only acceptance:

```sh
make local-single-machine-acceptance
```

Configure the local-only model routing:

```sh
make configure-local-single-machine
```

After interactive Claude/Gemini login, enable whichever personal CLI models
actually work:

```sh
make refresh-local-models
```

To check Claude/Gemini auth without changing runtime routing:

```sh
make probe-model-auth
make local-next-steps
make manual-setup-checklist
```

The auth probe writes a separate report at
`/private/tmp/dialectical-model-auth-check.json`, so `make local-next-steps`
and `make manual-setup-checklist` can keep showing the latest detailed auth
reason even after `make local-status` refreshes the normal readiness report.

To check only the domain and Cloudflare Tunnel path:

```sh
make hosting-status
```

Run the standalone LM Studio fallback worker once, or continuously only if the
native adapter is disabled or failing:

```sh
make lmstudio-worker-once
make lmstudio-worker
```

Install the standalone LM Studio worker as a launchd service:

```sh
make install-lmstudio-worker
```

Verify one synthetic LM Studio job end to end:

```sh
make probe-lmstudio-job
```

Rebuild and restart the web service if static assets fail or after frontend edits:

```sh
make rebuild-web-service
```

Start LM Studio's local server if needed:

```sh
lms server start
lms ps
curl http://127.0.0.1:1234/v1/models
```

Probe the loaded Gemma model:

```sh
curl http://127.0.0.1:1234/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"google_gemma-4-e4b-it","messages":[{"role":"user","content":"Reply with exactly: ok"}],"temperature":0,"max_tokens":5}'
```

Log in Claude Code interactively:

```sh
claude auth login
claude -p --max-turns 1 'Reply with exactly: ok'
```

Configure Gemini CLI only if using Google-account auth:

```sh
make configure-gemini-google-auth
gemini
gemini -p 'Reply with exactly: ok'
```

Choose `Login with Google` in the interactive CLI if prompted. The CLI may
alternatively accept API-key or Vertex modes, but do not set `GEMINI_API_KEY`
for this simplified phase unless paid API usage is intended.

Model auth follow-up is tracked in `ModelAuth_TODO.md`.

## dezbatere.ro Hosting Path

The practical setup is Cloudflare Tunnel, not traditional hosting.

1. Add `dezbatere.ro` to Cloudflare.
2. At Romarg, change the domain nameservers from the current Romarg nameservers
   to the two Cloudflare nameservers assigned for the zone.
3. After Cloudflare shows the zone active, create a named tunnel on this Mac.
4. Route both `dezbatere.ro` and `www.dezbatere.ro` to the tunnel.
5. Point the tunnel service to `http://127.0.0.1:3000`.
6. Stop the current quick tunnel once the named tunnel is verified.

After the Cloudflare zone is active, run:

```sh
cloudflared tunnel login
make local-status
make resume-dezbatere-hosting
```

`make resume-dezbatere-hosting` is the preferred wrapper. It checks ROTLD
delegation, Cloudflare login, and the local web status endpoint first, then
calls the lower-level `make setup-dezbatere-tunnel` flow only when the
prerequisites are ready.

To install the named tunnel as launchd and stop the provisional quick tunnel:

```sh
INSTALL_SERVICE=1 STOP_QUICK_TUNNEL=1 make resume-dezbatere-hosting
```

For this app, the tunnel ingress should ultimately map:

```yaml
tunnel: dialectical
credentials-file: /Users/stefannour/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: dezbatere.ro
    service: http://127.0.0.1:3000
  - hostname: www.dezbatere.ro
    service: http://127.0.0.1:3000
  - service: http_status:404
```

## Remaining Blockers

- `dezbatere.ro` still needs to be added to Cloudflare and delegated from
  Romarg to the assigned Cloudflare nameservers.
- Cloudflare is not logged in on this Mac yet, so `~/.cloudflared/cert.pem` and
  the named tunnel config are still missing.
- Claude Code and Gemini CLI still need interactive account auth if you want to
  include them in the simplified local model pool without paid API keys.
