from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from app.debate import TwoDebaterJudgeLoop
from app.evidence import EvidenceValidationPipeline, SourceRecord
from app.metareasoning import (
    AntiObfuscationChecker,
    NodeSelector,
    StoppingCriterion,
    StoppingDecision,
)
from app.providers import ProviderRegistry
from app.qbaf import ClaimNode, DFQuADSemantics, Edge, QBAFGraph, Semantics
from app.qbaf.model import require_non_empty


@dataclass(frozen=True)
class OrchestratorRun:
    graph: QBAFGraph
    root_confidence: float
    iterations: int
    root_history: tuple[float, ...]
    decisions: tuple[StoppingDecision, ...]


class RecursiveQBAFOrchestrator:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        max_iterations: int = 8,
        debate_loop: TwoDebaterJudgeLoop | None = None,
        evidence_pipeline: EvidenceValidationPipeline | None = None,
        anti_obfuscation: AntiObfuscationChecker | None = None,
        semantics: Semantics | None = None,
        selector: NodeSelector | None = None,
        stopping: StoppingCriterion | None = None,
        disagreement_threshold: float = 0.25,
        materiality_threshold: float = 0.02,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        self.registry = registry
        self.max_iterations = max_iterations
        self.semantics = semantics or DFQuADSemantics()
        self.selector = selector or NodeSelector(semantics=self.semantics)
        self.stopping = stopping or StoppingCriterion(selector=self.selector)
        self.debate_loop = debate_loop or TwoDebaterJudgeLoop(registry=registry)
        self.evidence_pipeline = evidence_pipeline or EvidenceValidationPipeline()
        self.anti_obfuscation = anti_obfuscation or AntiObfuscationChecker(registry=registry)
        self.disagreement_threshold = disagreement_threshold
        self.materiality_threshold = materiality_threshold

    def run(
        self,
        root_question: str,
        *,
        evidence_sources: dict[str, SourceRecord] | None = None,
        seed_evidence: bool = False,
    ) -> OrchestratorRun:
        root = ClaimNode(
            id="root",
            text=require_non_empty(root_question, "root_question"),
            type="root",
            status="open",
        )
        graph = QBAFGraph(root_id="root", nodes={"root": root}, edges=[])
        return self.run_graph(graph, evidence_sources=evidence_sources, seed_evidence=seed_evidence)

    def run_graph(
        self,
        graph: QBAFGraph,
        *,
        evidence_sources: dict[str, SourceRecord] | None = None,
        seed_evidence: bool = False,
    ) -> OrchestratorRun:
        sources = evidence_sources or {}
        current_graph = self._seed_evidence_sources(graph, sources) if seed_evidence else graph
        current_graph = self.semantics.propagate(current_graph)
        root_history = [current_graph.nodes[current_graph.root_id].final_strength]
        decisions: list[StoppingDecision] = []
        iterations = 0

        for iteration in range(self.max_iterations):
            iterations = iteration + 1
            node_id = self._next_node_id(current_graph)
            if node_id is not None:
                before_root = current_graph.nodes[current_graph.root_id].final_strength
                current_graph = self._process_node(
                    current_graph,
                    node_id,
                    sources,
                    before_root=before_root,
                )

            current_graph = self.semantics.propagate(current_graph)
            root_history.append(current_graph.nodes[current_graph.root_id].final_strength)
            decision = self.stopping.evaluate(current_graph, root_history=root_history)
            decisions.append(decision)
            if decision.should_stop:
                break

        return OrchestratorRun(
            graph=current_graph,
            root_confidence=current_graph.nodes[current_graph.root_id].final_strength,
            iterations=iterations,
            root_history=tuple(root_history),
            decisions=tuple(decisions),
        )

    def _seed_evidence_sources(
        self,
        graph: QBAFGraph,
        sources: dict[str, SourceRecord],
    ) -> QBAFGraph:
        if not sources:
            return graph
        nodes = dict(graph.nodes)
        edges = list(graph.edges)
        for reference, source in sources.items():
            node_id = _evidence_node_id(reference)
            if node_id in nodes:
                continue
            nodes[node_id] = ClaimNode(
                id=node_id,
                text=graph.nodes[graph.root_id].text,
                type="evidence_leaf",
                status="open",
                transcript=[{"reference": reference}],
            )
            edges.append(Edge(source_id=node_id, target_id=graph.root_id, polarity="support", weight=1.0))
        return QBAFGraph(root_id=graph.root_id, nodes=nodes, edges=edges)

    def _next_node_id(self, graph: QBAFGraph) -> str | None:
        if graph.nodes[graph.root_id].status == "open":
            return graph.root_id
        next_node = self.selector.select_next_node(graph)
        return next_node.node_id if next_node else None

    def _process_node(
        self,
        graph: QBAFGraph,
        node_id: str,
        sources: dict[str, SourceRecord],
        *,
        before_root: float,
    ) -> QBAFGraph:
        node = graph.nodes[node_id]
        if node.type == "evidence_leaf":
            return self._ground_evidence_node(graph, node_id, sources)

        debate_result = self.debate_loop.score_node(node)
        updated_node = self.anti_obfuscation.check_node(debate_result.node).node
        graph = self._replace_node(graph, updated_node)
        graph = self._replace_outgoing_edge_weights(graph, node_id, debate_result.edge_weight)
        root_after_score = self.semantics.propagate(graph).nodes[graph.root_id].final_strength
        if self._should_spawn_evidence(updated_node, before_root, root_after_score):
            graph = self._spawn_cited_evidence(graph, updated_node, debate_result.edge_weight, sources)
        return graph

    def _ground_evidence_node(
        self,
        graph: QBAFGraph,
        node_id: str,
        sources: dict[str, SourceRecord],
    ) -> QBAFGraph:
        node = graph.nodes[node_id]
        reference = _reference_for_node(node)
        if reference not in sources:
            return self._replace_node(
                graph,
                replace(
                    node,
                    status="blocked",
                    caveats=[*node.caveats, f"Missing source record for {reference}"],
                ),
            )
        return self._replace_node(graph, self.evidence_pipeline.ground_leaf(node, sources[reference]))

    def _should_spawn_evidence(self, node: ClaimNode, before_root: float, after_root: float) -> bool:
        return (
            _debate_disagreement(node) >= self.disagreement_threshold
            and abs(after_root - before_root) >= self.materiality_threshold
        )

    def _spawn_cited_evidence(
        self,
        graph: QBAFGraph,
        node: ClaimNode,
        edge_weight: float,
        sources: dict[str, SourceRecord],
    ) -> QBAFGraph:
        nodes = dict(graph.nodes)
        edges = list(graph.edges)
        existing = {edge.source_id for edge in edges if edge.target_id == node.id}
        for turn in node.transcript:
            if turn.get("role") not in {"proponent", "opponent"}:
                continue
            polarity = "support" if turn["role"] == "proponent" else "attack"
            for reference in turn.get("evidence", []):
                if reference not in sources:
                    continue
                child_id = _evidence_node_id(str(reference))
                if child_id not in nodes:
                    nodes[child_id] = ClaimNode(
                        id=child_id,
                        text=node.text,
                        type="evidence_leaf",
                        status="open",
                        transcript=[{"reference": reference}],
                    )
                if child_id in existing:
                    continue
                edges.append(
                    Edge(
                        source_id=child_id,
                        target_id=node.id,
                        polarity=polarity,
                        weight=edge_weight,
                    )
                )
                existing.add(child_id)
        return QBAFGraph(root_id=graph.root_id, nodes=nodes, edges=edges)

    @staticmethod
    def _replace_node(graph: QBAFGraph, node: ClaimNode) -> QBAFGraph:
        nodes = dict(graph.nodes)
        nodes[node.id] = node
        return QBAFGraph(root_id=graph.root_id, nodes=nodes, edges=list(graph.edges))

    @staticmethod
    def _replace_outgoing_edge_weights(graph: QBAFGraph, node_id: str, edge_weight: float) -> QBAFGraph:
        edges = [
            replace(edge, weight=edge_weight) if edge.source_id == node_id else edge
            for edge in graph.edges
        ]
        return QBAFGraph(root_id=graph.root_id, nodes=dict(graph.nodes), edges=edges)


def _evidence_node_id(reference: str) -> str:
    digest = hashlib.sha1(reference.encode("utf-8")).hexdigest()[:10]
    return f"evidence-{digest}"


def _reference_for_node(node: ClaimNode) -> str:
    for turn in node.transcript:
        if "reference" in turn:
            return str(turn["reference"])
    return node.id


def _debate_disagreement(node: ClaimNode) -> float:
    scores = [
        float(turn["score"])
        for turn in node.transcript
        if turn.get("role") in {"proponent", "opponent"} and "score" in turn
    ]
    if len(scores) < 2:
        return 0.0
    return max(scores) - min(scores)
