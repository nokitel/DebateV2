# /goal — Dialectical Engine

## What it is

A web platform where the user posts a debate topic, and workers running on the user's local machines pull open debate nodes from the coordinator and use the user's subscription LLMs to generate arguments. The result is a Kialo-style argument tree where each pro/con node is written by a different model, with auto-synthesis at the end. The website is public read; the user authenticates to post topics or regenerate nodes.

## Topology

```
   ┌─────────────────────────────────────────────┐
   │  Mac mini @ home (always on)                │
   │                                             │
   │  ┌──────────────────────────────────────┐   │
   │  │ Coordinator (FastAPI :8000)          │◄──┼───┐
   │  │ Web UI (Next.js :3000)               │   │   │
   │  │ SQLite at ~/.dialectical/db.sqlite3  │   │   │
   │  └──────────────────────────────────────┘   │   │
   │  ┌──────────────────────────────────────┐   │   │
   │  │ Worker A (local, localhost client)   │───┼───┘
   │  │   Claude / Codex / Gemini / Grok     │   │
   │  │   CLIs + Ollama on this machine      │   │
   │  └──────────────────────────────────────┘   │
   └────────────────┬────────────────────────────┘
                    │ Cloudflare Tunnel (HTTPS)
                    ▼
   https://debate.<your-domain>   ◄── public read, auth write
                    ▲
                    │ pull API (worker bearer token)
                    │
   ┌────────────────┴────────────────────────────┐
   │  adesso MacBook Pro (mobile)                │
   │  ┌──────────────────────────────────────┐   │
   │  │ Worker B                             │   │
   │  │   same adapter stack as Worker A     │   │
   │  └──────────────────────────────────────┘   │
   └─────────────────────────────────────────────┘
```

- Coordinator + UI live on the Mac mini, exposed publicly via Cloudflare Tunnel.
- Worker A runs on the Mac mini (localhost client to coordinator).
- Worker B runs on the adesso MacBook (talks over HTTPS through the tunnel).
- Workers don't share state; coordinator is the single source of truth.
- Reads (browse debates) are public, no auth. Writes (post topic, regenerate node, change settings) require the user bearer token.

## Components

### Coordinator (Python 3.12 + FastAPI on Mac mini)
- Owns SQLite database.
- Accepts new debates, expands the tree, schedules jobs.
- All routing decisions (which role → which model) happen here.
- Does NOT call any LLM directly; workers do all inference.
- Exposes pull API for workers, SSE for the web UI, REST for the user.
- Serves the Next.js app as static export on `:3000` (or proxied behind the same FastAPI port).

### Worker (Python 3.12, one process per machine)
- Registers with coordinator on startup, advertises capabilities (which model paths are installed and reachable locally).
- Long-polls the coordinator for jobs (30s).
- For each claimed job, invokes the assigned local backend, streams token deltas back to the coordinator over chunked HTTP POST, and posts the final result.
- Heartbeats every 30s; coordinator marks worker offline after 90s of silence.
- Reads config from `~/.dialectical-worker/config.toml`.

### Web UI (Next.js + React + TypeScript)
- Public pages: `/` (past debates list), `/debate/[id]` (live or completed view).
- Auth-gated pages: `/new`, `/settings`, `/admin/workers`.
- Auth: user enters a bearer token once, stored in browser localStorage, sent as `Authorization: Bearer ...`.

## Backends (each worker has all that are installed)

| Adapter | Mechanism |
|---|---|
| `ClaudeCliAdapter` | subprocess `claude -p "{prompt}" --output-format stream-json --verbose` |
| `CodexCliAdapter` | subprocess `codex exec --skip-git-repo-check --sandbox workspace-write "{prompt}"` |
| `GeminiCliAdapter` | subprocess `gemini -p "{prompt}"` |
| `GrokCliAdapter` | subprocess `grok -p "{prompt}"` when `grok --help` advertises `-p`/`--prompt` |
| `XaiApiAdapter` | HTTP `POST https://api.x.ai/v1/chat/completions` — fallback if `grok` CLI is absent or lacks noninteractive prompt mode |
| `OllamaAdapter` | HTTP `POST http://localhost:11434/api/generate` — parameterized by model name |

