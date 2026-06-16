from __future__ import annotations

import json

import pytest

from app.qbaf import ClaimNode, Edge, QBAFGraph


def test_qbaf_graph_round_trips_json() -> None:
    graph = QBAFGraph(
        root_id="root",
        nodes={
            "root": ClaimNode(
                id="root",
                text="Remote work improves productivity",
                type="root",
                base_score=0.55,
                final_strength=0.55,
                uncertainty=0.20,
                status="open",
                caveats=["evidence quality still pending"],
                transcript=[{"role": "judge", "content": "initial estimate"}],
            ),
            "sub-1": ClaimNode(
                id="sub-1",
                text="Workers report fewer interruptions",
                type="sub_claim",
                base_score=0.70,
                final_strength=0.70,
                uncertainty=0.10,
                status="scored",
            ),
            "evidence-1": ClaimNode(
                id="evidence-1",
                text="Survey result supports fewer interruptions",
                type="evidence_leaf",
                base_score=0.80,
                final_strength=0.80,
                uncertainty=0.05,
                status="grounded",
            ),
        },
        edges=[
            Edge(source_id="sub-1", target_id="root", polarity="support", weight=0.60),
            Edge(source_id="evidence-1", target_id="sub-1", polarity="support", weight=0.75),
        ],
    )

    reloaded = QBAFGraph.from_json(graph.to_json())

    assert reloaded == graph
    assert json.loads(reloaded.to_json())["root_id"] == "root"
    assert reloaded.nodes["root"].caveats == ["evidence quality still pending"]
    assert reloaded.nodes["root"].transcript == [{"role": "judge", "content": "initial estimate"}]


def test_claim_node_rejects_invalid_score_ranges() -> None:
    with pytest.raises(ValueError, match="base_score must be between 0 and 1"):
        ClaimNode(id="bad", text="bad", type="root", base_score=1.1)

    with pytest.raises(ValueError, match="uncertainty must be between 0 and 1"):
        ClaimNode(id="bad", text="bad", type="root", uncertainty=-0.1)


def test_graph_rejects_invalid_edges() -> None:
    node = ClaimNode(id="root", text="Root", type="root")

    with pytest.raises(ValueError, match="unknown edge source"):
        QBAFGraph(
            root_id="root",
            nodes={"root": node},
            edges=[Edge(source_id="missing", target_id="root", polarity="support", weight=0.5)],
        )

    with pytest.raises(ValueError, match="weight must be between 0 and 1"):
        Edge(source_id="root", target_id="root", polarity="support", weight=2.0)
