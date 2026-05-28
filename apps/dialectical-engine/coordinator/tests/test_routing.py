from __future__ import annotations

from app.services.routing import RoutingEngine


def test_round_robin_prefers_online_capabilities() -> None:
    engine = RoutingEngine(
        roles={
            "proposer": {
                "pool": ["a", "b", "c"],
                "strategy": "round_robin",
            }
        }
    )

    assert engine.choose("proposer", {"b", "c"}) == "b"
    assert engine.choose("proposer", {"b", "c"}) == "c"


def test_primary_fallback_exclusions() -> None:
    engine = RoutingEngine(
        roles={
            "synthesizer": {
                "primary": "a",
                "fallback": ["b"],
            }
        }
    )

    assert engine.choose("synthesizer", {"a", "b"}, exclude_models={"a"}) == "b"

