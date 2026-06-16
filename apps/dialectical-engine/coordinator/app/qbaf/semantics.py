from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Protocol

from app.qbaf.model import Edge, QBAFGraph, require_unit_interval


class Semantics(Protocol):
    name: str

    def propagate(self, graph: QBAFGraph) -> QBAFGraph:
        """Return a graph with propagated node strengths."""
        ...


def probabilistic_sum(values: Iterable[float]) -> float:
    aggregate = 0.0
    for value in values:
        strength = require_unit_interval(float(value), "strength")
        aggregate = aggregate + strength - aggregate * strength
    return aggregate


def combine_df_quad(base_score: float, attacker_strength: float, supporter_strength: float) -> float:
    base = require_unit_interval(float(base_score), "base_score")
    attackers = require_unit_interval(float(attacker_strength), "attacker_strength")
    supporters = require_unit_interval(float(supporter_strength), "supporter_strength")
    delta = abs(supporters - attackers)
    if attackers >= supporters:
        return base - base * delta
    return base + (1 - base) * delta


class DFQuADSemantics:
    name = "df-quad"

    def propagate(self, graph: QBAFGraph) -> QBAFGraph:
        incoming_edges = self._incoming_edges(graph)
        strengths: dict[str, float] = {}
        visiting: set[str] = set()

        def compute(node_id: str) -> float:
            if node_id in strengths:
                return strengths[node_id]
            if node_id in visiting:
                raise ValueError(f"cycle detected in QBAF graph at node {node_id}")

            visiting.add(node_id)
            try:
                supporting_strengths = []
                attacking_strengths = []
                for edge in incoming_edges[node_id]:
                    weighted_strength = edge.weight * compute(edge.source_id)
                    if edge.polarity == "support":
                        supporting_strengths.append(weighted_strength)
                    else:
                        attacking_strengths.append(weighted_strength)

                node = graph.nodes[node_id]
                strength = combine_df_quad(
                    node.base_score,
                    probabilistic_sum(attacking_strengths),
                    probabilistic_sum(supporting_strengths),
                )
                strengths[node_id] = strength
                return strength
            finally:
                visiting.discard(node_id)

        for node_id in graph.nodes:
            compute(node_id)

        return QBAFGraph(
            root_id=graph.root_id,
            nodes={
                node_id: replace(node, final_strength=strengths[node_id])
                for node_id, node in graph.nodes.items()
            },
            edges=list(graph.edges),
        )

    @staticmethod
    def _incoming_edges(graph: QBAFGraph) -> dict[str, list[Edge]]:
        incoming_edges: dict[str, list[Edge]] = {node_id: [] for node_id in graph.nodes}
        for edge in graph.edges:
            incoming_edges[edge.target_id].append(edge)
        return incoming_edges
