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