`OllamaAdapter` is one class, multiple instances (one per pulled model: Qwen 3.6, Gemma 4, plus any others the user pulls).

All adapters implement:

```python
class ModelClient(Protocol):
    model_id: str
    role_pool: set[str]
    async def stream(self, system: str, user: str, max_tokens: int) -> AsyncIterator[str]: ...
    async def health_check(self) -> bool: ...
```

Workers detect installed adapters at startup (check `$PATH` for CLIs, hit `localhost:11434/api/tags` for Ollama, read `XAI_API_KEY` env). Registered capabilities = adapters that pass `health_check`.

## Data Model

```python
class Debate:
    id: UUID
    topic: str
    status: Literal["draft", "generating", "complete", "failed", "archived"]
    config: dict                    # depth, branching, role overrides
    root_node_id: UUID | None
    synthesis_id: UUID | None
    created_at: datetime
    completed_at: datetime | None

class Node:
    id: UUID
    debate_id: UUID
    parent_id: UUID | None
    node_type: Literal["ROOT_CLAIM", "PRO", "CON"]
    depth: int
    position: int
    claim: str
    active_generation_id: UUID | None
    status: Literal["pending", "generating", "complete", "failed", "stale"]
    materialized_path: str
    created_at: datetime

class Generation:
    id: UUID
    node_id: UUID
    model_id: str
    role: Literal["decomposer", "proposer", "opponent", "synthesizer"]
    argument: str
    prompt_version: str
    prompt_rendered: str
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int
    is_active: bool                 # exactly one True per node
    worker_id: UUID
    created_at: datetime

class Synthesis:
    id: UUID
    debate_id: UUID
    strongest_pro: str
    strongest_con: str
    verdict: str
    model_id: str
    worker_id: UUID
    created_at: datetime

class Worker:
    id: UUID
    name: str                       # "mac-mini", "adesso-mbp"
    token_hash: str                 # bcrypt of bearer
    capabilities: list[str]         # e.g. ["claude-sonnet-4.5", "codex-gpt-5", "grok-4", "ollama:qwen-3.6"]
    last_seen: datetime
    status: Literal["online", "offline", "degraded"]
    created_at: datetime

class Job:
    id: UUID
    node_id: UUID | None            # null for decompose/synthesize jobs that operate on debate, not a node
    debate_id: UUID
    job_type: Literal["decompose", "argue", "synthesize"]
    required_role: str
    required_model: str             # coordinator decides via routing
    status: Literal["pending", "claimed", "running", "complete", "failed"]
    worker_id: UUID | None
    claimed_at: datetime | None
    deadline: datetime
    idempotency_key: UUID
```

`Generation` is append-only — every regenerate writes a new row, `is_active` flips. Free history per node.

## Routing

`~/.dialectical/coordinator.toml`:

```toml
[roles.decomposer]
primary  = "claude-sonnet-4.5"
fallback = ["codex-gpt-5"]

[roles.proposer]
pool       = ["claude-sonnet-4.5", "codex-gpt-5", "gemini-2.5-pro", "grok-4", "ollama:qwen-3.6", "ollama:gemma-4-9b"]
strategy   = "round_robin"

[roles.opponent]
pool       = ["claude-sonnet-4.5", "codex-gpt-5", "gemini-2.5-pro", "grok-4", "ollama:qwen-3.6", "ollama:gemma-4-9b"]
strategy   = "round_robin"
constraint = "not_same_as_claim_author"

[roles.synthesizer]
primary  = "claude-opus-4.7"
fallback = ["codex-gpt-5"]
```

Coordinator picks the exact model from this config, creates a `Job` with `required_model`, and any worker whose `capabilities` contains that model can claim it. If no online worker has the model, the job stays pending; after a timeout (default 60s) coordinator promotes to the next fallback or routes to a different model in the pool.

## Generation Flow

