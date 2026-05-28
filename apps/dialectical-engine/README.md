# Dialectical Engine

Local-first debate generation platform. A FastAPI coordinator owns SQLite state, local workers pull jobs and use installed model CLIs/API backends, and a Next.js UI renders public debate trees with token-gated write/admin operations.

## Layout

- `coordinator/`: FastAPI app, SQLite/SQLAlchemy models, orchestration, routing, SSE, REST APIs.
- `worker/`: long-polling local worker, capability detection, CLI/API/Ollama/mock adapters.
- `web/`: Next.js app with public debate list/detail and auth-gated new/settings/workers pages.
- `deploy/`: Cloudflare Tunnel and launchd templates.
- `scripts/`: dev runner and worker registration helpers.

## First Local Run

```bash
cd dialectical-engine
make bootstrap
make dev
```

On first coordinator boot the user bearer token is printed once. Paste it into `/new`, `/settings`, or `/admin/workers`. Local development enables the `mock-local` adapter so a full debate can complete without paid model CLIs.
`make dev` sets `DIALECTICAL_ENABLE_REAL_ADAPTERS=0` for Worker A by default; set it to `1` when you explicitly want local CLI/API adapters involved.
For isolated smoke runs, `DIALECTICAL_DEV_COORDINATOR_PORT`, `DIALECTICAL_DEV_WEB_PORT`, and `DIALECTICAL_DEV_NEXT_PORT` can override the default ports without changing the normal `make dev` topology.
`DIALECTICAL_DEV_HOME` can point the dev SQLite database and Worker A config at a temporary directory for isolated checks.
Set `DIALECTICAL_DEV_NEXT_MODE=start` to run the web proxy against a built Next upstream instead of `next dev`; `make dev-smoke` uses that mode with an isolated `.next-dev-smoke` build, verifies coordinator/web/Next/Worker A on temporary ports, and writes `/private/tmp/dialectical-dev-smoke.json`.

Services:

- Coordinator: `http://localhost:8000`
- Web UI: `http://localhost:3000` (source-controlled proxy: UI on `:3001`, same-origin `/api/*` to coordinator)
- Worker A: started by `make dev`

## Worker B

On the adesso MacBook:

```bash
cd dialectical-engine
make bootstrap
make install-worker COORDINATOR_URL=https://debate.<your-domain> WORKER_NAME=adesso-mbp
```

The script reads the user token from `DIALECTICAL_USER_TOKEN` or `USER_TOKEN`, or prompts only when a new worker registration is needed. It calls `/api/workers/register`, stores the returned worker token in `~/.dialectical-worker/config.toml`, verifies the worker can heartbeat, and installs a user launchd service for the worker. If a real `GEMINI_API_KEY` or `XAI_API_KEY` is set when `make install-worker` runs, the generated launchd service includes that API key in the worker environment; placeholder values such as `<optional-...>` are ignored. Rerun `make install-worker` after changing these keys so launchd picks them up. When the saved worker config already matches the worker name and coordinator URL, the rerun reuses the stored worker token without prompting for the user token; omitting `ALLOWED_MODELS` preserves the saved allowlist, while `ALLOWED_MODELS=` intentionally clears it. Noninteractive first-time registrations still need `DIALECTICAL_USER_TOKEN` or `USER_TOKEN`.
Production worker registration does not advertise `mock-local` unless you pass `--enable-mock`.
Set `DIALECTICAL_ALLOWED_MODELS=codex-gpt-5` or pass `--allowed-models codex-gpt-5` when installed Claude/Gemini CLIs should remain hidden until unattended auth is proved. The generated Worker B onboarding script uses that safe `codex-gpt-5` pin by default and verifies the worker advertises it; pass `ALLOWED_MODELS=` only when you intentionally want to clear the pin. If `GEMINI_API_KEY` is set, the worker can advertise `gemini-2.5-pro` through the Gemini API without relying on Gemini CLI auth, and that API path takes precedence over the CLI for the same model. If no healthy adapter matches the allowlist, worker registration stops before saving config or updating the coordinator.
For final different-model production proof, configure both workers with the same two-real-model allowlist after the second model key is available. The Worker B onboarding bundle includes `configure_worker_b_real_models.sh`; run it on the adesso MacBook with `ALLOWED_MODELS=codex-gpt-5,gemini-2.5-pro` and a real `GEMINI_API_KEY`. The consolidated handoff bundle includes `configure_worker_a_real_models.sh`; run it on the Mac mini with the same allowlist and API key, then run the final acceptance sequence. It defaults `WORKER_REQUIRED_CAPABILITIES` to `codex-gpt-5,gemini-2.5-pro`.
After moving from a quick Cloudflare URL to a named tunnel hostname, update Worker B through the onboarding bundle so the named endpoint is verified before config changes:

