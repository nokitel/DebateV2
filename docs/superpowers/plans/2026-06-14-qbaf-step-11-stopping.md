# QBAF Step 11 Stopping Criterion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conservative convergence/stopping criterion for QBAF expansion.

**Architecture:** Stopping logic lives under `coordinator/app/metareasoning/` and composes already-built pieces: root score history, `NodeSelector` rankings, node caveats/status, debate transcript score movement, and the `Skeptic` certification hook. It returns a structured decision with blocking reasons instead of a bare boolean.

**Tech Stack:** Python 3.12, dataclasses, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/metareasoning/stopping.py`: decision dataclass and criterion.
- Modify `apps/dialectical-engine/coordinator/app/metareasoning/__init__.py`: public stopping exports.
- Create `apps/dialectical-engine/coordinator/tests/test_stopping.py`: convergence and false-consensus tests.
- Create `docs/superpowers/plans/2026-06-14-qbaf-step-11-stopping.md`: this plan.

## Step Goal, Files, DoD, And Tests

Step goal: decide whether expansion can halt with explicit reasons.

Files touched:

- `apps/dialectical-engine/coordinator/app/metareasoning/stopping.py`
- `apps/dialectical-engine/coordinator/app/metareasoning/__init__.py`
- `apps/dialectical-engine/coordinator/tests/test_stopping.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-11-stopping.md`

Definition of Done:

- Root score must change by less than epsilon across the last two iterations.
- High-priority open nodes from `NodeSelector` block stopping.
- Any unresolved caveat blocks stopping.
- Debate score movement above epsilon blocks stopping.
- Skeptic certification failure blocks stopping.
- Decision returns `should_stop` plus reason strings.
- Converged fixture halts.
- False-consensus fixture with unaddressed attack does not halt.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 11 commit is created with message `feat(step-11): add stopping criterion`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_stopping.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Stopping Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_stopping.py`

- [x] **Step 1: Write the failing tests**

Tests cover converged halt, false consensus, unstable root history, and high-priority open node blocking.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because stopping exports do not exist yet.

### Task 2: Add Stopping Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/metareasoning/stopping.py`
- Modify: `apps/dialectical-engine/coordinator/app/metareasoning/__init__.py`

- [x] **Step 1: Implement decision and checks**

Add root stability, open-node, caveat, debate movement, and skeptic checks.

- [x] **Step 2: Return structured reasons**

Aggregate blocking reasons into a deterministic decision object.

### Task 3: Verify And Commit

**Files:**
- All Step 11 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [ ] **Step 4: Commit**

Stage Step 11 files and commit with:

```bash
git commit -m "feat(step-11): add stopping criterion"
```
