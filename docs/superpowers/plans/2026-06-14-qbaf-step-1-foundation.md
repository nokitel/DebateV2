# QBAF Step 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Proposal B Step 1 foundation inside the existing Dialectical Engine app.

**Architecture:** Add the first QBAF coordinator package without changing runtime orchestration. Record Proposal B invariants in the app-level `AGENTS.md`, and extend coordinator config with small `.env` loading for `OPENAI_API_KEY` and `OPENAI_MODEL` so Step 2 can build the Codex-compatible provider facade without revisiting foundation.

**Tech Stack:** Python 3.12, pytest, existing FastAPI coordinator package, no new dependencies.

---

## File Structure

- Modify `apps/dialectical-engine/AGENTS.md`: add Proposal B invariants and step discipline for future work.
- Modify `apps/dialectical-engine/coordinator/app/core/config.py`: add a tiny `.env` parser and `Settings.openai_api_key` / `Settings.openai_model`.
- Create `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`: introduce the QBAF package marker used by Step 1 tests.
- Create `apps/dialectical-engine/coordinator/tests/test_qbaf_foundation.py`: focused tests for guardrails, package wiring, and `.env` loading.

## Step Goal, Files, DoD, And Tests

Step goal: establish the QBAF foundation and guardrails without adding provider calls or graph semantics yet.

Files touched:

- `apps/dialectical-engine/AGENTS.md`
- `apps/dialectical-engine/coordinator/app/core/config.py`
- `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`
- `apps/dialectical-engine/coordinator/tests/test_qbaf_foundation.py`

Definition of Done:

- QBAF package imports successfully from coordinator tests.
- App-level `AGENTS.md` records the non-negotiable Proposal B invariants.
- Coordinator config loads `OPENAI_API_KEY` and `OPENAI_MODEL` from a local `.env` file when environment variables are not already set.
- No paid or live model call is introduced.
- Focused tests pass, then full `make test` is attempted.
- Step 1 commit is created with message `feat(step-1): add qbaf foundation guardrails`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_foundation.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test
```

---

### Task 1: Add Failing Foundation Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_qbaf_foundation.py`

- [x] **Step 1: Write the failing test**

Create `apps/dialectical-engine/coordinator/tests/test_qbaf_foundation.py`:

```python
from __future__ import annotations

from pathlib import Path

from app.core.config import load_settings


ENGINE_ROOT = Path(__file__).resolve().parents[2]


def test_qbaf_package_exposes_step_1_marker() -> None:
    from app import qbaf

    assert qbaf.FOUNDATION_STEP == "proposal-b-step-1"


def test_agents_file_records_proposal_b_invariants() -> None:
    agents_text = (ENGINE_ROOT / "AGENTS.md").read_text()

    required_phrases = [
        "Provider-agnostic agents",
        "OpenAI/Codex is the first real adapter",
        "Pure propagation",
        "Swappable semantics",
        "Every leaf is gated by the evidence subsystem",
        "Anonymize debate sources",
        "Skeptic certifies no unaddressed attack remains",
        "Confidence-driven, cost-soft",
    ]
    for phrase in required_phrases:
        assert phrase in agents_text


def test_coordinator_config_loads_openai_values_from_dotenv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=env-file-key\n"
        "OPENAI_MODEL=codex-gpt-5.5\n"
    )

    settings = load_settings(path=tmp_path / "missing-coordinator.toml")

    assert settings.openai_api_key == "env-file-key"
    assert settings.openai_model == "codex-gpt-5.5"
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_foundation.py -q
```

Expected: FAIL because `app.qbaf` does not exist and `Settings` has no `openai_api_key` / `openai_model` fields.

---

### Task 2: Record Proposal B Guardrails

**Files:**
- Modify: `apps/dialectical-engine/AGENTS.md`

- [x] **Step 1: Add Proposal B guardrails**

Append this section to `apps/dialectical-engine/AGENTS.md`:

