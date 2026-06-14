# QBAF Step 6 Debate Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic two-debater plus judge loop for scoring a single claim node.

**Architecture:** The debate loop lives in `coordinator/app/debate/` and depends on `ProviderRegistry`, the QBAF node model, Step 5 score parsing, and a tiny Step 8 evidence-validation stub. Debater turns are parsed from JSON, must cite evidence, and are stored on the node transcript. Prior turns are anonymized before being sent to any later agent. The judge returns `base_score` and `edge_weight`; debater score spread becomes node uncertainty.

**Tech Stack:** Python 3.12, dataclasses, standard-library JSON, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/debate/__init__.py`: public debate exports.
- Create `apps/dialectical-engine/coordinator/app/debate/loop.py`: anonymization, turn parser, and two-debater/judge loop.
- Create `apps/dialectical-engine/coordinator/app/evidence/__init__.py`: public evidence exports.
- Create `apps/dialectical-engine/coordinator/app/evidence/stub.py`: pending Step 8 evidence validation stub.
- Create `apps/dialectical-engine/coordinator/tests/test_debate_loop.py`: loop, anonymization, and evidence tests.
- Modify `apps/dialectical-engine/coordinator/tests/test_providers.py`: include debate/evidence modules in vendor-boundary checks.

## Step Goal, Files, DoD, And Tests

Step goal: run one deterministic debate on a claim and return an updated node plus judge edge weight.

Files touched:

- `apps/dialectical-engine/coordinator/app/debate/__init__.py`
- `apps/dialectical-engine/coordinator/app/debate/loop.py`
- `apps/dialectical-engine/coordinator/app/evidence/__init__.py`
- `apps/dialectical-engine/coordinator/app/evidence/stub.py`
- `apps/dialectical-engine/coordinator/tests/test_debate_loop.py`
- `apps/dialectical-engine/coordinator/tests/test_providers.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-6-debate-loop.md`

Definition of Done:

- Debate loop calls `proponent`, `opponent`, and `judge` through `ProviderRegistry`.
- Debater outputs must be valid JSON with `argument`, `score`, and non-empty `evidence`.
- Evidence references are routed through a Step 8 stub and recorded with pending validation status.
- Prior turns are anonymized before another agent reads them.
- Judge output reuses Step 5 score parsing and sets node `base_score` plus returned `edge_weight`.
- Node uncertainty equals debater score spread.
- Node transcript stores all debater and judge turns.
- Vendor-boundary static test covers `app/debate` and `app/evidence`.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 6 commit is created with message `feat(step-6): add two-debater judge loop`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_debate_loop.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Debate Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_debate_loop.py`
- Modify: `apps/dialectical-engine/coordinator/tests/test_providers.py`

- [x] **Step 1: Write the failing tests**

Tests cover loop scoring, call order, anonymized prior turns, evidence-stub recording, and required evidence validation.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because `app.debate` and `app.evidence` do not exist yet.

### Task 2: Add Debate And Evidence Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/debate/__init__.py`
- Create: `apps/dialectical-engine/coordinator/app/debate/loop.py`
- Create: `apps/dialectical-engine/coordinator/app/evidence/__init__.py`
- Create: `apps/dialectical-engine/coordinator/app/evidence/stub.py`

- [x] **Step 1: Implement evidence stub**

Return pending Step 8 validation records for each citation without scoring evidence yet.

- [x] **Step 2: Implement debate parser and anonymization**

Parse debater JSON, require evidence, validate scores, and strip role identity from prior turns.

- [x] **Step 3: Implement two-debater plus judge loop**

Call proponent/opponent for each round, then judge, and return a `DebateResult`.

### Task 3: Verify And Commit

**Files:**
- All Step 6 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [x] **Step 4: Commit**

Stage Step 6 files and commit with:

```bash
git commit -m "feat(step-6): add two-debater judge loop"
```
