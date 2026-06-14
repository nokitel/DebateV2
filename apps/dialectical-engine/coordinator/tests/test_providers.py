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
