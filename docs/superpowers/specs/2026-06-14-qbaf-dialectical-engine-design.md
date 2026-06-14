# QBAF Dialectical Engine Design

## Context

The repository already contains the Dialectical Engine application under
`apps/dialectical-engine/`. That app has a FastAPI coordinator, SQLite state,
worker registration, role/model routing, and worker adapters for Codex, Claude,
Gemini, Grok, Ollama, LM Studio, xAI, and deterministic mock models.

Proposal B adds a confidence-driven debate scorer over a Quantitative Bipolar
Argumentation Framework (QBAF). The implementation must preserve the existing
application instead of creating a parallel platform.

## Decision

Implement Proposal B as an evolution of `apps/dialectical-engine/`.

The QBAF core will live in the coordinator as focused Python modules. The
existing worker/routing system remains the runtime path for live agents, while a
small provider facade gives scoring, debate, evidence, and metareasoning code a
stable protocol that is independent of any model vendor or CLI.

## Architecture

The implementation will add coordinator modules in small increments:

- `coordinator/app/qbaf/`: pure QBAF graph model, serialization, gradual
  semantics, and scoring helpers.
- `coordinator/app/providers/`: `LLMProvider`, `LLMResponse`, deterministic
  `FakeProvider`, and provider registry/facade used by new engine code.
- `coordinator/app/debate/`: debate roles, anonymization, judging, transcripts,
  and skeptic certification hooks.
- `coordinator/app/evidence/`: evidence grounding pipeline modules added after
  the scoring/debate core exists.
- `coordinator/app/metareasoning/`: node selection and stopping criteria.

Existing `coordinator/app/services/orchestrator.py` and worker job flows will be
integrated only after the pure scoring/debate components are covered by focused
tests. Existing production debate generation should keep working during the
transition.

## Provider Boundary

All new LLM-dependent code will call a provider protocol:

```python
@dataclass
class LLMResponse:
    text: str
    raw: dict
    usage: dict | None

class LLMProvider(Protocol):
    name: str

    def generate(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        ...
```

The first real adapter will be Codex-compatible. The design must still make
future adapters platform-neutral: adding another provider should require changes
inside `coordinator/app/providers/` plus config, not inside QBAF scoring,
debate, evidence, metareasoning, or orchestration code.

Tests that need model behavior must use `FakeProvider`; no test may call a paid
or live API.

## Configuration

The current app uses routing in `coordinator/app/core/config.py` and runtime
settings. The Proposal B agent roster will extend that pattern instead of
introducing an unrelated config system.

Roles such as `proponent`, `opponent`, `judge`, `specialist`, `methodologist`,
`skeptic`, and `estimator` will each resolve to provider/model/temperature
settings through config. Switching an agent role to another platform must not
require changes to the role implementation.

## Data Flow

Early milestones use in-memory dataclasses:

1. Build or load a QBAF graph.
2. Assign base scores to nodes through deterministic scoring or provider-backed
   role calls.
3. Ground evidence leaves through the evidence subsystem once that milestone is
   reached.
4. Propagate strengths through pure semantics.
5. Use metareasoning to select the next node, stop, or expand.

Persistence and API changes are deferred until the core graph and debate loop
are independently tested.

## Error Handling

- Provider errors will be surfaced as structured failures with provider name,
  role, model, and safe error text.
- Parser failures for model JSON will fail the current scoring/debate operation
  rather than silently fabricating scores.
- Pure QBAF semantics will reject malformed graphs, invalid scores, invalid
  edge weights, and cycles with explicit exceptions.
- Evidence checks will produce caveats and score caps rather than hiding weak or
  unsupported sources.

## Testing

Every proposal step must be implemented with tests before or alongside code.
The near-term gates are:

- Step 1: coordinator test discovery proves the QBAF package scaffold is wired,
  app-level guardrails document the invariants, and config can still load.
- Step 2: provider registry works with `FakeProvider` and Codex-compatible
  config; static tests assert new non-provider modules do not reference Codex,
  OpenAI, or vendor SDKs.
- Step 3: QBAF graph JSON round trips.
- Step 4: DF-QuAD propagation is pure and deterministic, with golden/property
  tests.

Full app tests remain the safety net. Focused tests should be used during each
step, and `make test` should be run before each step commit when dependencies
are available.

## Step Discipline

The proposal's step discipline remains in force:

- Work one numbered proposal step at a time.
- At the start of each step, restate the goal, touched files, DoD, exact tests,
  and a short plan.
- End each step with tests, docs updates when behavior changes, and a clear git
  commit.

The user has approved continuing through simple approval gates, but material
architecture changes, dependency additions, paid/live model calls, or scope
changes still require explicit user confirmation.

## Out Of Scope

- Cross-question memory, RAG reuse of prior appraisals, and contradiction
  detection across sessions.
- Neo4j persistence before the in-memory QBAF core is proven.
- Live non-Codex adapters for Proposal B before the provider boundary and fake
  tests exist.
- Replacing the existing worker adapter ecosystem.
