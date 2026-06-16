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