```bash
NEW_COORDINATOR_URL=https://debate.<your-domain> \
ALLOWED_MODELS=codex-gpt-5 \
ENGINE_DIR=/path/to/dialectical-engine \
./switch_worker_b_url.sh
```

That helper preserves the stored worker token in `~/.dialectical-worker/config.toml` and omits `ALLOWED_MODELS` if you want to preserve the current allowlist unchanged.
Pass `ALLOWED_MODELS=` explicitly to clear the allowlist and advertise all detected healthy adapters.
Use `WORKER_REQUIRE_NAMED_HTTPS=1` when switching Worker B to the final named Cloudflare hostname so placeholder, local, and `trycloudflare.com` URLs are rejected before the config is changed. The generated Worker B `switch_worker_b_url.sh` sets this flag automatically.

## Tests

```bash
make test
```

The test target enforces at least 70% coverage across `coordinator/app/services` and `worker/app/adapters`.

## Acceptance Check

After the Mac mini services and at least one worker are online, run:

```bash
make acceptance COORDINATOR_URL=https://debate.<your-domain> EXPECTED_WORKERS=2 EXPECTED_WORKER_NAMES=mac-mini,adesso-mbp
```

The target prompts for the user token with terminal echo disabled unless `USER_TOKEN` is already set in the environment.
For the final two-worker production check, add `REQUIRE_WORKERS_IN_TREE=1 REQUIRE_DIFFERENT_REGEN_MODEL=1 ACCEPTANCE_REQUIRE_NAMED_HTTPS=1`. The checker verifies structured public archive API and web-home evidence, auth-gated web prompts, token-flow source contracts, post-unlock source surfaces, debate regenerate/history action-control source contracts, browser SSE streaming-client source contracts, structured worker-status payload counts and rows with timezone-aware `last_seen`, timezone-aware public-list/create/synthesis/history timestamps, structured debate lifecycle evidence for create/skeleton/role-override/timing/persistence checks, structured auth-boundary evidence for public-read/auth-write rejection checks, structured authenticated settings evidence with per-model spend/cap round-trips, auth writes, tree skeleton timing, structured SSE event/token/order evidence including replay-history mode, initial `tree_ready` payloads, completion with synthesis, structured online/offline worker rows with IDs, generated/regenerated node metadata, worker names, and model IDs, authenticated regenerate-request job evidence, regeneration history, regeneration model switching tied to archived/active history, markdown export, named HTTPS URL class, and URL persistence.
If only one safe real model is enabled, a rehearsal run can use `REQUIRE_DIFFERENT_REGEN_MODEL=0` only with `ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL=1`; `make status` will not treat that as final production proof.
For the physical failover check, pass `EXPECTED_WORKERS=1 EXPECTED_WORKER_NAMES=mac-mini EXPECTED_OFFLINE_WORKER_NAMES=adesso-mbp` after sleeping or powering off the MacBook, so the report proves Worker B was registered and is offline rather than merely absent.
When checking split local services instead of the Cloudflare same-origin host, pass `WEB_URL=http://localhost:3000`.

To prove the two-worker scheduler and one-worker failover path locally without the MacBook/tunnel, run:

```bash
make local-cluster-check
```

