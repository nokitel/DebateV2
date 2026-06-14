from __future__ import annotations

from dataclasses import dataclass, replace

from app.qbaf import DFQuADSemantics, QBAFGraph, Semantics
from app.qbaf.model import require_unit_interval


@dataclass(frozen=True)
class NodeRanking:
    node_id: str
    sensitivity: float
    uncertainty: float
    disagreement: float
    cost: float
    priority: float


class NodeSelector:
    def __init__(
        self,
        *,
        semantics: Semantics | None = None,
        costs: dict[str, float] | None = None,
    ) -> None:
        self.semantics = semantics or DFQuADSemantics()
        self.costs = costs or {}

    def rank_open_nodes(self, graph: QBAFGraph) -> list[NodeRanking]:
        ranking = [
            self._rank_node(graph, node_id)
            for node_id, node in graph.nodes.items()
            if node_id != graph.root_id and node.status == "open"
        ]
        return sorted(ranking, key=lambda item: (-item.priority, -item.sensitivity, item.node_id))

    def select_next_node(self, graph: QBAFGraph) -> NodeRanking | None:
        ranking = self.rank_open_nodes(graph)
        return ranking[0] if ranking else None

    def _rank_node(self, graph: QBAFGraph, node_id: str) -> NodeRanking:
        node = graph.nodes[node_id]
        uncertainty = node.uncertainty
        lower = max(0.0, node.final_strength - uncertainty)
        upper = min(1.0, node.final_strength + uncertainty)
        sensitivity = abs(
            self._root_strength_with_node_score(graph, node_id, upper)
            - self._root_strength_with_node_score(graph, node_id, lower)
        )
        disagreement = _score_disagreement(node.transcript)
        cost = max(0.01, float(self.costs.get(node_id, 1.0)))
        priority = sensitivity * (uncertainty + disagreement) / cost
        return NodeRanking(
            node_id=node_id,
            sensitivity=require_unit_interval(sensitivity, "sensitivity"),
            uncertainty=require_unit_interval(uncertainty, "uncertainty"),
            disagreement=require_unit_interval(disagreement, "disagreement"),
            cost=cost,
            priority=priority,
        )

    def _root_strength_with_node_score(self, graph: QBAFGraph, node_id: str, score: float) -> float:
        node = graph.nodes[node_id]
        updated_graph = QBAFGraph(
            root_id=graph.root_id,
            nodes={
                current_id: (
                    replace(node, base_score=score, final_strength=score)
                    if current_id == node_id
                    else current_node
                )
                for current_id, current_node in graph.nodes.items()
            },
            edges=list(graph.edges),
        )
        return self.semantics.propagate(updated_graph).nodes[graph.root_id].final_strength


def _score_disagreement(transcript: list[dict]) -> float:
    scores = []
    for turn in transcript:
        if "score" not in turn:
            continue
        try:
            scores.append(require_unit_interval(float(turn["score"]), "score"))
        except (TypeError, ValueError):
            continue
    if len(scores) < 2:
        return 0.0
    return max(scores) - min(scores)
