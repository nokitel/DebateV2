# /goal — Build the Dialectical Engine (Proposal B: Debate-Weighted QBAF)

## Mission
Implement a **confidence-driven AI debate engine** that scores the trustworthiness of any claim by debating it with adversarial, multi-perspective LLM agents over a **Quantitative Bipolar Argumentation Framework (QBAF)** graph, grounds every evidence leaf "from the ground up," and propagates per-node scores into a single calibrated root confidence. Build it in **small, independently testable increments**. Ship a working scoring core early; layer debate, evidence validation, and orchestration on top.

## Operating method (read first, follow every step)
1. **Work one Step at a time. Never skip ahead or batch Steps.**
2. At the **start of each Step**: restate the Step goal, list the files you will create/touch, state the **Definition of Done (DoD)** and the exact test that proves it, and write a 3–6 line plan. Then implement.
3. **Tests are mandatory.** Write the test alongside (or before) the code. Everything stays green. Use the deterministic `FakeProvider` (Step 2) for any test that would otherwise call a live model — **no test may hit a paid API.**
4. At the **end of each Step**: run the full suite, show it green, update `AGENTS.md` / docs if anything changed, and `git commit` with a clear message (e.g. `feat(step-4): self-consistency base scoring`). Then **STOP and report** a short summary so I can review before the next Step.
5. Keep changes minimal and reversible. Prefer small pure functions. Do not add a dependency without saying why.
6. If a Step reveals the plan is wrong, say so and propose a revision **before** coding around it.

## Non-negotiable invariants (re-check at every Step; record them in `AGENTS.md`)
- **Provider-agnostic agents.** Every LLM call goes through the `LLMProvider` interface (Step 2). No agent, scorer, or subsystem may import or call the OpenAI SDK/CLI directly. Each agent role gets its provider + model from config; switching any agent to another provider must require **zero code changes outside a new adapter + one config line**.
- **OpenAI/Codex is the only adapter implemented now**, but the second adapter must be addable without touching anything but `providers/` and config.
- **Pure propagation.** The graph-scoring math (Step 4) contains **no LLM calls, no I/O, no randomness** — it is a deterministic function of the graph. This keeps it unit-testable and auditable.
- **Swappable semantics.** DF-QuAD is the default gradual semantics, but it lives behind a `Semantics` strategy interface so QE / quadratic-energy can replace it later without touching the orchestrator.
- **Every leaf is gated by the evidence subsystem.** A claim that cites a source never gets a base score directly from "the model said so" — it is set by the Step 8 pipeline (retraction → entailment → quality grade → corroboration). A retracted/unsupported source caps the leaf near 0.
- **Anonymize debate sources** (strip "Agent A said…" identity) before any agent reads another's turn, to suppress sycophancy/conformity.
- **A node is never marked `converged` until the Skeptic certifies no unaddressed attack remains** (defeats false consensus).
- **Confidence-driven, cost-soft.** Stopping is driven by score convergence + caveat resolution + multi-perspective agreement. Cost is a soft tie-breaker, never a hard budget.

## Target architecture (guidance, not gospel)
- Language: **Python 3.11+**. Graph: in-memory (`dataclasses` / `networkx`) for v1; Neo4j later (Step 13). Tests: `pytest`. Config: `pydantic-settings` + YAML. Async optional but keep adapters sync-friendly.
- Layout:
```
dialectical_engine/
  providers/        # LLMProvider interface + OpenAI adapter + FakeProvider
  graph/            # QBAF data model, serialization
  semantics/        # DF-QuAD (default), QE later — behind a Semantics interface
  scoring/          # self-consistency base scoring
  debate/           # debaters, judge, roster, anonymization, protocol
  evidence/         # retraction, entailment, quality grading, corroboration
  metareasoning/    # node selection (EVOI proxy) + stopping criteria
  orchestrator/     # the recursive expand→debate→ground→propagate→stop loop
  api/              # FastAPI (later)
  eval/             # benchmark + calibration harness (later)
config/agents.yaml  # per-agent provider/model map
AGENTS.md           # invariants + how-to-run, kept current
```

