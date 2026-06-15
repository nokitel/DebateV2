# Subscription Loop Workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tmux-backed Claude and Gemini subscription loops and switch `dezbatere.ro` routing to use them.

**Architecture:** A Python helper owns worker registration, polling, streaming, completion, routing updates, and tmux launch commands. Claude and Gemini use reliable one-shot CLI invocations inside persistent tmux shell loops; the checked-in Claude Code skill remains available for interactive `/loop` operation. The coordinator keeps using the existing worker/job APIs.

**Tech Stack:** FastAPI coordinator APIs, existing worker client/config code, Python scripts, tmux, Claude Code skills, Gemini CLI headless mode, Make targets.

---

### Task 1: Protocol Tests

**Files:**
- Create: `coordinator/tests/test_subscription_loop.py`

- [x] Write failing tests for route replacement, production enabled model selection, Claude job instruction rendering, result parsing, Gemini command construction, and Make target exposure.
- [x] Run `cd coordinator && PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_subscription_loop.py -v` and confirm the tests fail because the helper does not exist.

### Task 2: Loop Helper

**Files:**
- Create: `scripts/subscription_loop.py`
- Create: `scripts/dezbatere_loop_helper.sh`

- [x] Implement provider defaults, result parsing, route replacement, worker registration, one-job claim, completion/failure, Gemini one-shot execution, routing configuration, and tmux launch/status/stop commands.
- [x] Run the focused tests and confirm they pass.

### Task 3: Claude Skill And Make Targets

**Files:**
- Create: `.claude/skills/dezbatere-loop/SKILL.md`
- Modify: `Makefile`
- Modify: `coordinator/tests/test_makefile_targets.py`

- [x] Add a Claude Code skill that runs one helper iteration and posts exactly one result.
- [x] Add Make targets for routing, starting/stopping/statusing loops, and provider-specific loop starts.
- [x] Run focused tests for Makefile and subscription loop behavior.

### Task 4: Production Cutover

**Files:**
- Runtime: `https://dezbatere.ro/api/settings`
- Runtime: tmux sessions `dialectical-claude-loop` and `dialectical-gemini-loop`

- [x] Apply subscription routing to `dezbatere.ro` with the user token.
- [x] Ensure loop workers are registered with dedicated config files.
- [x] Start tmux sessions.
- [x] Verify `https://dezbatere.ro/api/backends/status` shows loop workers online or degraded with clear evidence.

### Task 5: Verification And Commit

**Files:**
- Git worktree

- [x] Run focused Python tests.
- [x] Run relevant local status/acceptance gates that cover website health and worker visibility.
- [x] Inspect runtime state for routing and tmux sessions.
- [x] Commit all code and docs changes to Git.
