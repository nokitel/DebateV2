# QBAF Step 9 Anti-Obfuscation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a prover-estimator anti-obfuscation check for large or flagged argument nodes.

**Architecture:** The checker lives under `coordinator/app/metareasoning/`. It does not run debate itself; it detects nodes that need decomposition, calls only the configured `estimator` role through `ProviderRegistry`, parses JSON subclaim probabilities, and caps the parent node's support if any subclaim falls below the undefendable threshold.

**Tech Stack:** Python 3.12, dataclasses, standard-library JSON, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/metareasoning/__init__.py`: public metareasoning exports.
- Create `apps/dialectical-engine/coordinator/app/metareasoning/anti_obfuscation.py`: subclaim parser and checker.
- Create `apps/dialectical-engine/coordinator/tests/test_anti_obfuscation.py`: trigger/parser/cap tests.
- Modify `apps/dialectical-engine/coordinator/tests/test_providers.py`: include `app/metareasoning` in vendor-boundary checks.
- Create `docs/superpowers/plans/2026-06-14-qbaf-step-9-anti-obfuscation.md`: this plan.

## Step Goal, Files, DoD, And Tests

Step goal: cap a parent node when an estimator marks any subclaim undefendable.

Files touched:

- `apps/dialectical-engine/coordinator/app/metareasoning/__init__.py`
- `apps/dialectical-engine/coordinator/app/metareasoning/anti_obfuscation.py`
- `apps/dialectical-engine/coordinator/tests/test_anti_obfuscation.py`
- `apps/dialectical-engine/coordinator/tests/test_providers.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-9-anti-obfuscation.md`

Definition of Done:

- Checker triggers on nodes marked with a big-argument caveat or long text.
- Unflagged nodes skip without provider calls.
- Triggered nodes call only the `estimator` role through `ProviderRegistry`.
- Estimator JSON must include subclaims with probabilities in `[0, 1]`.
- If any subclaim probability is below the threshold, parent `base_score` and `final_strength` are capped.
- Undefendable subclaims are surfaced as caveats.
- Vendor-boundary static test covers `app/metareasoning`.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 9 commit is created with message `feat(step-9): add anti-obfuscation check`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_anti_obfuscation.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Anti-Obfuscation Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_anti_obfuscation.py`
- Modify: `apps/dialectical-engine/coordinator/tests/test_providers.py`

- [x] **Step 1: Write the failing tests**

Tests cover no-op skip behavior, estimator call path, invalid JSON rejection, and parent score caps.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because `app.metareasoning` does not exist yet.

### Task 2: Add Checker Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/metareasoning/__init__.py`
- Create: `apps/dialectical-engine/coordinator/app/metareasoning/anti_obfuscation.py`

- [x] **Step 1: Implement parser and result dataclasses**

Add subclaim parsing with strict probability validation.

- [x] **Step 2: Implement trigger and cap logic**

Skip unflagged nodes, call estimator for triggered nodes, and cap parent support when needed.

### Task 3: Verify And Commit

**Files:**
- All Step 9 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [ ] **Step 4: Commit**

Stage Step 9 files and commit with:

```bash
git commit -m "feat(step-9): add anti-obfuscation check"
```