### Provider interface (the keystone — build in Step 2)
Transport-agnostic so an adapter may wrap the OpenAI SDK **or** shell out to the Codex CLI:
```python
# providers/base.py
from dataclasses import dataclass
from typing import Protocol

@dataclass
class LLMResponse:
    text: str
    raw: dict
    usage: dict | None   # tokens / cost if the provider reports them

class LLMProvider(Protocol):
    name: str
    def generate(
        self,
        messages: list[dict],          # [{"role": "system|user|assistant", "content": str}]
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str | None = None,  # "json" for structured calls
    ) -> LLMResponse: ...
```
```yaml
# config/agents.yaml
defaults: { provider: openai, model: ${OPENAI_MODEL}, temperature: 0.2 }
agents:
  proponent:     { }                       # inherits defaults
  opponent:      { }
  judge:         { temperature: 0.0 }
  specialist:    { }
  methodologist: { }
  skeptic:       { }
  estimator:     { temperature: 0.0 }
# Later: set any line to provider: anthropic|gemini|grok|ollama and register the adapter.
# No agent code changes.
```

---

## The increments

### Milestone 0 — Foundation
**Step 1 — Skeleton & guardrails.** Create the package layout, `pytest` setup, structured logging, `.env` handling (`OPENAI_API_KEY`, `OPENAI_MODEL`), and `AGENTS.md` seeded with the invariants above. *DoD:* `pytest` runs, a trivial test passes, config loads from `.env`.

**Step 2 — Provider abstraction layer.** Implement `LLMProvider`, a `ProviderRegistry` (role → adapter+model from `config/agents.yaml`), the **OpenAI/Codex adapter** (the only real one), and a deterministic `FakeProvider` for tests. *DoD:* a live call works through the interface; the same call code works unchanged when the registry is pointed at `FakeProvider`; a test asserts no module outside `providers/` references OpenAI.

### Milestone 1 — Scoring core (no LLM yet)
**Step 3 — QBAF data model.** `ClaimNode` (`id`, `text`, `type ∈ {root, sub_claim, evidence_leaf}`, `base_score τ`, `final_strength σ`, `uncertainty`, `status`, `caveats[]`, `transcript`) and signed weighted `Edge` (`polarity ∈ {support,attack}`, `weight w∈[0,1]`). JSON (de)serialization. *DoD:* build/serialize/reload a hand-made graph; round-trip test passes.

**Step 4 — DF-QuAD propagation (pure, deterministic).** Implement product aggregation + linear influence, edge-weight scaling (effective child strength = `w · σ_child`), attackers/supporters aggregated separately, bottom-up over an acyclic tree. Put it behind a `Semantics` interface (QE as a future sibling). *DoD:* **reproduce the Rago et al. 2016 DF-QuAD worked-example σ values within ±0.001** as a golden test; property tests for balance/monotonicity.

### Milestone 2 — Debate-weighted scoring
**Step 5 — Self-consistency base scoring.** Given a claim, sample the assigned agent k=3–5× via the provider layer, parse a base score + edge weight, and reduce to `τ`/`w` + an uncertainty from sample spread. *DoD:* returns calibrated `τ` with uncertainty; fully deterministic under `FakeProvider`.

**Step 6 — Two-debater + judge loop.** Proponent vs. Opponent argue high-vs-low trustworthiness over n short rounds (each turn must cite evidence, routed to the Step 8 stub for now); a Judge sets `τ` and `w`; debater disagreement → node uncertainty. **Anonymize turns** before each agent reads them. Store the transcript on the node. *DoD:* end-to-end debate on one claim yields `τ`, `w`, uncertainty, transcript; deterministic under `FakeProvider`.

**Step 7 — Agent roster & routing.** Add **Domain-Specialist**, **Methodologist/Statistician**, and **Skeptic/red-team** personas, plus a lightweight topic classifier that routes specialists to relevant claims. Every role pulls provider+model from `config/agents.yaml`. *DoD:* roster is config-driven; specialist fires on flagged topics; Skeptic exposes a `certify_no_unaddressed_attack(node) -> bool` hook.

