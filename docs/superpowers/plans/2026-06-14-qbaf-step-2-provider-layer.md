# QBAF Step 2 Provider Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-agnostic LLM layer for Proposal B roles, with Codex as the first real provider and a deterministic fake provider for tests.

**Architecture:** New engine code talks to `LLMProvider` through `ProviderRegistry.generate_for_role()`. Role config is loaded from `apps/dialectical-engine/config/agents.yaml`; each role inherits defaults and can switch providers by config. The Codex provider shells out through the Codex CLI, while tests use `FakeProvider` and never invoke a live model.

**Tech Stack:** Python 3.12, pytest, PyYAML from existing dev requirements, subprocess for the Codex CLI adapter, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/config/agents.yaml`: Proposal B role-to-provider defaults.
- Create `apps/dialectical-engine/coordinator/app/providers/base.py`: `LLMResponse`, `LLMProvider`, `ProviderError`.
- Create `apps/dialectical-engine/coordinator/app/providers/fake.py`: deterministic test provider.
- Create `apps/dialectical-engine/coordinator/app/providers/codex_cli.py`: Codex CLI provider and command builder.
- Create `apps/dialectical-engine/coordinator/app/providers/registry.py`: config loader, env interpolation, role registry.
- Create `apps/dialectical-engine/coordinator/app/providers/__init__.py`: public exports.
- Create `apps/dialectical-engine/coordinator/tests/test_providers.py`: focused provider tests.

## Step Goal, Files, DoD, And Tests

Step goal: all Proposal B model-dependent code can call through one role/provider interface, with Codex available as the first real adapter and fake provider available for deterministic tests.

Files touched:

- `apps/dialectical-engine/config/agents.yaml`
- `apps/dialectical-engine/coordinator/app/providers/base.py`
- `apps/dialectical-engine/coordinator/app/providers/fake.py`
- `apps/dialectical-engine/coordinator/app/providers/codex_cli.py`
- `apps/dialectical-engine/coordinator/app/providers/registry.py`
- `apps/dialectical-engine/coordinator/app/providers/__init__.py`
- `apps/dialectical-engine/coordinator/tests/test_providers.py`

Definition of Done:

- `LLMProvider` protocol and `LLMResponse` dataclass exist.
- `ProviderRegistry` loads `config/agents.yaml`, merges defaults, and resolves `${OPENAI_MODEL}` from `load_settings()`.
- `FakeProvider` returns deterministic responses through the same `generate_for_role()` call path used by real providers.
- `CodexCliProvider` builds and can execute a Codex CLI command through the provider interface; tests cover command construction without live model calls.
- Static tests prove Proposal B engine modules outside `providers/` do not reference vendor names or model CLIs.
- Focused provider tests pass, then full `make test` passes on Python 3.12.
- Step 2 commit is created with message `feat(step-2): add qbaf provider abstraction`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin tests/test_providers.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing Provider Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_providers.py`

- [x] **Step 1: Write the failing tests**

Create `apps/dialectical-engine/coordinator/tests/test_providers.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from app.providers import (
    AgentConfig,
    CodexCliProvider,
    FakeProvider,
    LLMResponse,
    ProviderRegistry,
    load_agent_configs,
)


ENGINE_ROOT = Path(__file__).resolve().parents[2]


def test_agent_config_loads_defaults_and_openai_model_from_settings(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "codex-test-model")

    configs = load_agent_configs(ENGINE_ROOT / "config" / "agents.yaml")

    assert configs["proponent"] == AgentConfig(
        provider="codex",
        model="codex-test-model",
        temperature=0.2,
        max_tokens=None,
    )
    assert configs["judge"].temperature == 0.0
    assert configs["estimator"].temperature == 0.0


def test_registry_uses_fake_provider_without_changing_call_path() -> None:
    registry = ProviderRegistry(
        agents={
            "judge": AgentConfig(provider="fake", model="fake-model", temperature=0.0, max_tokens=128)
        },
        providers={
            "fake": FakeProvider({"judge": "score=0.73"}),
        },
    )

    response = registry.generate_for_role(
        "judge",
        [{"role": "user", "content": "score this claim"}],
        response_format="json",
    )

    assert response == LLMResponse(
        text="score=0.73",
        raw={"provider": "fake", "model": "fake-model", "role": "judge"},
        usage={"tokens_out": 1},
    )


def test_registry_rejects_unknown_role() -> None:
    registry = ProviderRegistry(agents={}, providers={"fake": FakeProvider()})

    with pytest.raises(KeyError, match="No agent configured for role specialist"):
        registry.generate_for_role("specialist", [{"role": "user", "content": "hello"}])


def test_codex_provider_builds_cli_command_without_live_call() -> None:
    provider = CodexCliProvider(executable="codex")

    command = provider.command(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "user"}],
        model="gpt-5.5",
        max_tokens=200,
        response_format="json",
    )

    assert command[:5] == ["codex", "exec", "--skip-git-repo-check", "--sandbox", "workspace-write"]
    assert "--model" in command
    assert "gpt-5.5" in command
    assert "Return only valid JSON." in command[-1]
    assert "Keep the answer under 200 tokens." in command[-1]


def test_proposal_engine_modules_outside_providers_do_not_reference_vendors() -> None:
    checked_roots = [
        ENGINE_ROOT / "coordinator" / "app" / "qbaf",
    ]
    forbidden = ["openai", "codex", "anthropic", "claude", "gemini", "grok", "ollama"]
    offenders: list[str] = []
    for root in checked_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text().lower()
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.relative_to(ENGINE_ROOT)} contains {token}")

    assert offenders == []
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin tests/test_providers.py -q
```

