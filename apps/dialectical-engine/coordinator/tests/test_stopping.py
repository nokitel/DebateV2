from __future__ import annotations

from app.metareasoning import StoppingCriterion
from app.qbaf import ClaimNode, Edge, QBAFGraph


def graph_with_nodes(*nodes: ClaimNode, edges: list[Edge] | None = None) -> QBAFGraph:
    root = ClaimNode(
        id="root",
        text="Root",
        type="root",
        base_score=0.7,
        final_strength=0.7,
        status="grounded",
    )
    all_nodes = {"root": root}
    all_nodes.update({node.id: node for node in nodes})
    return QBAFGraph(root_id="root", nodes=all_nodes, edges=edges or [])


def test_stopping_halts_on_converged_graph() -> None:
    graph = graph_with_nodes(
        ClaimNode(
            id="e1",
            text="Evidence",
            type="evidence_leaf",
            base_score=0.8,
            final_strength=0.8,
            status="grounded",
        ),
        edges=[Edge(source_id="e1", target_id="root", polarity="support", weight=0.5)],
    )

    decision = StoppingCriterion().evaluate(graph, root_history=[0.70, 0.71, 0.715])

    assert decision.should_stop is True
    assert decision.reasons == ()


def test_stopping_rejects_false_consensus_with_unaddressed_attack() -> None:
    graph = graph_with_nodes(
        ClaimNode(
            id="n1",
            text="Node",
            type="sub_claim",
            base_score=0.8,
            final_strength=0.8,
            status="grounded",
            caveats=["Unaddressed attack: selection bias"],
            transcript=[{"score": 0.8}, {"score": 0.81}],
        )
    )

    decision = StoppingCriterion().evaluate(graph, root_history=[0.80, 0.805, 0.81])

    assert decision.should_stop is False
    assert "unresolved caveats remain" in decision.reasons
    assert "skeptic did not certify all nodes" in decision.reasons


def test_stopping_requires_stable_root_history() -> None:
    graph = graph_with_nodes()

    decision = StoppingCriterion(root_epsilon=0.02).evaluate(
        graph,
        root_history=[0.50, 0.60, 0.66],
    )

    assert decision.should_stop is False
    assert "root score still moving" in decision.reasons


def test_stopping_blocks_high_priority_open_nodes() -> None:
    open_node = ClaimNode(
        id="open",
        text="Open node",
        type="sub_claim",
        base_score=0.5,
        final_strength=0.5,
        uncertainty=0.5,
        status="open",
    )
    graph = graph_with_nodes(
        open_node,
        edges=[Edge(source_id="open", target_id="root", polarity="support", weight=1.0)],
    )

    decision = StoppingCriterion(open_node_priority_threshold=0.01).evaluate(
        graph,
        root_history=[0.70, 0.705, 0.71],
    )

    assert decision.should_stop is False
    assert "high-priority open nodes remain" in decision.reasons
