from __future__ import annotations

import pytest

from app.evidence import SourceRecord
from app.orchestration import RecursiveQBAFOrchestrator
from app.providers import AgentConfig, FakeProvider, ProviderRegistry
from app.qbaf import ClaimNode, Edge, QBAFGraph


def registry(fake: FakeProvider) -> ProviderRegistry:
    return ProviderRegistry(
        agents={
            role: AgentConfig(provider="fake", model=f"fake-{role}", temperature=0.0)
            for role in ("proponent", "opponent", "judge", "estimator")
        },
        providers={"fake": fake},
    )


def source(reference: str = "doi:10/support") -> SourceRecord:
    return SourceRecord(
        reference=reference,
        text="A randomized trial reports remote work improves productivity.",
        quality_grade="high",
    )


def test_recursive_orchestrator_scores_sample_question_with_evidence() -> None:
    fake = FakeProvider(
        {
            "proponent": (
                '{"argument": "The trial supports the claim.", '
                '"score": 0.71, "evidence": ["doi:10/support"]}'
            ),
            "opponent": (
                '{"argument": "The concern is minor.", '
                '"score": 0.70, "evidence": ["doi:10/support"]}'
            ),
            "judge": '{"base_score": 0.70, "edge_weight": 0.80, "rationale": "supported"}',
            "estimator": '{"subclaims": []}',
        }
    )
    orchestrator = RecursiveQBAFOrchestrator(
        registry=registry(fake),
        max_iterations=6,
        disagreement_threshold=0.25,
    )

    run = orchestrator.run(
        "Remote work improves productivity",
        evidence_sources={"doi:10/support": source()},
        seed_evidence=True,
    )

    assert run.root_confidence == pytest.approx(run.graph.nodes["root"].final_strength)
    assert run.root_confidence > run.graph.nodes["root"].base_score
    assert run.graph.nodes["root"].status == "debated"
    assert [turn["role"] for turn in run.graph.nodes["root"].transcript] == [
        "proponent",
        "opponent",
        "judge",
    ]
    evidence_nodes = [
        node for node in run.graph.nodes.values() if node.type == "evidence_leaf"
    ]
    assert len(evidence_nodes) == 1
    assert evidence_nodes[0].status == "grounded"
    assert evidence_nodes[0].base_score == pytest.approx(0.85)
    assert run.decisions[-1].should_stop is True
    assert {call["role"] for call in fake.calls} == {"proponent", "opponent", "judge"}


def test_recursive_orchestrator_continues_existing_graph_by_selected_open_node() -> None:
    fake = FakeProvider(
        {
            "proponent": (
                '{"argument": "Focused evidence supports this node.", '
                '"score": 0.82, "evidence": ["doi:10/support"]}'
            ),
            "opponent": (
                '{"argument": "Only weak objections remain.", '
                '"score": 0.80, "evidence": ["doi:10/support"]}'
            ),
            "judge": '{"base_score": 0.78, "edge_weight": 0.60, "rationale": "credible"}',
            "estimator": '{"subclaims": []}',
        }
    )
    graph = QBAFGraph(
        root_id="root",
        nodes={
            "root": ClaimNode(
                id="root",
                text="Root",
                type="root",
                base_score=0.50,
                final_strength=0.50,
                status="debated",
            ),
            "open": ClaimNode(
                id="open",
                text="Open supporting claim",
                type="sub_claim",
                base_score=0.50,
                final_strength=0.50,
                uncertainty=0.40,
                status="open",
            ),
        },
        edges=[Edge(source_id="open", target_id="root", polarity="support", weight=1.0)],
    )

    run = RecursiveQBAFOrchestrator(
        registry=registry(fake),
        max_iterations=4,
    ).run_graph(graph, evidence_sources={"doi:10/support": source()})

    assert run.graph.nodes["open"].status == "debated"
    assert run.graph.nodes["open"].base_score == pytest.approx(0.78)
    assert run.graph.edges[0].weight == pytest.approx(0.60)
    assert run.root_confidence > 0.50


def test_orchestrator_spawns_cited_evidence_only_when_disagreement_and_materiality_hold() -> None:
    fake = FakeProvider(
        {
            "proponent": (
                '{"argument": "Strong citation supports the claim.", '
                '"score": 0.95, "evidence": ["doi:10/support"]}'
            ),
            "opponent": (
                '{"argument": "A counter-source attacks the claim.", '
                '"score": 0.10, "evidence": ["doi:10/attack"]}'
            ),
            "judge": '{"base_score": 0.55, "edge_weight": 0.75, "rationale": "contested"}',
            "estimator": '{"subclaims": []}',
        }
    )
    orchestrator = RecursiveQBAFOrchestrator(
        registry=registry(fake),
        max_iterations=2,
        disagreement_threshold=0.50,
        materiality_threshold=0.01,
    )

    run = orchestrator.run(
        "Remote work improves productivity",
        evidence_sources={
            "doi:10/support": source("doi:10/support"),
            "doi:10/attack": SourceRecord(
                reference="doi:10/attack",
                text="The study refutes that remote work improves productivity.",
                quality_grade="high",
            ),
        },
    )

    spawned_edges = [
        edge for edge in run.graph.edges if edge.target_id == "root" and edge.source_id != "root"
    ]
    assert {edge.polarity for edge in spawned_edges} == {"support", "attack"}

    calm_fake = FakeProvider(
        {
            "proponent": (
                '{"argument": "Citation supports the claim.", '
                '"score": 0.62, "evidence": ["doi:10/support"]}'
            ),
            "opponent": (
                '{"argument": "Similar estimate.", '
                '"score": 0.61, "evidence": ["doi:10/attack"]}'
            ),
            "judge": '{"base_score": 0.55, "edge_weight": 0.75}',
            "estimator": '{"subclaims": []}',
        }
    )
    calm_run = RecursiveQBAFOrchestrator(
        registry=registry(calm_fake),
        max_iterations=1,
        disagreement_threshold=0.50,
        materiality_threshold=0.01,
    ).run(
        "Remote work improves productivity",
        evidence_sources={
            "doi:10/support": source("doi:10/support"),
            "doi:10/attack": source("doi:10/attack"),
        },
    )

    assert [
        node for node in calm_run.graph.nodes.values() if node.type == "evidence_leaf"
    ] == []