### Milestone 3 — Evidence & anti-obfuscation
**Step 8 — Evidence-validation subsystem (leaf grounding).** Pipeline that sets `τ_leaf`: (a) resolve DOI + **retraction check** (cap near 0 if retracted); (b) **SciFact-style** SUPPORTS / REFUTES / NOINFO entailment of the *specific* claim against the cited text, with rationale sentences; (c) **GRADE / RoB-2 signaling-question** quality grade → multiplier on `τ` (advisory, surfaced as uncertainty); (d) corroboration / citation-context count; (e) statistical red-flags (small n, missing effect sizes). Output `τ_leaf` + `caveats[]`. Build each check as an independently testable module. *DoD:* claim+source returns `τ_leaf`+caveats; a retracted source caps `τ`; a NOINFO source collapses support.

**Step 9 — Anti-obfuscation prover-estimator check.** For "big argument" nodes the Opponent cannot fully rebut: decompose into subclaims, have an Estimator assign probabilities, and **cap the parent's support if any subclaim is undefendable**. *DoD:* triggers on flagged nodes; an undefendable subclaim measurably lowers parent support.

### Milestone 4 — Metareasoning & orchestration
**Step 10 — Node selection (EVOI proxy).** Per open node, compute **sensitivity** = how much root σ moves if this node's σ swings across its plausible range (finite difference on the DF-QuAD function). Rank by `sensitivity × uncertainty`, sharpened by debater disagreement; soft cost penalty as tie-breaker. *DoD:* orchestrator returns the next node to expand and logs the full ranking.

**Step 11 — Stopping criterion.** Halt expansion when **all** hold: root σ changed < ε (default 0.02) across two iterations; no open node is both high-sensitivity and high-uncertainty; no unresolved caveats; debaters stopped shifting position; and the Skeptic certifies no unaddressed attack. *DoD:* halts on a converged tree; a "false-consensus" fixture (agents agree but an attack is unaddressed) does **not** halt.

**Step 12 — Recursive orchestrator.** Wire it together: from the root question → pick node (Step 10) → debate/score (Steps 5–7) → ground leaves (Step 8) → run anti-obfuscation where flagged (Step 9) → propagate (Step 4) → check stop (Step 11) → repeat; spawn child sub-debates only when debaters fail to converge **and** the node materially moves the root. *DoD:* a full run on a sample question produces a scored graph with root confidence, per-node τ/σ, caveats, and transcripts.

### Milestone 5 — Productionization & evaluation
**Step 13 — Persistence, API, observability.** Add Neo4j persistence behind a repository interface (keep the in-memory impl for tests), FastAPI endpoints to start a run and fetch the graph, and structured run traces/replay. *DoD:* a run persists and is retrievable; the API returns the graph JSON.

**Step 14 — Evaluation & decision gate.** Harness that scores the engine on a labeled QA set (and a Kialo tree with human impact votes), runs a **matched-compute comparison of debate (Proposal B) vs. a self-consistency baseline**, and reports calibration (ECE). *DoD:* outputs accuracy + ECE + the baseline delta, and **flags whether the debate layer actually beats self-consistency** — if it doesn't, recommend simplifying toward the MVP and investing in the evidence subsystem instead.

---

## Research provenance (for the agent's and my reference, do not re-derive)
QBAF + DF-QuAD gradual semantics (Baroni/Rago/Toni 2019; Rago et al. 2016; Potyka 2018 for QE) → Steps 3–4. AI-safety-via-debate and its empirical support under information asymmetry (Irving et al. 2018; Khan et al. 2024; Kenton et al. 2024), incl. doubly-efficient / prover-estimator anti-obfuscation (Brown-Cohen et al. 2024, 2025) → Steps 6, 9. Multi-agent debate gains **and** sycophancy/false-convergence failure modes (Du et al. 2023; Zhang et al. 2025; "Talk Isn't Always Cheap" 2025) → Steps 6–7, 11, 14. Self-consistency + semantic entropy + SPRT-style stopping (Wang et al. 2022; Farquhar et al. *Nature* 2024; ConSol 2025) → Steps 5, 11. Value-of-computation node selection (Russell & Wefald 1991; EVPI) → Step 10. SciFact claim verification + GRADE + Cochrane RoB-2 + retraction/citation-context signals → Step 8.

## Explicitly out of scope for now
Cross-question correlation — storing each resolved graph and reusing prior appraisals / detecting contradictions across sessions via a RAG knowledge graph. **Do not build this.** Just keep the run output serialized so it's possible later.