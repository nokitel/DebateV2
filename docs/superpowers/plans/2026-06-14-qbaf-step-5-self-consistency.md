# QBAF Step 5 Self-Consistency Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add provider-backed self-consistency scoring that samples an assigned agent 3-5 times and reduces the samples into a base score, edge weight, and uncertainty.

**Architecture:** The scorer lives in `coordinator/app/scoring/` and depends only on the Proposal B provider registry plus QBAF validation helpers. It calls `ProviderRegistry.generate_for_role`, requests JSON, parses each response into a score sample, and returns an immutable result object. Tests use `FakeProvider` sequences only.

**Tech Stack:** Python 3.12, dataclasses, standard-library JSON/statistics, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/scoring/__init__.py`: public scoring exports.
- Create `apps/dialectical-engine/coordinator/app/scoring/self_consistency.py`: score sample dataclasses, parser, reducer, and scorer.
- Modify `apps/dialectical-engine/coordinator/app/providers/fake.py`: deterministic response sequences and call capture for provider-layer tests.
- Create `apps/dialectical-engine/coordinator/tests/test_self_consistency_scoring.py`: self-consistency tests.
- Modify `apps/dialectical-engine/coordinator/tests/test_providers.py`: include `app/scoring` in vendor-boundary static checks.

## Step Goal, Files, DoD, And Tests

Step goal: score a claim with deterministic provider samples and return calibrated `base_score`, `edge_weight`, and uncertainty.

Files touched:

- `apps/dialectical-engine/coordinator/app/scoring/__init__.py`
- `apps/dialectical-engine/coordinator/app/scoring/self_consistency.py`
- `apps/dialectical-engine/coordinator/app/providers/fake.py`
- `apps/dialectical-engine/coordinator/tests/test_self_consistency_scoring.py`
- `apps/dialectical-engine/coordinator/tests/test_providers.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-5-self-consistency.md`

Definition of Done:

- `SelfConsistencyScorer` samples one configured role 3-5 times through `ProviderRegistry`.
- No test or scorer path calls a live API.
- Provider responses must be valid JSON with `base_score`/`edge_weight` or `tau`/`weight` aliases.
- Parsed scores and weights are validated in `[0, 1]`.
- Returned `base_score` and `edge_weight` are sample means.
- Returned `uncertainty` is the maximum sample spread across base scores and edge weights.
- `FakeProvider` can return deterministic response sequences and records calls.
- Vendor-boundary static test covers `app/scoring`.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 5 commit is created with message `feat(step-5): add self-consistency scoring`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_self_consistency_scoring.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Self-Consistency Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_self_consistency_scoring.py`
- Modify: `apps/dialectical-engine/coordinator/tests/test_providers.py`

- [x] **Step 1: Write the failing tests**

Tests cover deterministic fake-provider sampling, JSON parsing aliases, range validation, sample-count validation, call capture, and vendor-boundary static checks.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because `app.scoring` does not exist yet.

### Task 2: Add Scoring Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/scoring/__init__.py`
- Create: `apps/dialectical-engine/coordinator/app/scoring/self_consistency.py`
- Modify: `apps/dialectical-engine/coordinator/app/providers/fake.py`

- [x] **Step 1: Implement deterministic fake response sequences**

Allow `FakeProvider` responses to be either a string or a list of strings, using the next response on each call and repeating the final response after the sequence is exhausted.

- [x] **Step 2: Implement score parsing and reduction**

Add `ScoreSample`, `SelfConsistencyResult`, `parse_score_sample`, and `SelfConsistencyScorer`.

### Task 3: Verify And Commit

**Files:**
- All Step 5 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [x] **Step 4: Commit**

Stage Step 5 files and commit with:

```bash
git commit -m "feat(step-5): add self-consistency scoring"
```