1. **POST `/api/debates`** with topic + optional config. Coordinator creates `Debate` and `ROOT_CLAIM` node (claim = topic), creates a `decompose` Job.
2. A worker polls, claims the decompose job, calls the assigned model with the decomposer prompt. Streams tokens back via `POST /api/jobs/{id}/stream`. Coordinator forwards to SSE subscribers as `node_token` events for the root node.
3. Worker finalizes via `POST /api/jobs/{id}/complete` with structured JSON: root claim text + initial sub-claims (with claim text, not yet arguments).
4. Coordinator parses, creates child Nodes (PRO and CON) all `pending`, plus one `argue` Job per child. Emits `tree_ready`.
5. Workers claim argue jobs as they have available capabilities. Tokens stream → SSE `node_token`. Completion → `node_complete`.
6. When a node completes and `depth < max_depth`, coordinator may spawn its own children (using the just-written argument as the parent claim) and queue more argue jobs.
7. When all leaves complete, coordinator creates a `synthesize` job. Worker generates, streams `synthesis_token`, completes.
8. Coordinator emits `debate_complete`, persists final state.

### SSE events (coordinator → web UI)
- `tree_ready { tree }`
- `node_started { node_id, model_id, worker_id, role }`
- `node_token { node_id, delta }`
- `node_complete { node_id, generation_id }`
- `node_failed { node_id, reason, retry_in_s? }`
- `synthesis_started`, `synthesis_token`, `synthesis_complete`
- `debate_complete`
- `error { scope, message }`

## REST Surface

**Public (no auth):**
```
GET    /api/debates                       # list, paginated
GET    /api/debates/{id}                  # detail
GET    /api/debates/{id}/events           # SSE stream (read-only updates)
GET    /api/debates/{id}/export.md        # markdown export
GET    /api/backends/status               # online workers + their capabilities
```

**User-auth (Bearer user token):**
```
POST   /api/debates                       # create + start
DELETE /api/debates/{id}                  # archive (soft delete)
POST   /api/nodes/{id}/regenerate         # body: { model_id? }
GET    /api/nodes/{id}/generations        # generation history
GET    /api/settings
PUT    /api/settings
```

**Worker-auth (Bearer worker token):**
```
POST   /api/workers/register              # body: { name, capabilities }
POST   /api/workers/{id}/poll             # long-poll 30s
POST   /api/workers/{id}/heartbeat
POST   /api/jobs/{id}/stream              # chunked POST of token deltas
POST   /api/jobs/{id}/complete            # final result + metadata
POST   /api/jobs/{id}/fail                # body: { reason, retryable }
```

## Web UI Pages

- **`/`** (public): list of past debates with topic, date, model badges, completion status.
- **`/debate/[id]`** (public, live or static):
  - Vertical Kialo tree: root at top; pros branching right (green), cons branching left (red), recursive.
  - Each node card: claim, argument (streaming cursor if active), model badge, worker badge, role badge.
  - Auth-gated "Regenerate" button on each node.
  - Bottom synthesis panel: strongest pro / strongest con / verdict.
  - Top-right "Export Markdown" button.
- **`/new`** (auth): topic input + optional config (depth, branching, role overrides). Redirects to `/debate/[id]`.
- **`/settings`** (auth): enable/disable each model in routing pools, edit role config, view running spend per backend, and set per-backend monthly $ caps.
- **`/admin/workers`** (auth): live worker status, capabilities, current job, last_seen.

## Repository Layout

```
dialectical-engine/
├── coordinator/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                  debates.py, nodes.py, workers.py, jobs.py, events.py
│   │   ├── core/                 config, db, auth, logging
│   │   ├── models/               SQLAlchemy ORM
│   │   ├── services/             orchestrator.py, routing.py, synthesis.py
│   │   └── prompts/              decomposer.v1.md, proposer.v1.md, opponent.v1.md, synthesizer.v1.md
│   ├── migrations/               Alembic
│   ├── tests/
│   └── pyproject.toml
├── worker/
│   ├── app/
│   │   ├── main.py
│   │   ├── client.py             coordinator HTTP client + long-poll loop
│   │   ├── adapters/             base.py, claude_cli.py, codex_cli.py, gemini_cli.py, grok_cli.py, xai_api.py, ollama.py
│   │   ├── capabilities.py       startup detection
│   │   └── config.py
│   ├── tests/
│   └── pyproject.toml
├── web/                          Next.js
│   ├── app/                      page.tsx, debate/[id]/page.tsx, new/page.tsx, settings/page.tsx, admin/workers/page.tsx
│   ├── components/
│   └── lib/                      api client, SSE hook, types
├── deploy/
│   ├── cloudflared.config.yml
│   ├── launchd/                  coordinator.plist, worker.plist
│   └── README.md                 first-time setup
├── Makefile                      dev, test, install-services, install-tunnel
└── README.md
```

