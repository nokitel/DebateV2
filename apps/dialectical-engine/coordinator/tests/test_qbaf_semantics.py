from __future__ import annotations

import pytest

from app.qbaf import ClaimNode, DFQuADSemantics, Edge, QBAFGraph, probabilistic_sum


def claim(node_id: str, base_score: float, node_type: str = "sub_claim") -> ClaimNode:
    return ClaimNode(
        id=node_id,
        text=f"Claim {node_id}",
        type=node_type,
        base_score=base_score,
        final_strength=0.0,
    )


def root(base_score: float) -> ClaimNode:
    return claim("root", base_score, "root")


def propagated_root_strength(graph: QBAFGraph) -> float:
    return DFQuADSemantics().propagate(graph).nodes[graph.root_id].final_strength


def test_probabilistic_sum_matches_df_quad_aggregation_formula() -> None:
    assert probabilistic_sum([]) == 0.0
    assert probabilistic_sum([0.8]) == 0.8
    assert probabilistic_sum([0.8, 0.25]) == pytest.approx(0.85)
    assert probabilistic_sum([0.8, 0.25, 0.1]) == pytest.approx(0.865)


def test_df_quad_propagates_weighted_support_and_attack_formula() -> None:
    graph = QBAFGraph(
        root_id="root",
        nodes={
            "root": root(0.4),
            "support": claim("support", 0.7),
            "attack": claim("attack", 0.6),
        },
        edges=[
            Edge(source_id="support", target_id="root", polarity="support", weight=0.5),
            Edge(source_id="attack", target_id="root", polarity="attack", weight=0.25),
        ],
    )

    result = DFQuADSemantics().propagate(graph)

    assert graph.nodes["root"].final_strength == 0.0
    assert result is not graph
    assert result.nodes["support"].final_strength == pytest.approx(0.7)
    assert result.nodes["attack"].final_strength == pytest.approx(0.6)
    assert result.nodes["root"].final_strength == pytest.approx(0.52)


def test_df_quad_combines_multiple_weighted_supporters() -> None:
    graph = QBAFGraph(
        root_id="root",
        nodes={
            "root": root(0.5),
            "s1": claim("s1", 0.8),
            "s2": claim("s2", 0.5),
            "a1": claim("a1", 0.4),
        },
        edges=[
            Edge(source_id="s1", target_id="root", polarity="support", weight=1.0),
            Edge(source_id="s2", target_id="root", polarity="support", weight=0.5),
            Edge(source_id="a1", target_id="root", polarity="attack", weight=1.0),
        ],
    )

    result = DFQuADSemantics().propagate(graph)

    assert result.nodes["root"].final_strength == pytest.approx(0.725)


def test_df_quad_support_and_attack_are_monotonic() -> None:
    weak_support = QBAFGraph(
        root_id="root",
        nodes={"root": root(0.5), "support": claim("support", 0.6)},
        edges=[Edge(source_id="support", target_id="root", polarity="support", weight=0.25)],
    )
    strong_support = QBAFGraph(
        root_id="root",
        nodes={"root": root(0.5), "support": claim("support", 0.6)},
        edges=[Edge(source_id="support", target_id="root", polarity="support", weight=0.75)],
    )

    weak_attack = QBAFGraph(
        root_id="root",
        nodes={"root": root(0.5), "attack": claim("attack", 0.6)},
        edges=[Edge(source_id="attack", target_id="root", polarity="attack", weight=0.25)],
    )
    strong_attack = QBAFGraph(
        root_id="root",
        nodes={"root": root(0.5), "attack": claim("attack", 0.6)},
        edges=[Edge(source_id="attack", target_id="root", polarity="attack", weight=0.75)],
    )

    assert propagated_root_strength(strong_support) > propagated_root_strength(weak_support)
    assert propagated_root_strength(strong_attack) < propagated_root_strength(weak_attack)


def test_df_quad_rejects_cycles() -> None:
    graph = QBAFGraph(
        root_id="a",
        nodes={"a": claim("a", 0.5, "root"), "b": claim("b", 0.5)},
        edges=[
            Edge(source_id="a", target_id="b", polarity="support", weight=1.0),
            Edge(source_id="b", target_id="a", polarity="attack", weight=1.0),
        ],
    )

    with pytest.raises(ValueError, match="cycle"):
        DFQuADSemantics().propagate(graph)
