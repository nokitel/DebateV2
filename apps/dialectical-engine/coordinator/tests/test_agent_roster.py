from __future__ import annotations

from app.debate import AgentRoster, Skeptic, TopicClassifier
from app.providers import AgentConfig, FakeProvider, ProviderRegistry
from app.qbaf import ClaimNode


def roster_registry() -> ProviderRegistry:
    return ProviderRegistry(
        agents={
            "specialist": AgentConfig(provider="fake", model="domain-model", temperature=0.3),
            "methodologist": AgentConfig(provider="fake", model="stats-model", temperature=0.1),
            "skeptic": AgentConfig(provider="fake", model="red-team-model", temperature=0.0),
        },
        providers={"fake": FakeProvider()},
    )


def test_agent_roster_reads_role_metadata_from_registry() -> None:
    roster = AgentRoster.from_registry(roster_registry())

    specialist = roster.role("specialist")
    methodologist = roster.role("methodologist")
    skeptic = roster.role("skeptic")

    assert specialist.model == "domain-model"
    assert specialist.provider == "fake"
    assert specialist.temperature == 0.3
    assert methodologist.model == "stats-model"
    assert skeptic.model == "red-team-model"


def test_topic_classifier_routes_specialists_for_flagged_claims() -> None:
    roster = AgentRoster.from_registry(roster_registry())

    routed = roster.route_for_claim(
        "A clinical trial reports a p-value but has a small sample size."
    )

    assert routed == ("specialist", "methodologist", "skeptic")


def test_topic_classifier_routes_skeptic_for_plain_claims() -> None:
    roster = AgentRoster.from_registry(roster_registry())

    assert roster.route_for_claim("Remote work improves productivity.") == ("skeptic",)


def test_topic_classifier_reports_domain_and_methodology_flags() -> None:
    classifier = TopicClassifier()

    assert classifier.classify("Clinical patients improved after treatment.") == {"domain"}
    assert classifier.classify("The sample size and p-value are questionable.") == {"methodology"}
    assert classifier.classify("A randomized trial reports a confidence interval.") == {
        "domain",
        "methodology",
    }


def test_skeptic_certifies_only_when_no_attack_markers_remain() -> None:
    skeptic = Skeptic()

    assert skeptic.certify_no_unaddressed_attack(
        ClaimNode(id="ok", text="Claim", type="root", caveats=[])
    )
    assert not skeptic.certify_no_unaddressed_attack(
        ClaimNode(
            id="blocked",
            text="Claim",
            type="root",
            caveats=["Unaddressed attack: selection bias"],
        )
    )
    assert not skeptic.certify_no_unaddressed_attack(
        ClaimNode(
            id="blocked",
            text="Claim",
            type="root",
            transcript=[{"unaddressed_attack": "missing counterargument"}],
        )
    )
