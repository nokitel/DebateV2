from __future__ import annotations

import json
from dataclasses import dataclass, replace
from json import JSONDecodeError
from typing import Any

from app.providers import ProviderRegistry
from app.qbaf import ClaimNode
from app.qbaf.model import require_non_empty, require_unit_interval


BIG_ARGUMENT_MARKERS = (
    "big argument",
    "cannot fully rebut",
    "decompose",
    "obfuscation",
)


@dataclass(frozen=True)
class SubclaimEstimate:
    text: str
    probability: float
    undefendable: bool


@dataclass(frozen=True)
class AntiObfuscationResult:
    node: ClaimNode
    triggered: bool
    subclaims: tuple[SubclaimEstimate, ...] = ()
    support_cap: float | None = None


class AntiObfuscationChecker:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        threshold: float = 0.35,
        long_text_words: int = 60,
    ) -> None:
        self.registry = registry
        self.threshold = require_unit_interval(float(threshold), "threshold")
        if long_text_words < 1:
            raise ValueError("long_text_words must be positive")
        self.long_text_words = long_text_words

    def check_node(self, node: ClaimNode) -> AntiObfuscationResult:
        if not self.should_trigger(node):
            return AntiObfuscationResult(node=node, triggered=False)

        response = self.registry.generate_for_role(
            "estimator",
            self._messages(node),
            response_format="json",
        )
        subclaims = parse_subclaim_estimates(response.text, threshold=self.threshold)
        undefendable = [subclaim for subclaim in subclaims if subclaim.undefendable]
        if not undefendable:
            support_cap = min((subclaim.probability for subclaim in subclaims), default=None)
            return AntiObfuscationResult(
                node=node,
                triggered=True,
                subclaims=subclaims,
                support_cap=support_cap,
            )

        support_cap = min(subclaim.probability for subclaim in undefendable)
        capped_score = min(node.base_score, support_cap)
        capped_strength = min(node.final_strength, support_cap)
        caveats = list(node.caveats)
        caveats.extend(
            f"Undefendable subclaim: {subclaim.text} (p={subclaim.probability:.2f})"
            for subclaim in undefendable
        )
        return AntiObfuscationResult(
            node=replace(
                node,
                base_score=capped_score,
                final_strength=capped_strength,
                caveats=caveats,
                status="anti_obfuscation_checked",
            ),
            triggered=True,
            subclaims=subclaims,
            support_cap=support_cap,
        )

    def should_trigger(self, node: ClaimNode) -> bool:
        if _contains_marker(node.caveats):
            return True
        return len(node.text.split()) >= self.long_text_words

    def _messages(self, node: ClaimNode) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "Decompose the claim into necessary subclaims and estimate each "
                    "subclaim probability. Return only JSON with subclaims."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Claim:\n{node.text}\n"
                    f"Caveats:\n{'; '.join(node.caveats) if node.caveats else 'None'}"
                ),
            },
        ]


def parse_subclaim_estimates(payload: str, *, threshold: float = 0.35) -> tuple[SubclaimEstimate, ...]:
    try:
        raw = json.loads(payload)
    except JSONDecodeError as exc:
        raise ValueError("estimator response must be valid JSON") from exc

    if not isinstance(raw, dict):
        raise ValueError("estimator response JSON must be an object")
    subclaims = raw.get("subclaims")
    if not isinstance(subclaims, list):
        raise ValueError("subclaims must be a list")

    clean_threshold = require_unit_interval(float(threshold), "threshold")
    return tuple(_parse_subclaim(item, clean_threshold) for item in subclaims)


def _parse_subclaim(item: Any, threshold: float) -> SubclaimEstimate:
    if not isinstance(item, dict):
        raise ValueError("subclaim must be an object")
    text = require_non_empty(str(item.get("text", "")), "text")
    probability = require_unit_interval(_required_float(item, "probability"), "probability")
    return SubclaimEstimate(
        text=text,
        probability=probability,
        undefendable=probability < threshold,
    )


def _required_float(raw: dict[str, Any], key: str) -> float:
    value = raw.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric") from exc


def _contains_marker(caveats: list[str]) -> bool:
    return any(marker in caveat.lower() for marker in BIG_ARGUMENT_MARKERS for caveat in caveats)
