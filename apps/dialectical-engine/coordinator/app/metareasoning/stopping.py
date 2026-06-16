from __future__ import annotations

from dataclasses import dataclass

from app.debate import Skeptic
from app.metareasoning.node_selection import NodeSelector
from app.qbaf import QBAFGraph


@dataclass(frozen=True)
class StoppingDecision:
    should_stop: bool
    reasons: tuple[str, ...] = ()


class StoppingCriterion:
    def __init__(
        self,
        *,
        root_epsilon: float = 0.02,
        debate_epsilon: float = 0.02,
        open_node_priority_threshold: float = 0.02,
        selector: NodeSelector | None = None,
        skeptic: Skeptic | None = None,
    ) -> None:
        self.root_epsilon = root_epsilon
        self.debate_epsilon = debate_epsilon
        self.open_node_priority_threshold = open_node_priority_threshold
        self.selector = selector or NodeSelector()
        self.skeptic = skeptic or Skeptic()

    def evaluate(self, graph: QBAFGraph, *, root_history: list[float]) -> StoppingDecision:
        reasons: list[str] = []
        if not self._root_is_stable(root_history):
            reasons.append("root score still moving")
        if self._has_high_priority_open_nodes(graph):
            reasons.append("high-priority open nodes remain")
        if self._has_unresolved_caveats(graph):
            reasons.append("unresolved caveats remain")
        if self._has_debate_movement(graph):
            reasons.append("debate scores still shifting")
        if not self._skeptic_certifies(graph):
            reasons.append("skeptic did not certify all nodes")
        return StoppingDecision(should_stop=not reasons, reasons=tuple(reasons))

    def _root_is_stable(self, root_history: list[float]) -> bool:
        if len(root_history) < 3:
            return False
        recent = root_history[-3:]
        deltas = [abs(recent[index + 1] - recent[index]) for index in range(2)]
        return all(delta < self.root_epsilon for delta in deltas)

    def _has_high_priority_open_nodes(self, graph: QBAFGraph) -> bool:
        return any(
            item.priority >= self.open_node_priority_threshold
            for item in self.selector.rank_open_nodes(graph)
        )

    @staticmethod
    def _has_unresolved_caveats(graph: QBAFGraph) -> bool:
        return any(node.caveats for node in graph.nodes.values())

    def _has_debate_movement(self, graph: QBAFGraph) -> bool:
        for node in graph.nodes.values():
            scores = [
                float(turn["score"])
                for turn in node.transcript
                if isinstance(turn, dict) and "score" in turn
            ]
            if len(scores) >= 2 and abs(scores[-1] - scores[-2]) >= self.debate_epsilon:
                return True
        return False

    def _skeptic_certifies(self, graph: QBAFGraph) -> bool:
        return all(
            self.skeptic.certify_no_unaddressed_attack(node)
            for node in graph.nodes.values()
        )
