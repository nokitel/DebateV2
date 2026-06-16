from __future__ import annotations

import pytest

from app.evaluation import EvaluationExample, EvaluationHarness


def test_evaluation_report_flags_debate_when_it_beats_self_consistency() -> None:
    examples = [
        EvaluationExample(id="qa-1", prompt="Claim A", label=True),
        EvaluationExample(id="qa-2", prompt="Claim B", label=False),
        EvaluationExample(id="kialo-1", prompt="Claim C", label=True, dataset="kialo", human_impact_vote=0.9),
    ]
    report = EvaluationHarness(num_bins=2).evaluate(
        examples,
        debate_scores={"qa-1": 0.9, "qa-2": 0.2, "kialo-1": 0.8},
        baseline_scores={"qa-1": 0.6, "qa-2": 0.7, "kialo-1": 0.4},
    )

    assert report.debate_accuracy == pytest.approx(1.0)
    assert report.baseline_accuracy == pytest.approx(1 / 3)
    assert report.baseline_delta == pytest.approx(2 / 3)
    assert report.debate_ece == pytest.approx(1 / 6)
    assert report.baseline_ece == pytest.approx(0.3)
    assert report.kialo_impact_alignment == pytest.approx(1.0)
    assert report.debate_beats_baseline is True
    assert "keep the debate layer" in report.recommendation


def test_evaluation_report_recommends_simplifying_when_debate_does_not_win() -> None:
    examples = [
        EvaluationExample(id="qa-1", prompt="Claim A", label=True),
        EvaluationExample(id="qa-2", prompt="Claim B", label=False),
    ]
    report = EvaluationHarness(num_bins=2).evaluate(
        examples,
        debate_scores={"qa-1": 0.4, "qa-2": 0.6},
        baseline_scores={"qa-1": 0.8, "qa-2": 0.2},
    )

    assert report.debate_accuracy == pytest.approx(0.0)
    assert report.baseline_accuracy == pytest.approx(1.0)
    assert report.baseline_delta == pytest.approx(-1.0)
    assert report.debate_beats_baseline is False
    assert "simplify toward the self-consistency baseline" in report.recommendation
    assert "evidence subsystem" in report.recommendation


def test_evaluation_rejects_missing_matched_scores() -> None:
    examples = [EvaluationExample(id="qa-1", prompt="Claim A", label=True)]

    with pytest.raises(ValueError, match="missing debate score"):
        EvaluationHarness().evaluate(examples, debate_scores={}, baseline_scores={"qa-1": 0.8})

    with pytest.raises(ValueError, match="missing baseline score"):
        EvaluationHarness().evaluate(examples, debate_scores={"qa-1": 0.8}, baseline_scores={})