## Auth

- **User bearer token**: generated on first coordinator boot, printed to terminal once, stored hashed in DB. User pastes into the web UI; UI stores in browser localStorage. Used for `/new`, `/settings`, `/admin/*`, `/api/nodes/*/regenerate`.
- **Worker bearer token**: one per worker. Issued via `make register-worker` on the worker machine; the command prompts for the coordinator URL and the user token, then calls `POST /api/workers/register` and saves the returned worker token to `~/.dialectical-worker/config.toml`.
- **Public reads**: no auth. Rate-limit unauthenticated endpoints at 100 req/min/IP.

## Markdown Export Format

```markdown
# Debate: {topic}

**Created:** {date} • **Workers:** {distinct} • **Models:** {distinct} • **Depth:** {n} • **Nodes:** {n}

## Synthesis

**Strongest Pro** *(by {model})*: …
**Strongest Con** *(by {model})*: …
**Verdict** *(by {model})*: …

---

## Tree

### Root Claim
> {claim}

#### ▲ Pro 1 — *{model}* (worker: {worker})
{argument}

  ##### ▲ Pro 1.1 — *{model}*
  …

  ##### ▼ Con 1.1 — *{model}*
  …

#### ▼ Con 1 — *{model}*
{argument}

…
```

## Acceptance Criteria

1. `make dev` on Mac mini starts coordinator (`:8000`) + Next.js (`:3000`) + Worker A; `make install-tunnel` exposes the coordinator at `https://debate.<your-domain>` via Cloudflare Tunnel.
2. `make install-worker` on adesso MacBook registers Worker B with the public URL using the user token; both workers appear online in `/admin/workers`.
3. Opening `https://debate.<your-domain>` from any browser, no auth, shows the past debates list (empty initially).
4. Auth: clicking `/new` prompts for the user token; once entered, the topic form appears.
5. Post a topic like *"Should the EU ban gas cars by 2035?"*. Within ~30s the tree skeleton renders.
6. Arguments stream live into nodes, color-coded by model. Each node shows which worker generated it.
7. Both workers visibly participate over the course of the debate (visible in `/admin/workers`).
8. When all nodes complete, the synthesis panel populates with strongest pro / strongest con / verdict.
9. Any node has a "Regenerate" button; clicking re-queues a job with a different model; new generation streams in place, old preserved in history.
10. "Export Markdown" downloads the full debate.
11. Past debates persist in SQLite; revisiting any URL shows it exactly as left.
12. Power off the adesso MacBook → Worker A handles new debates alone, just slower. Power back on → Worker B reappears and picks up new jobs.
13. `make test` → all unit + integration tests pass; ≥70% coverage on `coordinator/services` and `worker/adapters`.

## Milestones

| M | Scope |
|---|---|
| **M1** | Coordinator skeleton: FastAPI, SQLite, ORM models (Debate, Node, Generation, Synthesis, Worker, Job), worker register/poll/complete endpoints, mock adapter, end-to-end mock loop |
| **M2** | Worker skeleton: register, capabilities detection, long-poll, mock adapter, complete loop. Run Worker A on Mac mini against local coordinator. |
| **M3** | All six real adapters in worker. Capabilities detection wires them up. Health checks. |
| **M4** | Coordinator orchestration: decomposer → tree expansion → argue jobs → recurse → synthesizer. Routing engine with role pools and constraints. Run via curl, full tree appears in DB. |
| **M5** | Next.js UI: list, debate detail (no streaming yet), `/new` with auth gate, `/admin/workers`. |
| **M6** | SSE streaming end-to-end: worker chunked POST → coordinator → browser SSE → live token rendering on the tree. |
| **M7** | Regenerate flow, markdown export, settings UI, synthesis rendering, history viewer per node. All acceptance criteria pass locally. |
| **M8** | Deploy: Cloudflare Tunnel config, launchd plists for coordinator and worker, install scripts. Worker B on adesso MacBook connects from outside the LAN through the tunnel. |

