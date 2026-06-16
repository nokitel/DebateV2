from __future__ import annotations

import inspect


def test_v2_completion_has_one_synthesis_handler() -> None:
    from app.services import dialectical_v2

    source = inspect.getsource(dialectical_v2.complete_v2_worker_job)

    assert source.count('if job.job_type == "v2_synthesize":') == 1


def test_v2_product_flow_does_not_export_legacy_capability_router() -> None:
    from app.services import dialectical_v2

    assert not hasattr(dialectical_v2, "select_reusable_skill")
    assert not hasattr(dialectical_v2, "select_reusable_agent")
    assert not hasattr(dialectical_v2, "queue_next_capability_job")


def test_v2_product_flow_does_not_export_deterministic_analyzer_scaffold() -> None:
    from app.services import dialectical_v2

    assert not hasattr(dialectical_v2, "DEFAULT_ANALYZERS")
    assert not hasattr(dialectical_v2, "analyzer_output")
    assert not hasattr(dialectical_v2, "run_analyzers")


def test_spend_service_does_not_export_grok_specific_cap_alias() -> None:
    from app.services import spend

    assert not hasattr(spend, "grok_cap_reached")
