from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.providers import AgentConfig, ProviderRegistry
from app.qbaf import ClaimNode
from app.qbaf.model import require_non_empty


PERSONAS = {
    "specialist": "Domain specialist",
    "methodologist": "Methodologist/statistician",
    "skeptic": "Skeptic/red team",
}

DOMAIN_KEYWORDS = {
    "clinical",
    "disease",
    "health",
    "medical",
    "patient",
    "patients",
    "therapy",
    "treatment",
    "trial",
}

METHODOLOGY_KEYWORDS = {
    "bias",
    "confidence interval",
    "correlation",
    "effect size",
    "p-value",
    "randomized",
    "sample",
    "sample size",
    "statistical",
}

ATTACK_MARKERS = (
    "unaddressed attack",
    "unresolved attack",
    "missing counterargument",
    "needs rebuttal",
)


@dataclass(frozen=True)
class AgentRole:
    name: str
    persona: str
    provider: str
    model: str
    temperature: float
    max_tokens: int | None

    @classmethod
    def from_config(cls, name: str, config: AgentConfig) -> "AgentRole":
        clean_name = require_non_empty(name, "name")
        return cls(
            name=clean_name,
            persona=PERSONAS.get(clean_name, clean_name.replace("_", " ")),
            provider=config.provider,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )


class TopicClassifier:
    def classify(self, claim: str) -> set[str]:
        text = require_non_empty(claim, "claim").lower()
        flags: set[str] = set()
        if _contains_any(text, DOMAIN_KEYWORDS):
            flags.add("domain")
        if _contains_any(text, METHODOLOGY_KEYWORDS):
            flags.add("methodology")
        return flags


class AgentRoster:
    def __init__(
        self,
        roles: dict[str, AgentRole],
        *,
        classifier: TopicClassifier | None = None,
    ) -> None:
        self.roles = dict(roles)
        self.classifier = classifier or TopicClassifier()

    @classmethod
    def from_registry(
        cls,
        registry: ProviderRegistry,
        *,
        classifier: TopicClassifier | None = None,
    ) -> "AgentRoster":
        return cls(
            {
                role_name: AgentRole.from_config(role_name, config)
                for role_name, config in registry.agents.items()
            },
            classifier=classifier,
        )

    def role(self, name: str) -> AgentRole:
        clean_name = require_non_empty(name, "name")
        if clean_name not in self.roles:
            raise KeyError(f"No agent role configured for {clean_name}")
        return self.roles[clean_name]

    def route_for_claim(self, claim: str) -> tuple[str, ...]:
        flags = self.classifier.classify(claim)
        routed: list[str] = []
        if "domain" in flags and "specialist" in self.roles:
            routed.append("specialist")
        if "methodology" in flags and "methodologist" in self.roles:
            routed.append("methodologist")
        if "skeptic" in self.roles:
            routed.append("skeptic")
        return tuple(routed)


class Skeptic:
    def certify_no_unaddressed_attack(self, node: ClaimNode) -> bool:
        if _contains_attack_marker(node.caveats):
            return False
        for turn in node.transcript:
            if turn.get("unaddressed_attack"):
                return False
            if _contains_attack_marker(str(value) for value in turn.values()):
                return False
        return True


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _contains_attack_marker(values: Iterable[str]) -> bool:
    return any(_contains_any(value.lower(), ATTACK_MARKERS) for value in values)