```markdown
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
```

- [x] **Step 2: Re-run the guardrail assertion**

Run:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_foundation.py::test_agents_file_records_proposal_b_invariants -q
```

Expected: PASS.

---

### Task 3: Add QBAF Package Marker

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`

- [x] **Step 1: Create the package marker**

Create `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`:

```python
from __future__ import annotations

FOUNDATION_STEP = "proposal-b-step-1"

__all__ = ["FOUNDATION_STEP"]
```

- [x] **Step 2: Re-run the import assertion**

Run:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_foundation.py::test_qbaf_package_exposes_step_1_marker -q
```

Expected: PASS.

---

### Task 4: Add `.env` Loading To Coordinator Config

**Files:**
- Modify: `apps/dialectical-engine/coordinator/app/core/config.py`

- [x] **Step 1: Add settings fields**

Update the `Settings` dataclass:

```python
@dataclass
class Settings:
    home: Path = DEFAULT_COORDINATOR_DIR
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    user_token: str | None = None
    public_base_url: str = "http://localhost:8000"
    web_origin: str = "http://localhost:3000"
    public_rate_limit_per_minute: int = 100
    worker_poll_seconds: int = 30
    worker_offline_seconds: int = 90
    job_fallback_seconds: int = 60
    routing: dict[str, dict[str, Any]] = field(default_factory=lambda: deepcopy(DEFAULT_ROUTING))
    grok_monthly_cap_usd: float = 25.0
    openai_api_key: str | None = None
    openai_model: str | None = None
```

- [x] **Step 2: Add a tiny dotenv loader**

Add this helper above `load_settings`:

```python
def load_dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        cleaned = value.strip().strip('"').strip("'")
        values[key] = cleaned
    return values
```

- [x] **Step 3: Use `.env` values without overriding real env vars**

At the start of `load_settings`, after resolving `path`, add:

```python
    dotenv_values = load_dotenv_values(Path(".env"))
```

Then set the new fields near the existing environment-backed settings:

```python
    settings.openai_api_key = os.getenv("OPENAI_API_KEY", dotenv_values.get("OPENAI_API_KEY"))
    settings.openai_model = clean_string(
        os.getenv("OPENAI_MODEL", dotenv_values.get("OPENAI_MODEL")),
        settings.openai_model or "codex-gpt-5.5",
    )
```

- [x] **Step 4: Re-run the dotenv assertion**

Run:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_foundation.py::test_coordinator_config_loads_openai_values_from_dotenv -q
```

Expected: PASS.

---

### Task 5: Run Step 1 Verification And Commit

**Files:**
- Verify all Step 1 files.

- [x] **Step 1: Run focused Step 1 tests**

Run:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_foundation.py -q
```

Expected: all tests PASS.

- [x] **Step 2: Attempt full app tests**

Run:

```bash
cd apps/dialectical-engine
make test
```

Expected: full tests PASS. If the local environment lacks dependencies or a Python runtime compatible with the Makefile, record the exact failure and keep the focused test result as the Step 1 proof.

- [x] **Step 3: Review git diff**

Run:

```bash
git diff -- apps/dialectical-engine/AGENTS.md apps/dialectical-engine/coordinator/app/core/config.py apps/dialectical-engine/coordinator/app/qbaf/__init__.py apps/dialectical-engine/coordinator/tests/test_qbaf_foundation.py
```

Expected: only Step 1 foundation changes appear.

- [x] **Step 4: Commit Step 1**

Run:

```bash
git add apps/dialectical-engine/AGENTS.md apps/dialectical-engine/coordinator/app/core/config.py apps/dialectical-engine/coordinator/app/qbaf/__init__.py apps/dialectical-engine/coordinator/tests/test_qbaf_foundation.py docs/superpowers/plans/2026-06-14-qbaf-step-1-foundation.md
git commit -m "feat(step-1): add qbaf foundation guardrails"
```

Expected: commit succeeds.