It starts a temporary coordinator plus two mock workers, requires both workers to generate nodes, stops the second worker, verifies a new debate completes with the remaining worker, restarts the second worker, and requires both workers to generate nodes again. It then restarts the coordinator against the same SQLite database, verifies a completed debate detail is unchanged after restart, and runs a dedicated retryable failure probe that proves `node_failed` SSE payloads are emitted, the failed worker is visible as degraded with `current_job_id` cleared, and the failed node is requeued.
The `make local-cluster-check` target builds the Next production app before starting the temporary web proxy, so the proof is reproducible from a clean checkout without relying on a pre-existing `.next` directory.
The local cluster uses two named mock model IDs so the acceptance checker also requires regeneration to switch models without needing paid CLI auth.
Each phase writes a durable JSON report under `/private/tmp/dialectical-local-cluster-*.json`, including the current-job, in-flight failover, restart-persistence, and node-failure SSE probes. `make status` summarizes those reports separately from production acceptance reports.

## Deployment Notes

For the simplified single-Mac `dezbatere.ro` setup, use
`deploy/local-single-computer-dezbatere.md` as the runbook and run:

```bash
make setup-status
```

That refreshes the local readiness report, Claude/Codex/Gemini auth probes,
Cloudflare/Romarg hosting status, `ManualSetup_TODO.md`, and the concise next
actions. The requested Romarg and Cloudflare manual checklists are
`Romarg_TODO.md` and `Cloudfare_TODO.md`; `Cloudflare_TODO.md` is a spelling
alias that points back to the requested filename.
After Cloudflare assigns the two nameservers, run
`CLOUDFLARE_NAMESERVERS="first.ns.cloudflare.com second.ns.cloudflare.com" make prepare-romarg-nameservers`
with the real values to write `Romarg_Nameservers_To_Set.md` for the Romarg
form.
Run `make interactive-manual-setup` from a normal Terminal to start the Claude,
Gemini Google-account, and Cloudflare browser login flows; it refuses to run in
non-interactive automation. After Claude/Gemini login, accept its local model
routing refresh so the worker advertises newly usable personal models. After
Cloudflare login and DNS delegation are ready, accept its named tunnel setup
prompt to continue into `make resume-dezbatere-hosting`.
The remaining manual gates are also tracked in
`https://github.com/DebateAIRO/debateairo/issues/5`.
Because this local `dialectical-engine` directory is not currently a git
checkout, run `make source-snapshot` to create a clean archive for repository
import. See `RepoHandoff_TODO.md`.

Run `make deploy-preflight DEPLOY_ROLE=both` before the first production launch. Use `PREFLIGHT_FLAGS="--require-installed-services --require-registered-worker"` after installing launchd services and registering the worker to verify the machine is actually ready for acceptance. Mac mini preflight verifies the named `cloudflared` launchd service uses `~/.cloudflared/config.yml` and runs the same tunnel declared in that config. Worker preflight reports whether the installed worker launchd service contains `GEMINI_API_KEY` and `XAI_API_KEY`; a WARN for a key you expect means rerun `make install-worker` with that key in the environment. If preflight reports an old `user_token` in `~/.dialectical-worker/config.toml`, rerun with `PREFLIGHT_FLAGS="--repair-worker-config"` to remove only that stale key while preserving the worker token.
Adapter checks in preflight only prove that model invocation commands, credentials, or local services are present. API credential checks count real keys from the current shell or from the installed worker launchd environment and ignore placeholder values. They do not run paid model prompts or prove unattended CLI auth; prove enabled models with `make acceptance` before routing production debates to them. Grok CLI is only counted when `grok --help` advertises noninteractive `-p`/`--prompt` mode; otherwise set `XAI_API_KEY` to use the xAI API fallback. Set `GEMINI_API_KEY` to use the Gemini API-backed `gemini-2.5-pro` adapter as the second real-model path. `make status STATUS_FLAGS=--strict-production` also checks source invariants for the Claude, Codex, Grok, Ollama, Gemini, and xAI adapter contracts before accepting final production status.

