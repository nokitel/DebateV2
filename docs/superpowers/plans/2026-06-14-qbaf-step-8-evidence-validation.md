# QBAF Step 8 Evidence Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic evidence-validation subsystem for grounding evidence leaves.

**Architecture:** Evidence code lives in `coordinator/app/evidence/`. The v1 pipeline is deterministic and local: source metadata carries retraction/quality/corroboration/statistical signals, and source text is checked for a lightweight SUPPORTS/REFUTES/NOINFO entailment label. This gives the orchestrator a real gated leaf-scoring surface now, while leaving DOI resolution and live SciFact-style retrieval for future adapters.

**Tech Stack:** Python 3.12, dataclasses, standard-library text processing, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/evidence/model.py`: source/result dataclasses and labels.
- Create `apps/dialectical-engine/coordinator/app/evidence/entailment.py`: deterministic claim/source entailment check.
- Create `apps/dialectical-engine/coordinator/app/evidence/quality.py`: quality multiplier and caveats.
- Create `apps/dialectical-engine/coordinator/app/evidence/retraction.py`: retraction check.
- Create `apps/dialectical-engine/coordinator/app/evidence/pipeline.py`: score composition and evidence-leaf grounding.
- Modify `apps/dialectical-engine/coordinator/app/evidence/__init__.py`: public evidence exports.
- Create `apps/dialectical-engine/coordinator/tests/test_evidence_pipeline.py`: evidence validation tests.
- Create `docs/superpowers/plans/2026-06-14-qbaf-step-8-evidence-validation.md`: this plan.

## Step Goal, Files, DoD, And Tests

Step goal: score an evidence leaf from source metadata/text instead of model assertion.

Files touched:

- `apps/dialectical-engine/coordinator/app/evidence/model.py`
- `apps/dialectical-engine/coordinator/app/evidence/entailment.py`
- `apps/dialectical-engine/coordinator/app/evidence/quality.py`
- `apps/dialectical-engine/coordinator/app/evidence/retraction.py`
- `apps/dialectical-engine/coordinator/app/evidence/pipeline.py`
- `apps/dialectical-engine/coordinator/app/evidence/__init__.py`
- `apps/dialectical-engine/coordinator/tests/test_evidence_pipeline.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-8-evidence-validation.md`

Definition of Done:

- `SourceRecord` captures source text, retraction status, quality grade, corroboration count, and statistical flags.
- Entailment check returns SUPPORTS, REFUTES, or NOINFO deterministically.
- Retraction check caps score near zero and records a caveat.
- NOINFO source collapses support near zero and records a caveat.
- Quality grade and statistical flags affect score/caveats.
- `EvidenceValidationPipeline.ground_leaf(node, source)` updates only evidence leaves.
- No model, network, file, database, time, or randomness is used.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 8 commit is created with message `feat(step-8): add evidence validation pipeline`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_evidence_pipeline.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Evidence Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_evidence_pipeline.py`

- [x] **Step 1: Write the failing tests**

Tests cover retraction caps, NOINFO collapse, quality/statistical caveats, entailment labels, and evidence-leaf grounding.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because the evidence pipeline modules do not exist yet.

### Task 2: Add Evidence Implementation

**Files:**
- Create/modify all evidence files listed above.

- [x] **Step 1: Implement independent checks**

Add source/result dataclasses, entailment labels, retraction check, and quality scoring.

- [x] **Step 2: Implement pipeline composition**

Compose checks into a final `EvidenceScore` and `ground_leaf` helper.

### Task 3: Verify And Commit

**Files:**
- All Step 8 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [x] **Step 4: Commit**

Stage Step 8 files and commit with:

```bash
git commit -m "feat(step-8): add evidence validation pipeline"
```
