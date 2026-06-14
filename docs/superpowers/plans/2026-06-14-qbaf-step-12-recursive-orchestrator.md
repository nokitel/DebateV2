# QBAF Step 12 Recursive Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Proposal B scoring pieces into a deterministic in-memory recursive orchestrator.

**Architecture:** The new orchestrator lives under `coordinator/app/orchestration/` so it does not disturb the existing production `app/services/orchestrator.py`. It composes the provider-backed debate loop, evidence pipeline, anti-obfuscation check, DF-QuAD semantics, node selector, and stopping criterion. The first version runs fully in memory and is deterministic under `FakeProvider`.

**Tech Stack:** Python 3.12, dataclasses, standard-library hashing, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/orchestration/__init__.py`: public orchestration exports.
- Create `apps/dialectical-engine/coordinator/app/orchestration/recursive.py`: run result dataclass and recursive orchestrator.
- Create `apps/dialectical-engine/coordinator/tests/test_recursive_orchestrator.py`: end-to-end in-memory orchestration tests.
- Modify `apps/dialectical-engine/coordinator/tests/test_providers.py`: include `app/orchestration` in vendor-boundary checks.
- Create `docs/superpowers/plans/2026-06-14-qbaf-step-12-recursive-orchestrator.md`: this plan.

## Step Goal, Files, DoD, And Tests

Step goal: run a complete sample question through debate, evidence grounding, propagation, node selection, and stopping.

Files touched:

- `apps/dialectical-engine/coordinator/app/orchestration/__init__.py`
- `apps/dialectical-engine/coordinator/app/orchestration/recursive.py`
- `apps/dialectical-engine/coordinator/tests/test_recursive_orchestrator.py`
- `apps/dialectical-engine/coordinator/tests/test_providers.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-12-recursive-orchestrator.md`

Definition of Done:

- `RecursiveQBAFOrchestrator.run(root_question, evidence_sources=...)` creates a root graph and returns a structured run result.
- Seed evidence leaves are explicit via `seed_evidence=True`; otherwise `evidence_sources` is only a source registry for cited evidence.
- `run_graph(graph, evidence_sources=...)` can continue an existing graph.
- Root and sub-claim nodes are scored through `TwoDebaterJudgeLoop`.
- Evidence leaves are grounded through `EvidenceValidationPipeline`.
- Anti-obfuscation is run for debated non-evidence nodes.
- DF-QuAD propagation updates final strengths after each step.
- Node selection chooses open non-root nodes after root scoring.
- Stopping decisions are recorded.
- Cited evidence children are spawned only when debater disagreement and root materiality thresholds are met.
- Provider-boundary static test covers `app/orchestration`.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 12 commit is created with message `feat(step-12): add recursive qbaf orchestrator`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_recursive_orchestrator.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Orchestrator Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_recursive_orchestrator.py`
- Modify: `apps/dialectical-engine/coordinator/tests/test_providers.py`

- [x] **Step 1: Write the failing tests**

Tests cover a full sample run, continuing an existing graph by selected open node, and gated cited-evidence child spawning.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because `app.orchestration` does not exist yet.

### Task 2: Add Recursive Orchestrator Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/orchestration/__init__.py`
- Create: `apps/dialectical-engine/coordinator/app/orchestration/recursive.py`

- [x] **Step 1: Implement run result and graph seeding**

Create root graphs and deterministic evidence leaf IDs from source references.

- [x] **Step 2: Implement node processing**

Debate non-evidence nodes, ground evidence leaves, update edge weights, run anti-obfuscation, and optionally spawn cited evidence leaves.

- [x] **Step 3: Implement recursive loop**

Propagate, select next nodes, record root history/stopping decisions, and stop or return at `max_iterations`.

### Task 3: Verify And Commit

**Files:**
- All Step 12 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [ ] **Step 4: Commit**

Stage Step 12 files and commit with:

```bash
git commit -m "feat(step-12): add recursive qbaf orchestrator"
```
