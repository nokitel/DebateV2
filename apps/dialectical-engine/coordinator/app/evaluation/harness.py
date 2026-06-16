from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.qbaf.model import require_non_empty, require_unit_interval


@dataclass(frozen=True)
class EvaluationExample:
    id: str
    prompt: str
    label: bool
    dataset: str = "qa"
    human_impact_vote: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_empty(self.id, "id"))
        object.__setattr__(self, "prompt", require_non_empty(self.prompt, "prompt"))
        object.__setattr__(self, "dataset", require_non_empty(self.dataset, "dataset"))
        if self.human_impact_vote is not None:
            object.__setattr__(
                self,
                "human_impact_vote",
                require_unit_interval(float(self.human_impact_vote), "human_impact_vote"),
            )


@dataclass(frozen=True)
class EvaluationReport:
    debate_accuracy: float
    baseline_accuracy: float
    baseline_delta: float
    debate_ece: float
    baseline_ece: float
    kialo_impact_alignment: float | None
    debate_beats_baseline: bool
    recommendation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "debate_accuracy": self.debate_accuracy,
            "baseline_accuracy": self.baseline_accuracy,
            "baseline_delta": self.baseline_delta,
            "debate_ece": self.debate_ece,
            "baseline_ece": self.baseline_ece,
            "kialo_impact_alignment": self.kialo_impact_alignment,
            "debate_beats_baseline": self.debate_beats_baseline,
            "recommendation": self.recommendation,
        }


class EvaluationHarness:
    def __init__(self, *, num_bins: int = 10) -> None:
        if num_bins < 1:
            raise ValueError("num_bins must be positive")
        self.num_bins = num_bins

    def evaluate(
        self,
        examples: list[EvaluationExample],
        *,
        debate_scores: Mapping[str, float],
        baseline_scores: Mapping[str, float],
    ) -> EvaluationReport:
        if not examples:
            raise ValueError("examples cannot be empty")
        debate = _matched_scores(examples, debate_scores, "debate")
        baseline = _matched_scores(examples, baseline_scores, "baseline")
        debate_accuracy = _accuracy(examples, debate)
        baseline_accuracy = _accuracy(examples, baseline)
        debate_ece = _expected_calibration_error(examples, debate, self.num_bins)
        baseline_ece = _expected_calibration_error(examples, baseline, self.num_bins)
        baseline_delta = debate_accuracy - baseline_accuracy
        debate_beats_baseline = baseline_delta > 0 and debate_ece <= baseline_ece
        return EvaluationReport(
            debate_accuracy=debate_accuracy,
            baseline_accuracy=baseline_accuracy,
            baseline_delta=baseline_delta,
            debate_ece=debate_ece,
            baseline_ece=baseline_ece,
            kialo_impact_alignment=_kialo_impact_alignment(examples, debate),
            debate_beats_baseline=debate_beats_baseline,
            recommendation=_recommendation(debate_beats_baseline),
        )


def _matched_scores(
    examples: list[EvaluationExample],
    scores: Mapping[str, float],
    label: str,
) -> dict[str, float]:
    matched = {}
    for example in examples:
        if example.id not in scores:
            raise ValueError(f"missing {label} score for {example.id}")
        matched[example.id] = require_unit_interval(float(scores[example.id]), f"{label} score")
    return matched


def _accuracy(examples: list[EvaluationExample], scores: dict[str, float]) -> float:
    correct = sum((scores[example.id] >= 0.5) == example.label for example in examples)
    return correct / len(examples)


def _expected_calibration_error(
    examples: list[EvaluationExample],
    scores: dict[str, float],
    num_bins: int,
) -> float:
    total = len(examples)
    ece = 0.0
    for bin_index in range(num_bins):
        lower = bin_index / num_bins
        upper = (bin_index + 1) / num_bins
        in_bin = [
            example
            for example in examples
            if lower <= _confidence(scores[example.id]) <= upper
            and (bin_index == num_bins - 1 or _confidence(scores[example.id]) < upper)
        ]
        if not in_bin:
            continue
        accuracy = _accuracy(in_bin, scores)
        confidence = sum(_confidence(scores[example.id]) for example in in_bin) / len(in_bin)
        ece += (len(in_bin) / total) * abs(accuracy - confidence)
    return ece


def _confidence(score: float) -> float:
    return score if score >= 0.5 else 1 - score


def _kialo_impact_alignment(
    examples: list[EvaluationExample],
    scores: dict[str, float],
) -> float | None:
    impact_examples = [
        example
        for example in examples
        if example.dataset == "kialo" and example.human_impact_vote is not None
    ]
    if not impact_examples:
        return None
    aligned = sum(
        (scores[example.id] >= 0.5) == (example.human_impact_vote >= 0.5)
        for example in impact_examples
    )
    return aligned / len(impact_examples)


def _recommendation(debate_beats_baseline: bool) -> str:
    if debate_beats_baseline:
        return "Decision gate passed: keep the debate layer and continue evaluation."
    return (
        "Decision gate failed: simplify toward the self-consistency baseline "
        "and invest in the evidence subsystem."
    )