Expected: FAIL because `app.providers` and `config/agents.yaml` do not exist.

---

### Task 2: Add Agent Config File

**Files:**
- Create: `apps/dialectical-engine/config/agents.yaml`

- [x] **Step 1: Create the role config**

Create `apps/dialectical-engine/config/agents.yaml`:

```yaml
defaults:
  provider: codex
  model: ${OPENAI_MODEL}
  temperature: 0.2
agents:
  proponent: {}
  opponent: {}
  judge:
    temperature: 0.0
  specialist: {}
  methodologist: {}
  skeptic: {}
  estimator:
    temperature: 0.0
```

---

### Task 3: Add Provider Base Types

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/providers/base.py`
- Create: `apps/dialectical-engine/coordinator/app/providers/__init__.py`

- [x] **Step 1: Create base provider contracts**

Create `apps/dialectical-engine/coordinator/app/providers/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMResponse:
    text: str
    raw: dict
    usage: dict | None


class ProviderError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def generate(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str | None = None,
        role: str | None = None,
    ) -> LLMResponse:
        ...
```

- [x] **Step 2: Create initial exports**

Create `apps/dialectical-engine/coordinator/app/providers/__init__.py`:

```python
from app.providers.base import LLMProvider, LLMResponse, ProviderError

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ProviderError",
]
```

---

### Task 4: Add Fake And Codex Providers

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/providers/fake.py`
- Create: `apps/dialectical-engine/coordinator/app/providers/codex_cli.py`
- Modify: `apps/dialectical-engine/coordinator/app/providers/__init__.py`

- [x] **Step 1: Create deterministic fake provider**

Create `apps/dialectical-engine/coordinator/app/providers/fake.py`:

```python
from __future__ import annotations

from app.providers.base import LLMResponse


class FakeProvider:
    name = "fake"

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}

    def generate(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str | None = None,
        role: str | None = None,
    ) -> LLMResponse:
        key = role or model
        text = self.responses.get(key, self.responses.get(model, "fake response"))
        return LLMResponse(
            text=text,
            raw={"provider": self.name, "model": model, "role": role},
            usage={"tokens_out": len(text.split())},
        )
```

- [x] **Step 2: Create Codex CLI provider**

Create `apps/dialectical-engine/coordinator/app/providers/codex_cli.py`:

```python
from __future__ import annotations

import shutil
import subprocess

from app.providers.base import LLMResponse, ProviderError


class CodexCliProvider:
    name = "codex"

    def __init__(self, executable: str = "codex", timeout_seconds: int = 120) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def command(
        self,
        messages: list[dict],
        *,
        model: str,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> list[str]:
        prompt = self.prompt_from_messages(messages)
        if response_format == "json":
            prompt = f"{prompt}\n\nReturn only valid JSON."
        if max_tokens is not None:
            prompt = f"{prompt}\n\nKeep the answer under {max_tokens} tokens."
        return [
            self.executable,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--model",
            model,
            prompt,
        ]

    def generate(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str | None = None,
        role: str | None = None,
    ) -> LLMResponse:
        if shutil.which(self.executable) is None:
            raise ProviderError(f"Codex executable not found: {self.executable}")
        command = self.command(
            messages,
            model=model,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip() or "Codex command failed"
            raise ProviderError(error[:2_000])
        return LLMResponse(
            text=completed.stdout.strip(),
            raw={"provider": self.name, "returncode": completed.returncode, "stderr": completed.stderr},
            usage=None,
        )

    @staticmethod
    def prompt_from_messages(messages: list[dict]) -> str:
        parts: list[str] = []
        for message in messages:
            role = str(message.get("role", "user")).strip() or "user"
            content = str(message.get("content", ""))
            parts.append(f"{role.upper()}:\n{content}")
        return "\n\n".join(parts)
```

