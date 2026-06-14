# QBAF Step 13 Persistence And API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistence, retrieval API, and structured trace output for QBAF runs.

**Architecture:** Persistence lives under `coordinator/app/orchestration/repository.py` behind a `QBAFRunRepository` protocol. Tests use `InMemoryQBAFRunRepository`; a `Neo4jQBAFRunRepository` adapter boundary is present without adding a driver dependency. FastAPI routes live in `app/api/qbaf.py` and are included from `app/main.py`.

**Tech Stack:** Python 3.12, dataclasses, FastAPI/Pydantic already in the app, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/orchestration/repository.py`: run record dataclass, repository protocol, in-memory repository, Neo4j adapter boundary, trace serialization.
- Modify `apps/dialectical-engine/coordinator/app/orchestration/__init__.py`: public repository exports.
- Create `apps/dialectical-engine/coordinator/app/api/qbaf.py`: QBAF run start/fetch endpoints.
- Modify `apps/dialectical-engine/coordinator/app/main.py`: include QBAF router.
- Create `apps/dialectical-engine/coordinator/tests/test_qbaf_api.py`: repository/API tests.
- Modify `apps/dialectical-engine/coordinator/tests/test_providers.py`: include API boundary if needed.
- Create `docs/superpowers/plans/2026-06-14-qbaf-step-13-persistence-api.md`: this plan.

## Step Goal, Files, DoD, And Tests

Step goal: persist a QBAF run and fetch its graph JSON through the API.

Files touched:

- `apps/dialectical-engine/coordinator/app/orchestration/repository.py`
- `apps/dialectical-engine/coordinator/app/orchestration/__init__.py`
- `apps/dialectical-engine/coordinator/app/api/qbaf.py`
- `apps/dialectical-engine/coordinator/app/main.py`
- `apps/dialectical-engine/coordinator/tests/test_qbaf_api.py`
- `apps/dialectical-engine/coordinator/tests/test_providers.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-13-persistence-api.md`

Definition of Done:

- `QBAFRunRecord` stores id, topic, graph JSON, root confidence, root history, decision trace, and created timestamp.
- `InMemoryQBAFRunRepository` can save/get/list records.
- `Neo4jQBAFRunRepository` exists behind the repository protocol without adding a dependency.
- `POST /api/qbaf/runs` starts a run, persists it, and returns the record JSON.
- `GET /api/qbaf/runs/{run_id}` returns the persisted graph JSON and trace.
- POST requires the existing user bearer token.
- API tests do not call live providers.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 13 commit is created with message `feat(step-13): add qbaf run persistence api`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_qbaf_api.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Persistence/API Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_qbaf_api.py`

- [x] **Step 1: Write the failing tests**

Tests cover repository save/get, authenticated POST run creation, unauthenticated write rejection, and GET retrieval.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because repository and QBAF API route do not exist yet.

### Task 2: Add Repository And API

**Files:**
- Create/modify all Step 13 files listed above.

- [x] **Step 1: Implement repository layer**

Add record serialization, in-memory repository, and Neo4j adapter boundary.

- [x] **Step 2: Implement FastAPI route**

Add POST and GET endpoints with source payload validation and dependency hooks for tests.

- [x] **Step 3: Wire route into app**

Include the QBAF router from `app/main.py`.

### Task 3: Verify And Commit

**Files:**
- All Step 13 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [ ] **Step 4: Commit**

Stage Step 13 files and commit with:

```bash
git commit -m "feat(step-13): add qbaf run persistence api"
```
