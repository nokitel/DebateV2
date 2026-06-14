from __future__ import annotations

import pytest

from app.providers import AgentConfig, FakeProvider, ProviderRegistry
from app.scoring import SelfConsistencyScorer, parse_score_sample


def registry_with_fake(fake: FakeProvider) -> ProviderRegistry:
    return ProviderRegistry(
        agents={
            "estimator": AgentConfig(
                provider="fake",
                model="fake-model",
                temperature=0.0,
                max_tokens=256,
            )
        },
        providers={"fake": fake},
    )


def test_self_consistency_scoring_reduces_fake_provider_samples() -> None:
    fake = FakeProvider(
        {
            "estimator": [
                '{"base_score": 0.2, "edge_weight": 0.4, "rationale": "weak"}',
                '{"base_score": 0.6, "edge_weight": 0.5, "rationale": "mixed"}',
                '{"base_score": 0.8, "edge_weight": 0.9, "rationale": "strong"}',
            ]
        }
    )
    scorer = SelfConsistencyScorer(
        registry=registry_with_fake(fake),
        role="estimator",
        sample_count=3,
    )

    result = scorer.score_claim("Remote work improves productivity")

    assert result.claim == "Remote work improves productivity"
    assert result.role == "estimator"
    assert result.base_score == pytest.approx((0.2 + 0.6 + 0.8) / 3)
    assert result.edge_weight == pytest.approx((0.4 + 0.5 + 0.9) / 3)
    assert result.uncertainty == pytest.approx(0.6)
    assert [sample.rationale for sample in result.samples] == ["weak", "mixed", "strong"]
    assert len(fake.calls) == 3
    assert {call["role"] for call in fake.calls} == {"estimator"}
    assert {call["response_format"] for call in fake.calls} == {"json"}


def test_score_sample_parser_accepts_tau_and_weight_aliases() -> None:
    sample = parse_score_sample('{"tau": 0.75, "weight": 0.25, "rationale": "alias keys"}')

    assert sample.base_score == 0.75
    assert sample.edge_weight == 0.25
    assert sample.rationale == "alias keys"


def test_score_sample_parser_rejects_invalid_payloads() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        parse_score_sample("score=0.7")

    with pytest.raises(ValueError, match="base_score"):
        parse_score_sample('{"base_score": 1.2, "edge_weight": 0.3}')

    with pytest.raises(ValueError, match="edge_weight"):
        parse_score_sample('{"base_score": 0.7}')


def test_self_consistency_scorer_requires_three_to_five_samples() -> None:
    registry = registry_with_fake(FakeProvider({"estimator": "{}"}))

    with pytest.raises(ValueError, match="between 3 and 5"):
        SelfConsistencyScorer(registry=registry, role="estimator", sample_count=2)

    with pytest.raises(ValueError, match="between 3 and 5"):
        SelfConsistencyScorer(registry=registry, role="estimator", sample_count=6)
