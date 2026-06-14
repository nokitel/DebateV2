from __future__ import annotations

import pytest

from app.debate import TwoDebaterJudgeLoop, anonymize_transcript
from app.providers import AgentConfig, FakeProvider, ProviderRegistry
from app.qbaf import ClaimNode


def debate_registry(fake: FakeProvider) -> ProviderRegistry:
    agents = {
        role: AgentConfig(provider="fake", model=f"fake-{role}", temperature=0.0, max_tokens=256)
        for role in ("proponent", "opponent", "judge")
    }
    return ProviderRegistry(agents=agents, providers={"fake": fake})


def test_two_debater_judge_loop_scores_node_and_records_transcript() -> None:
    fake = FakeProvider(
        {
            "proponent": (
                '{"argument": "Clinical trial supports the claim.", '
                '"score": 0.85, "evidence": ["doi:10/example"]}'
            ),
            "opponent": (
                '{"argument": "The trial has a small sample.", '
                '"score": 0.25, "evidence": ["pmid:123"]}'
            ),
            "judge": '{"base_score": 0.62, "edge_weight": 0.7, "rationale": "balanced"}',
        }
    )
    loop = TwoDebaterJudgeLoop(registry=debate_registry(fake), rounds=1)
    node = ClaimNode(id="root", text="Remote work improves productivity", type="root")

    result = loop.score_node(node)

    assert result.node.base_score == pytest.approx(0.62)
    assert result.node.uncertainty == pytest.approx(0.60)
    assert result.node.status == "debated"
    assert result.edge_weight == pytest.approx(0.7)
    assert [call["role"] for call in fake.calls] == ["proponent", "opponent", "judge"]
    assert [turn["role"] for turn in result.node.transcript] == ["proponent", "opponent", "judge"]
    assert result.node.transcript[0]["evidence_checks"] == [
        {
            "reference": "doi:10/example",
            "status": "pending_step_8",
            "caveats": ["Evidence validation is pending Step 8."],
        }
    ]
    assert result.node.transcript[2]["base_score"] == pytest.approx(0.62)


def test_debate_context_anonymizes_prior_turn_roles() -> None:
    fake = FakeProvider(
        {
            "proponent": (
                '{"argument": "Clinical trial supports the claim.", '
                '"score": 0.85, "evidence": ["doi:10/example"]}'
            ),
            "opponent": (
                '{"argument": "The trial has a small sample.", '
                '"score": 0.25, "evidence": ["pmid:123"]}'
            ),
            "judge": '{"base_score": 0.62, "edge_weight": 0.7, "rationale": "balanced"}',
        }
    )
    loop = TwoDebaterJudgeLoop(registry=debate_registry(fake), rounds=1)

    loop.score_node(ClaimNode(id="root", text="Remote work improves productivity", type="root"))

    opponent_messages = "\n".join(message["content"] for message in fake.calls[1]["messages"])
    assert "Clinical trial supports the claim." in opponent_messages
    assert "proponent" not in opponent_messages.lower()
    assert "opponent" not in opponent_messages.lower()


def test_anonymize_transcript_strips_agent_identity() -> None:
    anonymous = anonymize_transcript(
        [
            {"role": "proponent", "argument": "A", "score": 0.8},
            {"role": "opponent", "argument": "B", "score": 0.2},
        ]
    )

    assert anonymous == [
        {"argument": "A", "score": 0.8},
        {"argument": "B", "score": 0.2},
    ]


def test_debater_turns_must_cite_evidence() -> None:
    fake = FakeProvider(
        {
            "proponent": '{"argument": "No citation.", "score": 0.7, "evidence": []}',
            "opponent": '{"argument": "Counter.", "score": 0.3, "evidence": ["pmid:123"]}',
            "judge": '{"base_score": 0.5, "edge_weight": 0.5}',
        }
    )
    loop = TwoDebaterJudgeLoop(registry=debate_registry(fake), rounds=1)

    with pytest.raises(ValueError, match="evidence"):
        loop.score_node(ClaimNode(id="root", text="Remote work improves productivity", type="root"))
