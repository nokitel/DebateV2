# QBAF Step 14 Evaluation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an evaluation harness and decision gate comparing debate scores against self-consistency baseline scores.

**Architecture:** Evaluation lives under `coordinator/app/evaluation/`. The harness is deterministic and accepts labeled examples plus matched debate/baseline score maps or callables. It reports accuracy, expected calibration error (ECE), Kialo impact alignment, baseline delta, and whether the debate layer beats self-consistency.

**Tech Stack:** Python 3.12, dataclasses, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/evaluation/__init__.py`: public evaluation exports.
- Create `apps/dialectical-engine/coordinator/app/evaluation/harness.py`: examples, metrics, report, and decision gate.
- Create `apps/dialectical-engine/coordinator/tests/test_evaluation_harness.py`: metric and decision gate tests.
- Modify `apps/dialectical-engine/coordinator/tests/test_providers.py`: include `app/evaluation` in vendor-boundary checks.
- Create `docs/superpowers/plans/2026-06-14-qbaf-step-14-evaluation.md`: this plan.

## Step Goal, Files, DoD, And Tests

Step goal: output accuracy + ECE + debate-vs-baseline delta and recommendation.

Files touched:

- `apps/dialectical-engine/coordinator/app/evaluation/__init__.py`
- `apps/dialectical-engine/coordinator/app/evaluation/harness.py`
- `apps/dialectical-engine/coordinator/tests/test_evaluation_harness.py`
- `apps/dialectical-engine/coordinator/tests/test_providers.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-14-evaluation.md`

Definition of Done:

- Harness evaluates a labeled QA-style set.
- Harness supports Kialo-style examples with human impact votes.
- Report includes debate accuracy, baseline accuracy, baseline delta, debate ECE, baseline ECE, and Kialo impact alignment.
- Decision gate flags whether debate beats self-consistency.
- If debate does not beat self-consistency, recommendation says to simplify toward the baseline and invest in evidence.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 14 commit is created with message `feat(step-14): add evaluation decision gate`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_evaluation_harness.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Evaluation Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_evaluation_harness.py`
- Modify: `apps/dialectical-engine/coordinator/tests/test_providers.py`

- [x] **Step 1: Write the failing tests**

Tests cover accuracy/ECE computation, Kialo impact alignment, positive debate delta, and simplification recommendation when debate does not beat baseline.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because `app.evaluation` does not exist yet.

### Task 2: Add Evaluation Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/evaluation/__init__.py`
- Create: `apps/dialectical-engine/coordinator/app/evaluation/harness.py`

- [x] **Step 1: Implement metrics**

Add accuracy, ECE, and Kialo impact alignment helpers.

- [x] **Step 2: Implement report and decision gate**

Return a structured report with recommendation.

### Task 3: Verify And Commit

**Files:**
- All Step 14 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [x] **Step 4: Commit**

Stage Step 14 files and commit with:

```bash
git commit -m "feat(step-14): add evaluation decision gate"
```
