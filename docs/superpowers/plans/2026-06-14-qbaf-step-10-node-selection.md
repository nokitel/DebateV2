# QBAF Step 10 Node Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an EVOI-style proxy that ranks open nodes by root sensitivity times uncertainty/disagreement, with a soft cost penalty.

**Architecture:** Node selection lives under `coordinator/app/metareasoning/`. It remains pure and uses the swappable QBAF semantics interface from Step 4. For each open non-root node, the selector perturbs that node across its plausible range, propagates the graph, measures root movement, and returns a full ranking plus the next node to expand.

**Tech Stack:** Python 3.12, dataclasses, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/metareasoning/node_selection.py`: ranking dataclasses and selector.
- Modify `apps/dialectical-engine/coordinator/app/metareasoning/__init__.py`: public node-selection exports.
- Create `apps/dialectical-engine/coordinator/tests/test_node_selection.py`: sensitivity/ranking tests.
- Create `docs/superpowers/plans/2026-06-14-qbaf-step-10-node-selection.md`: this plan.

## Step Goal, Files, DoD, And Tests

Step goal: choose the next open node to expand based on root score sensitivity and uncertainty.

Files touched:

- `apps/dialectical-engine/coordinator/app/metareasoning/node_selection.py`
- `apps/dialectical-engine/coordinator/app/metareasoning/__init__.py`
- `apps/dialectical-engine/coordinator/tests/test_node_selection.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-10-node-selection.md`

Definition of Done:

- Selector ranks all open non-root nodes.
- Sensitivity is computed by finite difference through the `Semantics` strategy.
- Plausible range is derived from `final_strength +/- uncertainty`, clipped to `[0, 1]`.
- Priority is `sensitivity * uncertainty`, sharpened by transcript score disagreement, with cost as a soft divisor.
- Full ranking is returned for logging/inspection.
- `select_next_node` returns the highest-priority node or `None`.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 10 commit is created with message `feat(step-10): add qbaf node selection`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_node_selection.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Node-Selection Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_node_selection.py`

- [x] **Step 1: Write the failing tests**

Tests cover ranking, root sensitivity, transcript disagreement sharpening, and the no-open-node case.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because node-selection exports do not exist yet.

### Task 2: Add Selector Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/metareasoning/node_selection.py`
- Modify: `apps/dialectical-engine/coordinator/app/metareasoning/__init__.py`

- [x] **Step 1: Implement ranking dataclass and finite difference**

Perturb one node at a time and measure propagated root movement.

- [x] **Step 2: Implement ranking and selection**

Rank open non-root nodes by priority and return the full list.

### Task 3: Verify And Commit

**Files:**
- All Step 10 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [ ] **Step 4: Commit**

Stage Step 10 files and commit with:

```bash
git commit -m "feat(step-10): add qbaf node selection"
```
