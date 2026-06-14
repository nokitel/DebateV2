from __future__ import annotations

from app.metareasoning import NodeSelector
from app.qbaf import ClaimNode, Edge, QBAFGraph


def node(
    node_id: str,
    *,
    base_score: float,
    uncertainty: float,
    status: str = "open",
    transcript: list[dict] | None = None,
) -> ClaimNode:
    return ClaimNode(
        id=node_id,
        text=f"Claim {node_id}",
        type="sub_claim",
        base_score=base_score,
        final_strength=base_score,
        uncertainty=uncertainty,
        status=status,
        transcript=transcript or [],
    )


def test_node_selector_ranks_open_nodes_by_root_sensitivity_and_uncertainty() -> None:
    graph = QBAFGraph(
        root_id="root",
        nodes={
            "root": ClaimNode(id="root", text="Root", type="root", base_score=0.5),
            "important": node("important", base_score=0.6, uncertainty=0.4),
            "minor": node("minor", base_score=0.6, uncertainty=0.1),
        },
        edges=[
            Edge(source_id="important", target_id="root", polarity="support", weight=1.0),
            Edge(source_id="minor", target_id="root", polarity="support", weight=0.2),
        ],
    )

    ranking = NodeSelector().rank_open_nodes(graph)

    assert [item.node_id for item in ranking] == ["important", "minor"]
    assert ranking[0].sensitivity > ranking[1].sensitivity
    assert ranking[0].priority > ranking[1].priority
    assert NodeSelector().select_next_node(graph).node_id == "important"


def test_node_selector_sharpens_priority_with_debater_disagreement() -> None:
    graph = QBAFGraph(
        root_id="root",
        nodes={
            "root": ClaimNode(id="root", text="Root", type="root", base_score=0.5),
            "calm": node("calm", base_score=0.5, uncertainty=0.2),
            "contested": node(
                "contested",
                base_score=0.5,
                uncertainty=0.2,
                transcript=[{"score": 0.9}, {"score": 0.1}],
            ),
        },
        edges=[
            Edge(source_id="calm", target_id="root", polarity="support", weight=0.5),
            Edge(source_id="contested", target_id="root", polarity="support", weight=0.5),
        ],
    )

    ranking = NodeSelector().rank_open_nodes(graph)

    assert [item.node_id for item in ranking] == ["contested", "calm"]
    assert ranking[0].disagreement == 0.8


def test_node_selector_returns_none_when_no_open_nodes_exist() -> None:
    graph = QBAFGraph(
        root_id="root",
        nodes={
            "root": ClaimNode(id="root", text="Root", type="root", base_score=0.5),
            "done": node("done", base_score=0.6, uncertainty=0.4, status="grounded"),
        },
        edges=[Edge(source_id="done", target_id="root", polarity="support", weight=1.0)],
    )

    selector = NodeSelector()

    assert selector.rank_open_nodes(graph) == []
    assert selector.select_next_node(graph) is None
