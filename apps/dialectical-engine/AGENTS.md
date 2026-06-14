# AGENTS.md

This directory is the Dialectical Engine application, not the AI Harness
skeleton.

## Local Workflow

- Use the app-level `Makefile` from this directory.
- Prefer the simplified single-Mac path unless the task explicitly returns to
  two-worker production acceptance.
- Use `make setup-status` for the current local runtime, model auth, hosting,
  and manual checklist state.
- Use `make interactive-manual-setup` only from a normal Terminal because it
  starts browser/account login flows.

## Verification

For focused setup changes, run the narrow tests that cover touched scripts.
Common checks:

```sh
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib \
/Users/stefannour/Documents/Debate\ V2/dialectical-engine/.venv313/bin/python -m pytest -p pytest_asyncio.plugin \
  coordinator/tests/test_hosting_status.py \
  coordinator/tests/test_makefile_targets.py \
  coordinator/tests/test_status_report.py -q
```

When working from the original active local tree at
`/Users/stefannour/Documents/Debate V2/dialectical-engine`, use that tree's
`.venv313/bin/python` and run `make setup-status` there to verify the live Mac
services.

## Proposal B QBAF Guardrails

When working on the Debate-Weighted QBAF goal, keep these invariants current:

- **Provider-agnostic agents.** New scoring, debate, evidence, metareasoning,
  and orchestration code must call the Proposal B `LLMProvider` interface
  instead of importing or invoking model SDKs or CLIs directly.
- **OpenAI/Codex is the first real adapter.** The first live provider path may
  use Codex, but the second provider must be addable through `providers/` plus
  configuration without changing agent, scorer, evidence, or QBAF semantics
  code.
- **Pure propagation.** QBAF graph-scoring math must contain no model calls,
  file/network I/O, time, randomness, or database access.
- **Swappable semantics.** DF-QuAD is the default gradual semantics and must
  live behind a strategy interface so another semantics implementation can
  replace it later.
- **Every leaf is gated by the evidence subsystem.** Evidence leaves that cite
  sources receive base scores from the evidence pipeline, not directly from a
  model assertion.
- **Anonymize debate sources.** Strip agent identity before another debate role
  reads prior turns.
- **Skeptic certifies no unaddressed attack remains.** A node is not converged
  until the skeptic hook passes.
- **Confidence-driven, cost-soft.** Stop conditions are driven by convergence,
  unresolved caveats, and skeptic certification; cost is a soft tie-breaker.

Work one proposal Step at a time. Each Step starts with the goal, touched files,
Definition of Done, exact tests, and a short plan; each Step ends with tests and
a clear commit.
