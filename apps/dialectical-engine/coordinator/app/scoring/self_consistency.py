from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from statistics import fmean
from typing import Any

from app.providers import ProviderRegistry
from app.qbaf.model import require_non_empty, require_unit_interval


@dataclass(frozen=True)
class ScoreSample:
    base_score: float
    edge_weight: float
    rationale: str = ""


@dataclass(frozen=True)
class SelfConsistencyResult:
    claim: str
    role: str
    base_score: float
    edge_weight: float
    uncertainty: float
    samples: tuple[ScoreSample, ...]


def parse_score_sample(payload: str) -> ScoreSample:
    try:
        raw = json.loads(payload)
    except JSONDecodeError as exc:
        raise ValueError("provider response must be valid JSON") from exc

    if not isinstance(raw, dict):
        raise ValueError("provider response JSON must be an object")

    base_score = _required_number(raw, "base_score", "tau")
    edge_weight = _required_number(raw, "edge_weight", "weight")
    return ScoreSample(
        base_score=require_unit_interval(base_score, "base_score"),
        edge_weight=require_unit_interval(edge_weight, "edge_weight"),
        rationale=str(raw.get("rationale", "")).strip(),
    )


class SelfConsistencyScorer:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        role: str = "estimator",
        sample_count: int = 5,
    ) -> None:
        if sample_count < 3 or sample_count > 5:
            raise ValueError("sample_count must be between 3 and 5")
        self.registry = registry
        self.role = require_non_empty(role, "role")
        self.sample_count = sample_count

    def score_claim(self, claim: str, *, context: str | None = None) -> SelfConsistencyResult:
        cleaned_claim = require_non_empty(claim, "claim")
        samples = tuple(
            parse_score_sample(
                self.registry.generate_for_role(
                    self.role,
                    self._messages(
                        claim=cleaned_claim,
                        context=context,
                        sample_index=sample_index,
                    ),
                    response_format="json",
                ).text
            )
            for sample_index in range(self.sample_count)
        )
        return _reduce_samples(cleaned_claim, self.role, samples)

    def _messages(
        self,
        *,
        claim: str,
        context: str | None,
        sample_index: int,
    ) -> list[dict[str, str]]:
        context_text = f"\nContext:\n{context.strip()}" if context and context.strip() else ""
        return [
            {
                "role": "system",
                "content": (
                    "Estimate claim trustworthiness for a QBAF scoring engine. "
                    "Return only JSON with base_score, edge_weight, and rationale."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Claim:\n{claim}{context_text}\n"
                    f"Independent sample {sample_index + 1} of {self.sample_count}.\n"
                    "Use numbers between 0 and 1."
                ),
            },
        ]


def _reduce_samples(
    claim: str,
    role: str,
    samples: tuple[ScoreSample, ...],
) -> SelfConsistencyResult:
    base_scores = [sample.base_score for sample in samples]
    edge_weights = [sample.edge_weight for sample in samples]
    uncertainty = max(_spread(base_scores), _spread(edge_weights))
    return SelfConsistencyResult(
        claim=claim,
        role=role,
        base_score=require_unit_interval(fmean(base_scores), "base_score"),
        edge_weight=require_unit_interval(fmean(edge_weights), "edge_weight"),
        uncertainty=require_unit_interval(uncertainty, "uncertainty"),
        samples=samples,
    )


def _required_number(raw: dict[str, Any], primary_key: str, alias_key: str) -> float:
    value = raw.get(primary_key, raw.get(alias_key))
    if value is None:
        raise ValueError(f"{primary_key} is required")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{primary_key} must be numeric") from exc


def _spread(values: list[float]) -> float:
    return max(values) - min(values)