Use `make status STATUS_FLAGS=--check-endpoints` for a compact runtime report covering launchd services, named `cloudflared` plist/config/tunnel alignment, the public URL, local/public read endpoints, prompt-safety source invariants, worker retry/stream resilience source invariants, API adapter source invariants, the audit artifact, and Worker B bundle. With endpoint checks enabled, the command exits nonzero if any checked endpoint, export, or web route fails.
Use `make status STATUS_FLAGS=--strict-production` as the final handoff gate after the named tunnel, Worker B onboarding, local proof refresh, and all three production acceptance phases are complete. Strict production mode also runs endpoint checks and exits nonzero while the runtime is still on a quick tunnel, prompt safety is stale, worker retry/stream resilience is stale, API adapter support is stale, local proof artifacts are stale, required bundles are stale, production acceptance reports are missing/stale/incomplete, a production or local proof report contains token-looking user/worker values, a production report has generic or stale result details for the web auth/token-flow, SSE, regeneration, markdown export, or persistence checks, has stale failure metadata, lacks ordered timezone-aware timestamps or a UUID `debate_id` matching the create/persistence result details, lacks structured public archive API and web-home evidence, structured worker-status payload evidence for `/api/backends/status` counts and rows, structured debate lifecycle evidence for create/skeleton/role-override/timing/persistence checks, structured auth-boundary evidence for public-read/auth-write rejection checks, structured settings round-trip evidence for per-model spend/cap persistence and restoration, structured web-auth gate evidence for the protected pages, structured web-auth token-flow evidence for AuthGate/API client source contracts, structured post-unlock web surface evidence for the protected pages, structured debate-action source evidence for regenerate/history controls and API calls, structured streaming-client source evidence for SSE rendering, reconnect, refresh, and model color markers, structured SSE evidence for required initial/regenerated event types, token counts, event-sequence ordering, initial replay-history mode, regenerated live-only mode, initial `tree_ready` root/child IDs, and start/completion payloads, structured generated/regenerated node metadata evidence for active argument generations, structured initial/regenerated synthesis evidence with debate IDs, timestamps, observed worker names, and persisted regenerated synthesis ID, structured regenerate-request evidence for queued job and previous generation/synthesis IDs, structured regeneration-history evidence for archived/active generations with argument, latency, and token metadata, structured web-debate detail evidence for the public debate page, structured markdown-export evidence for headers, sections, workers, models, and history counts, structured online/offline worker rows with IDs, capabilities, timezone-aware `last_seen`, and `current_job_id`, stable worker IDs across the two-worker, failover, and rejoin production phases, sequential production phase timestamps from two-worker to failover to rejoin, distinct debate IDs across the three production phases, generated/regenerated worker and model ID fields, aggregate observed worker/model fields and recorded result detail/evidence matching that detailed evidence, the exact expected worker names for the phase, a structured real `old -> new` regeneration model switch that matches archived/active generation history, or a production report observes local worker names, unexpected worker names, mock model IDs, placeholder model IDs, missing required worker capabilities, or expected-offline workers in online/generated/regenerated evidence.
The handoff bundle's `final_production_check.sh` also fails before refreshing local proof if any of the three production acceptance reports is missing from `/private/tmp` or if `ACCEPTANCE_REPORT_DIR` points elsewhere without `ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR=1`; nonstandard report directories are rehearsal-only because strict status reads `/private/tmp`, so they also require `REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS=0` with `ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL=1` before proof refresh. It runs `make test` after deploy preflight so the coordinator/services and worker/adapters coverage gates are part of the final handoff path. Skipping its local proof refresh also requires pairing `REFRESH_LOCAL_PROOF=0` with `ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL=1` and is only for rehearsal runs.
Use `make handoff-bundles PUBLIC_URL=https://debate.<your-domain>` to generate credentials-free Worker B onboarding, named-tunnel, and consolidated handoff bundles under `/private/tmp`. The Makefile also exposes `make production-readiness`, `make production-acceptance-sequence`, and `make final-production-check`; each target unpacks `HANDOFF_ARCHIVE` (defaulting to today's `/private/tmp/dialectical-v2-handoff-YYYY-MM-DD.tgz`) and runs the matching handoff script with `ENGINE_DIR` set to the current checkout.
The Worker B onboarding bundle includes `production_acceptance.sh` for the two-worker, one-worker failover, and Worker B rejoin acceptance phases. It waits for both workers to be online before two-worker/rejoin phases, waits for Worker B to be offline before the failover phase, and requires a passed two-worker report before failover plus a passed failover report before rejoin. The helper parses those prior reports and rejects stale phase, URL, web/SSE, or named-HTTPS/different-model proof that does not match the current run's requirements before prompting for the user token. After each run, it validates the report it just wrote before printing success.
Skipping the standalone Worker B strict report validator requires pairing `SKIP_STRICT_REPORT_VALIDATION=1` with `ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1` and is only for rehearsal runs. Standalone quick-tunnel, one-model, or nonstandard report-directory rehearsals must set those strict-validation skip flags before the token prompt.
For final production proof, run those three helper phases from the Mac mini so the reports land under `/private/tmp` where strict status reads them. If a phase is run elsewhere, copy its JSON report to the same `/private/tmp/dialectical-acceptance-*.json` path on the Mac mini before the next phase and before final strict status.
The consolidated handoff bundle includes `production_readiness.sh`, a token-free pre-acceptance gate. Run it after the named tunnel is live and both workers are configured, either from the extracted handoff bundle or with `make production-readiness`; it verifies the named public endpoint, requires the temporary quick tunnel to be stopped, runs deploy preflight and endpoint status, requires launchd API keys for API-backed final models on the Mac mini worker, and checks both `mac-mini` and `adesso-mbp` advertise the final real-model capabilities before `production_acceptance_sequence.sh` asks for the user token. Skipping readiness deploy preflight or endpoint status requires pairing `RUN_PREFLIGHT=0` or `RUN_ENDPOINT_STATUS=0` with the matching `ALLOW_SKIP_*_FOR_REHEARSAL=1` flag and is only for rehearsal runs; in the consolidated sequence, either skip also requires the strict-report-validation and final-check rehearsal skip flags before the token prompt.
Before readiness and the token prompt, `production_acceptance_sequence.sh` also unpacks the embedded Worker B bundle and asks the bundled status helper to validate the full onboarding bundle against the resolved public URL, including shell syntax, endpoint verifier freshness, registration and real-model setup guards, switch helper, report-locality guidance, and strict acceptance helper contract. Any consolidated quick-tunnel or one-model rehearsal must set `SKIP_STRICT_REPORT_VALIDATION=1`, `ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1`, `FINAL_CHECK_AFTER_ACCEPTANCE=0`, and `ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1` before the token prompt; quick-tunnel rehearsals must also skip readiness with the matching rehearsal flag.
The sequence writes final production reports to `/private/tmp`, which is the directory strict status reads; overriding `ACCEPTANCE_REPORT_DIR` requires `ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR=1`, `SKIP_STRICT_REPORT_VALIDATION=1`, `ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1`, `FINAL_CHECK_AFTER_ACCEPTANCE=0`, and `ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1` before the token prompt, and is only for rehearsal runs.
The helper rejects placeholder, non-HTTPS, local, and `trycloudflare.com` quick-tunnel URLs by default and passes `ACCEPTANCE_REQUIRE_NAMED_HTTPS=1` into `make acceptance`; set `ALLOW_QUICK_TUNNEL_ACCEPTANCE=1` only for an explicit provisional quick-tunnel smoke run. In the consolidated sequence, quick-tunnel smoke also requires `RUN_READINESS_CHECK=0` with `ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL=1` and `FINAL_CHECK_AFTER_ACCEPTANCE=0` with `ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1`. Final production acceptance must use the named Cloudflare hostname.
The standalone Worker B `production_acceptance.sh` helper, Worker B env example, and consolidated Mac mini `production_acceptance_sequence.sh` default `WORKER_REQUIRED_CAPABILITIES` to `codex-gpt-5,gemini-2.5-pro` for final different-model proof and reject placeholder, mock, duplicate, or single-model capability lists before prompting for the user token. During the failover phase the standalone helper also requires the expected-offline Worker B status row to retain the required capabilities, proving the offline row is the registered production worker rather than an empty placeholder. After `GEMINI_API_KEY` is configured on both workers and `ALLOWED_MODELS=codex-gpt-5,gemini-2.5-pro` is applied, run the final sequence without overriding that default unless the final real-model pair changes. `REQUIRE_DIFFERENT_REGEN_MODEL=1` is the default for final production proof; setting it to `0` also requires `ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL=1` and is only for rehearsal runs while a second real model is still being configured. One-model sequence rehearsals also need the strict report-validation skip flags and final-check skip flags, because final strict status rejects those reports.

1. Install and start the Cloudflare Tunnel service with `make setup-named-tunnel TUNNEL_NAME=dialectical TUNNEL_HOSTNAME=debate.<your-domain>`. The helper runs `cloudflared tunnel login` if needed, runs `cloudflared tunnel create` when credentials do not exist, calls `make install-tunnel`, then runs deploy preflight, endpoint status, and `make handoff-bundles PUBLIC_URL=https://debate.<your-domain>` so Worker B and handoff archives carry the named URL. If `~/.cloudflared` contains exactly one tunnel credentials JSON with `AccountTag`, UUID-shaped `TunnelID`, and `TunnelSecret`, the installer uses it automatically; otherwise pass `CLOUDFLARED_CREDENTIALS=$HOME/.cloudflared/<tunnel-id>.json`. `TUNNEL_NAME` must be a real Cloudflare tunnel name or UUID, and `TUNNEL_HOSTNAME` must be a DNS hostname, not a URL or `trycloudflare.com` quick tunnel host. The helper refuses to refresh handoff bundles or stop the quick tunnel when endpoint status or deploy preflight is skipped unless the handoff refresh is explicitly marked unverified. By default it stops the quick tunnel after the named endpoint check succeeds; set `STOP_QUICK_TUNNEL_AFTER_VERIFY=0` only when you intentionally need to keep the provisional quick tunnel alive.
2. Install Mac mini coordinator/web services with `make install-services`.
3. Register Worker A on the Mac mini with `make install-worker COORDINATOR_URL=http://localhost:8000 WORKER_NAME=mac-mini`.
4. After the named tunnel is verified, run `make stop-quick-tunnel` on the Mac mini if the setup helper did not already stop it, so final status no longer resolves the public URL from a temporary quick-tunnel log.
5. Start Worker B from the MacBook with the public HTTPS coordinator URL. The Worker B bundle verifies the token-free `/api/backends/status` endpoint before prompting for a token or switching Worker B to a named URL. If it was first registered against a quick tunnel, use the bundle's `switch_worker_b_url.sh` after the named tunnel is live so the endpoint is checked before the worker config changes.
6. Configure both workers for final different-model proof with `ALLOWED_MODELS=codex-gpt-5,gemini-2.5-pro` and the real `GEMINI_API_KEY`, using the Worker B bundle's `configure_worker_b_real_models.sh` on the MacBook and the handoff bundle's `configure_worker_a_real_models.sh` on the Mac mini.
7. Run the handoff bundle's `production_readiness.sh` on the Mac mini before starting the final acceptance sequence.

The tunnel routes `/api/*` to FastAPI on `:8000` and all other paths to the web service on `:3000`.
The installed web service also proxies same-origin API, OpenAPI, docs, and SSE routes to FastAPI while serving Next.js from an internal `:3001` upstream, so quick tunnels and local browser sessions can use one origin. Coordinator SSE streams keep a bounded per-debate event history, so subscribers and reconnecting clients receive the recent ordered event prefix before live events.
The web client uses same-origin API calls in the browser by default, so a public tunnel host works without baking a domain into the Next.js bundle. Set `NEXT_PUBLIC_API_BASE` only when the web UI and coordinator are intentionally served from different origins.

Public reads require no token. Writes, settings, and admin pages use the user bearer token stored in browser `localStorage`. Worker calls use per-worker bearer tokens stored in `~/.dialectical-worker/config.toml`.
