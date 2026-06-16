from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.core.config import DEFAULT_ROUTING, load_settings


@dataclass
class RoutingEngine:
    roles: dict[str, dict[str, Any]] = field(default_factory=lambda: load_settings().routing)
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def choose(
        self,
        role: str,
        online_capabilities: set[str] | None = None,
        exclude_models: set[str] | None = None,
        allowed_models: set[str] | None = None,
        roles: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        online_capabilities = online_capabilities or set()
        exclude_models = exclude_models or set()
        configured_roles = roles or self.roles
        config = configured_roles.get(role, DEFAULT_ROUTING.get(role, {}))

        if "pool" in config:
            pool = [model for model in config["pool"] if model not in exclude_models]
            if allowed_models is not None:
                pool = [model for model in pool if model in allowed_models]
            if online_capabilities:
                available = [model for model in pool if model in online_capabilities]
                if available:
                    pool = available
            if not pool:
                raise ValueError(f"No models available for role {role}")
            if config.get("strategy") == "round_robin":
                index = self.counters[role] % len(pool)
                self.counters[role] += 1
                return pool[index]
            return pool[0]

        ordered = [config.get("primary"), *config.get("fallback", [])]
        ordered = [model for model in ordered if model and model not in exclude_models]
        if allowed_models is not None:
            ordered = [model for model in ordered if model in allowed_models]
        if online_capabilities:
            for model in ordered:
                if model in online_capabilities:
                    return model
        if ordered:
            return ordered[0]
        raise ValueError(f"No models configured for role {role}")

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return self.roles


routing_engine = RoutingEngine()
