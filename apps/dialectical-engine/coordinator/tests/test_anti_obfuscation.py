from __future__ import annotations

import pytest

from app.metareasoning import AntiObfuscationChecker, parse_subclaim_estimates
from app.providers import AgentConfig, FakeProvider, ProviderRegistry
from app.qbaf import ClaimNode


def estimator_registry(fake: FakeProvider) -> ProviderRegistry:
    return ProviderRegistry(
        agents={
            "estimator": AgentConfig(provider="fake", model="fake-estimator", temperature=0.0)
        },
        providers={"fake": fake},
    )


def test_anti_obfuscation_skips_unflagged_nodes_without_provider_call() -> None:
    fake = FakeProvider({"estimator": '{"subclaims": []}'})
    checker = AntiObfuscationChecker(registry=estimator_registry(fake))
    node = ClaimNode(id="n1", text="Short claim", type="sub_claim", base_score=0.8)

    result = checker.check_node(node)

    assert result.triggered is False
    assert result.node == node
    assert fake.calls == []


def test_anti_obfuscation_caps_parent_when_subclaim_is_undefendable() -> None:
    fake = FakeProvider(
        {
            "estimator": (
                '{"subclaims": ['
                '{"text": "The mechanism is established", "probability": 0.82},'
                '{"text": "The key bridge claim holds", "probability": 0.18}'
                "]}"
            )
        }
    )
    checker = AntiObfuscationChecker(registry=estimator_registry(fake), threshold=0.35)
    node = ClaimNode(
        id="n1",
        text="A large argument combines several premises into a strong conclusion.",
        type="sub_claim",
        base_score=0.9,
        final_strength=0.9,
        caveats=["big argument"],
    )

    result = checker.check_node(node)

    assert result.triggered is True
    assert result.support_cap == pytest.approx(0.18)
    assert result.node.base_score == pytest.approx(0.18)
    assert result.node.final_strength == pytest.approx(0.18)
    assert "Undefendable subclaim: The key bridge claim holds (p=0.18)" in result.node.caveats
    assert [call["role"] for call in fake.calls] == ["estimator"]
    assert result.subclaims[1].undefendable is True


def test_subclaim_estimate_parser_rejects_invalid_payloads() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        parse_subclaim_estimates("not json")

    with pytest.raises(ValueError, match="subclaims"):
        parse_subclaim_estimates('{"items": []}')

    with pytest.raises(ValueError, match="probability"):
        parse_subclaim_estimates('{"subclaims": [{"text": "A", "probability": 1.4}]}')
