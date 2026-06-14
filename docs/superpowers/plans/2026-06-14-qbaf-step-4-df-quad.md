# QBAF Step 4 DF-QuAD Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pure, swappable DF-QuAD propagation for weighted QBAF graphs.

**Architecture:** Semantics live under `coordinator/app/qbaf/` behind a small strategy interface. DF-QuAD reads a `QBAFGraph`, computes bottom-up strengths from incoming support and attack edges, applies edge weights as child-strength multipliers, and returns a new graph with updated `final_strength` values.

**Formula source:** DF-QuAD uses the Rago et al. gradual semantics formula as recapped in arXiv:2410.22209: probabilistic sum for support and attack aggregation, followed by the discontinuity-free combination function over base score, attacker strength, and supporter strength.

**Tech Stack:** Python 3.12, dataclasses, standard-library typing, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/qbaf/semantics.py`: semantics protocol, DF-QuAD implementation, and formula helpers.
- Modify `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`: export semantics types and helpers.
- Create `apps/dialectical-engine/coordinator/tests/test_qbaf_semantics.py`: formula, monotonicity, immutability, and cycle tests.

## Step Goal, Files, DoD, And Tests

Step goal: propagate a hand-made weighted QBAF graph with deterministic DF-QuAD scores and no side effects.

Files touched:

- `apps/dialectical-engine/coordinator/app/qbaf/semantics.py`
- `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`
- `apps/dialectical-engine/coordinator/tests/test_qbaf_semantics.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-4-df-quad.md`

Definition of Done:

- `Semantics` protocol exists for future semantics replacements.
- `DFQuADSemantics` is the default concrete strategy.
- Propagation is pure: no model calls, file/network I/O, time, randomness, database access, or input graph mutation.
- Weighted support and attack edges are applied as `edge.weight * child.final_strength`.
- Probabilistic sum implements `v1 + v2 - v1 * v2`, recursively/iteratively for any number of values.
- DF-QuAD combination implements:
  - if attack >= support: `base - base * abs(support - attack)`
  - if attack < support: `base + (1 - base) * abs(support - attack)`
- Cycles are rejected with a clear `ValueError`.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 4 commit is created with message `feat(step-4): add df-quad qbaf semantics`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_semantics.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Semantics Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_qbaf_semantics.py`

- [x] **Step 1: Write the failing tests**

Tests cover deterministic formula values, probabilistic sum aggregation, support/attack monotonicity, input graph immutability, and cycle rejection.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because `DFQuADSemantics` and formula helpers do not exist yet.

### Task 2: Add DF-QuAD Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/qbaf/semantics.py`
- Modify: `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`

- [x] **Step 1: Implement formula helpers**

Add `probabilistic_sum` and `combine_df_quad` as pure functions that validate values are in `[0, 1]`.

- [x] **Step 2: Implement semantics strategy**

Add `Semantics` and `DFQuADSemantics.propagate(graph)`. Compute every node recursively from incoming edges, detect cycles, and return a new `QBAFGraph` with updated `final_strength` values.

### Task 3: Verify And Commit

**Files:**
- All Step 4 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [ ] **Step 4: Commit**

Stage Step 4 files and commit with:

```bash
git commit -m "feat(step-4): add df-quad qbaf semantics"
```