## Risks & Notes

- **Anthropic Agent SDK credit (effective 2026-06-15)**: `claude -p` from the worker draws from a separate monthly credit ($20 Pro / $100 Max-5x / $200 Max-20x). Settings UI surfaces the running spend per backend; per-backend monthly $ cap enforced before issuing jobs.
- **Gemini CLI ToS**: hostile to third-party orchestration. The worker now includes a `GeminiApiAdapter` for `gemini-2.5-pro`; set `GEMINI_API_KEY` to use the Google AI Studio API path and avoid relying on Gemini CLI unattended auth. Rerun `make install-worker` with the key present so the launchd worker receives it.
- **Grok CLI**: worker detection and deployment preflight only count the installed `grok` binary when `grok --help` advertises non-interactive `-p`/`--prompt` invocation; otherwise `XaiApiAdapter` (xAI API) is the `grok-4` fallback when `XAI_API_KEY` is set. Rerun `make install-worker` with the key present so launchd receives it.
- **SQLite + concurrent workers**: workers never write to the DB directly; all writes go through coordinator REST endpoints, which serialize them through a single asyncio writer task. Use `aiosqlite` and WAL mode.
- **Cloudflare Tunnel + SSE**: long-lived connections work but Cloudflare may rotate the quick tunnel; named-tunnel install rejects `trycloudflare.com` quick tunnel hostnames so the production hostname is stable. SSE clients (browser and worker streaming POST) must auto-reconnect with backoff.
- **Final production gate**: use `make status STATUS_FLAGS=--strict-production` only after the named tunnel is installed, the quick tunnel is stopped with `make stop-quick-tunnel`, local proof artifacts are refreshed, Worker B onboarding is complete, handoff bundles are regenerated for the named URL, and all three production acceptance reports exist. It runs endpoint checks and fails on quick-tunnel runtime, stale prompt-safety source invariants, stale worker retry/stream resilience source invariants, stale Gemini API adapter source invariants, stale local proof, stale bundles, or missing/stale/incomplete production reports, including reports that lack auth-gated token-flow, post-unlock web surface, browser SSE streaming-client, regenerate/history action-control proof, named HTTPS URL-class proof, structured online/offline worker rows, generated/regenerated worker and model ID fields, expected generated and regenerated worker names for the phase, a structured real regeneration model switch, observed non-mock model IDs, non-local worker names, or expected-offline workers in online/generated/regenerated evidence.
- **Adesso MacBook offline**: worker should gracefully retry on network drops, surface "degraded" status in `/admin/workers`, resume on reconnection.
- **Worker B model exposure**: onboarding defaults to `ALLOWED_MODELS=codex-gpt-5`, fails before registration if no healthy adapter matches that pin, and verifies that capability through the public coordinator until additional unattended adapter auth is proved.
- **Public read endpoint abuse**: rate-limit `100 req/min/IP` on all public routes. Cloudflare in front already gives DDoS protection.
- **Prompt injection**: sanitize topic input and model-generated claim text before reflecting into child prompts. Wrap all reflected content in clearly delimited tags in templates.
- **Structured output for decomposer**: use the adapter's native structured-output mode (Claude tool use, OpenAI JSON mode, Gemini structured output) where available; otherwise robust fenced-JSON parser.

## Out of Scope

- Multiple human users, OAuth, RBAC, accounts
- Cross-debate semantic reuse, embeddings, pgvector
- Reputation, anti-sybil, World ID, BrightID, stake/slashing
- MultiversX or any blockchain
- Browser automation of Claude.ai / ChatGPT / Gemini web UIs
- Tauri / desktop packaging
- EU AI Act labels, C2PA credentials
- Mobile UI
- Real-time collaborative editing
- Public API for third parties
