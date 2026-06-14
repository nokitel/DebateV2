# QBAF Step 7 Agent Roster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a config-driven agent roster, lightweight topic routing, and a skeptic certification hook.

**Architecture:** Roster code lives in `coordinator/app/debate/roster.py` and reads role configuration from the existing `ProviderRegistry`. It does not call providers. A keyword classifier flags domain/statistical claims, routes `specialist` and `methodologist`, and always includes the `skeptic` role. The skeptic hook checks node caveats/transcript for unresolved attacks.

**Tech Stack:** Python 3.12, dataclasses, standard library only, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/debate/roster.py`: role metadata, classifier, roster routing, skeptic hook.
- Modify `apps/dialectical-engine/coordinator/app/debate/__init__.py`: public roster exports.
- Create `apps/dialectical-engine/coordinator/tests/test_agent_roster.py`: roster/routing/skeptic tests.
- Create `docs/superpowers/plans/2026-06-14-qbaf-step-7-agent-roster.md`: this plan.

## Step Goal, Files, DoD, And Tests

Step goal: route configured debate roles for a claim and expose skeptic certification.

Files touched:

- `apps/dialectical-engine/coordinator/app/debate/roster.py`
- `apps/dialectical-engine/coordinator/app/debate/__init__.py`
- `apps/dialectical-engine/coordinator/tests/test_agent_roster.py`
- `docs/superpowers/plans/2026-06-14-qbaf-step-7-agent-roster.md`

Definition of Done:

- `AgentRoster.from_registry` returns role metadata from `ProviderRegistry.agents`.
- `specialist`, `methodologist`, and `skeptic` roles are config-driven.
- Topic classifier flags domain topics and statistical/methodological topics.
- Specialist fires on flagged domain topics.
- Methodologist fires on statistical/methodological topics.
- Skeptic is always routed.
- `Skeptic.certify_no_unaddressed_attack(node) -> bool` returns false when attack caveats or transcript markers remain.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 7 commit is created with message `feat(step-7): add agent roster routing`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_agent_roster.py tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Roster Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_agent_roster.py`

- [x] **Step 1: Write the failing tests**

Tests cover registry-derived role metadata, topic routing, default skeptic routing, and skeptic attack certification.

- [x] **Step 2: Run focused tests to verify they fail**

Expected: FAIL because roster exports do not exist yet.

### Task 2: Add Roster Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/debate/roster.py`
- Modify: `apps/dialectical-engine/coordinator/app/debate/__init__.py`

- [x] **Step 1: Implement role metadata and classifier**

Add immutable role metadata and a keyword classifier for domain/statistical flags.

- [x] **Step 2: Implement roster routing and skeptic hook**

Route `specialist`, `methodologist`, and `skeptic` from config and expose attack certification.

### Task 3: Verify And Commit

**Files:**
- All Step 7 files above.

- [x] **Step 1: Run focused tests**

Run the exact focused test command above.

- [x] **Step 2: Run full app tests**

Run the full app test command above.

- [x] **Step 3: Review diff**

Check `git diff --stat` and `git diff`.

- [x] **Step 4: Commit**

Stage Step 7 files and commit with:

```bash
git commit -m "feat(step-7): add agent roster routing"
```