- [x] **Step 3: Export providers**

Update `apps/dialectical-engine/coordinator/app/providers/__init__.py`:

```python
from app.providers.base import LLMProvider, LLMResponse, ProviderError
from app.providers.codex_cli import CodexCliProvider
from app.providers.fake import FakeProvider

__all__ = [
    "CodexCliProvider",
    "FakeProvider",
    "LLMProvider",
    "LLMResponse",
    "ProviderError",
]
```

---

### Task 5: Add Provider Registry

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/providers/registry.py`
- Modify: `apps/dialectical-engine/coordinator/app/providers/__init__.py`

- [x] **Step 1: Create registry and config loading**

Create `apps/dialectical-engine/coordinator/app/providers/registry.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.core.config import load_settings
from app.providers.base import LLMProvider, LLMResponse
from app.providers.codex_cli import CodexCliProvider


@dataclass(frozen=True)
class AgentConfig:
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int | None = None


def default_agents_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "agents.yaml"


def resolve_config_value(value: Any) -> Any:
    if value == "${OPENAI_MODEL}":
        settings = load_settings()
        return os.getenv("OPENAI_MODEL") or settings.openai_model or "codex-gpt-5.5"
    return value


def load_agent_configs(path: Path | None = None) -> dict[str, AgentConfig]:
    config_path = path or default_agents_path()
    raw = yaml.safe_load(config_path.read_text()) or {}
    defaults = raw.get("defaults") or {}
    agents = raw.get("agents") or {}
    configs: dict[str, AgentConfig] = {}
    for role, role_config in agents.items():
        merged = {**defaults, **(role_config or {})}
        configs[str(role)] = AgentConfig(
            provider=str(resolve_config_value(merged.get("provider", "codex"))),
            model=str(resolve_config_value(merged.get("model", "codex-gpt-5.5"))),
            temperature=float(resolve_config_value(merged.get("temperature", 0.0))),
            max_tokens=(
                int(resolve_config_value(merged["max_tokens"]))
                if merged.get("max_tokens") is not None
                else None
            ),
        )
    return configs


class ProviderRegistry:
    def __init__(
        self,
        *,
        agents: dict[str, AgentConfig] | None = None,
        providers: dict[str, LLMProvider] | None = None,
    ) -> None:
        self.agents = agents if agents is not None else load_agent_configs()
        self.providers = providers if providers is not None else {"codex": CodexCliProvider()}

    def generate_for_role(
        self,
        role: str,
        messages: list[dict],
        *,
        response_format: str | None = None,
    ) -> LLMResponse:
        if role not in self.agents:
            raise KeyError(f"No agent configured for role {role}")
        agent = self.agents[role]
        provider = self.providers[agent.provider]
        return provider.generate(
            messages,
            model=agent.model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            response_format=response_format,
            role=role,
        )
```

- [x] **Step 2: Export registry**

Update `apps/dialectical-engine/coordinator/app/providers/__init__.py`:

```python
from app.providers.base import LLMProvider, LLMResponse, ProviderError
from app.providers.codex_cli import CodexCliProvider
from app.providers.fake import FakeProvider
from app.providers.registry import AgentConfig, ProviderRegistry, load_agent_configs

__all__ = [
    "AgentConfig",
    "CodexCliProvider",
    "FakeProvider",
    "LLMProvider",
    "LLMResponse",
    "ProviderError",
    "ProviderRegistry",
    "load_agent_configs",
]
```

---

### Task 6: Run Step 2 Verification And Commit

**Files:**
- Verify all Step 2 files.

- [x] **Step 1: Run focused provider tests**

Run:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin tests/test_providers.py -q
```

Expected: all tests PASS.

- [x] **Step 2: Run full app tests**

Run:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

Expected: full tests PASS.

- [x] **Step 3: Review git diff**

Run:

```bash
git diff -- apps/dialectical-engine/config/agents.yaml apps/dialectical-engine/coordinator/app/providers apps/dialectical-engine/coordinator/tests/test_providers.py docs/superpowers/plans/2026-06-14-qbaf-step-2-provider-layer.md
```

Expected: only Step 2 provider-layer changes appear.

- [x] **Step 4: Commit Step 2**

Run:

```bash
git add apps/dialectical-engine/config/agents.yaml apps/dialectical-engine/coordinator/app/providers apps/dialectical-engine/coordinator/tests/test_providers.py docs/superpowers/plans/2026-06-14-qbaf-step-2-provider-layer.md
git commit -m "feat(step-2): add qbaf provider abstraction"
```

Expected: commit succeeds.
