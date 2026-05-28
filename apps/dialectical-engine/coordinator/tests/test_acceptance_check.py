from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
WORKER_A_ID = "11111111-1111-4111-8111-111111111111"
WORKER_B_ID = "22222222-2222-4222-8222-222222222222"
JOB_ID = "33333333-3333-4333-8333-333333333333"


def load_acceptance_module():
    spec = importlib.util.spec_from_file_location("dialectical_acceptance_check", ROOT / "scripts" / "acceptance_check.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_require_offline_worker_names_passes_for_registered_offline_worker() -> None:
    module = load_acceptance_module()
    workers = [
        {"name": "mac-mini", "status": "online"},
        {"name": "adesso-mbp", "status": "offline"},
    ]

    assert module.require_offline_worker_names(workers, {"adesso-mbp"}) == "adesso-mbp"


def test_require_offline_worker_names_rejects_missing_worker() -> None:
    module = load_acceptance_module()
    workers = [{"name": "mac-mini", "status": "online"}]

    with pytest.raises(module.AcceptanceError, match="missing"):
        module.require_offline_worker_names(workers, {"adesso-mbp"})


def test_require_offline_worker_names_rejects_online_worker() -> None:
    module = load_acceptance_module()
    workers = [
        {"name": "mac-mini", "status": "online"},
        {"name": "adesso-mbp", "status": "online"},
    ]

    with pytest.raises(module.AcceptanceError, match="adesso-mbp is 'online'"):
        module.require_offline_worker_names(workers, {"adesso-mbp"})


def test_public_list_evidence_records_archive_rows() -> None:
    module = load_acceptance_module()
    payload = {
        "limit": 50,
        "offset": 0,
        "items": [
            {
                "id": "debate-1",
                "topic": "Topic",
                "status": "complete",
                "created_at": "2026-05-24T00:00:00+00:00",
                "completed_at": "2026-05-24T00:01:00+00:00",
                "models": ["codex-gpt-5", "claude-sonnet-4.5", "codex-gpt-5"],
            }
        ],
    }

    evidence = module.public_list_evidence(payload)

    assert module.public_list_detail(evidence) == "1 debates visible without auth"
    assert evidence["debate_count"] == 1
    assert evidence["items"][0]["models"] == ["claude-sonnet-4.5", "codex-gpt-5"]


def test_public_list_evidence_rejects_archived_rows() -> None:
    module = load_acceptance_module()

    with pytest.raises(module.AcceptanceError, match="archived"):
        module.public_list_evidence(
            {
                "limit": 50,
                "offset": 0,
                "items": [
                    {
                        "id": "debate-1",
                        "topic": "Topic",
                        "status": "archived",
                        "created_at": "2026-05-24T00:00:00+00:00",
                        "completed_at": None,
                        "models": [],
                    }
                ],
            }
        )


def test_public_list_evidence_rejects_timestamp_without_timezone() -> None:
    module = load_acceptance_module()

    with pytest.raises(module.AcceptanceError, match="created_at missing timezone"):
        module.public_list_evidence(
            {
                "limit": 50,
                "offset": 0,
                "items": [
                    {
                        "id": "debate-1",
                        "topic": "Topic",
                        "status": "complete",
                        "created_at": "2026-05-24T00:00:00",
                        "completed_at": None,
                        "models": [],
                    }
                ],
            }
        )


def test_require_public_list_current_debate_accepts_current_complete_row() -> None:
    module = load_acceptance_module()
    evidence = {
        "items": [
            {
                "id": "debate-1",
                "topic": "Topic",
                "status": "complete",
                "models": ["codex-gpt-5", "gemini-2.5-pro"],
            }
        ]
    }

    module.require_public_list_current_debate(
        evidence,
        "debate-1",
        "Topic",
        {"codex-gpt-5", "gemini-2.5-pro"},
    )


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda row: row.update({"id": "other-debate"}), "missing current debate"),
        (lambda row: row.update({"topic": "Stale topic"}), "topic mismatch"),
        (lambda row: row.update({"status": "generating"}), "not complete"),
        (lambda row: row.update({"models": ["codex-gpt-5"]}), "missing model badges"),
    ],
)
def test_require_public_list_current_debate_rejects_stale_rows(mutator, message: str) -> None:
    module = load_acceptance_module()
    row = {
        "id": "debate-1",
        "topic": "Topic",
        "status": "complete",
        "models": ["codex-gpt-5", "gemini-2.5-pro"],
    }
    mutator(row)
    evidence = {"items": [row]}

    with pytest.raises(module.AcceptanceError, match=message):
        module.require_public_list_current_debate(
            evidence,
            "debate-1",
            "Topic",
            {"codex-gpt-5", "gemini-2.5-pro"},
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://debate.example.com",
        "https://sub.domain.example.com/",
    ],
)
def test_named_https_url_issue_accepts_named_https_origin(url: str) -> None:
    module = load_acceptance_module()

    assert module.named_https_url_issue(url) is None


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("", "empty URL"),
        ("http://debate.example.com", "must be an HTTPS URL"),
        ("https://debate.<your-domain>", "placeholder URL"),
        ("https://localhost", "must use a public DNS hostname"),
        ("https://127.0.0.1", "must use a public DNS hostname"),
        ("https://temporary.trycloudflare.com", "trycloudflare.com quick tunnel"),
        ("https://debate.example.com/path", "without a path"),
        ("https://user:pass@debate.example.com", "must not include credentials"),
    ],
)
def test_named_https_url_issue_rejects_non_final_origins(url: str, message: str) -> None:
    module = load_acceptance_module()

    assert message in str(module.named_https_url_issue(url))


def test_require_generated_node_metadata_reports_argument_metadata() -> None:
    module = load_acceptance_module()
    debate = {
        "tree": {
            "id": "root",
            "node_type": "ROOT_CLAIM",
            "children": [
                {
                    "id": "node-1",
                    "node_type": "PRO",
                    "status": "complete",
                    "active_generation_id": "generation-1",
                    "active_generation": {
                        "id": "generation-1",
                        "model_id": "mock-alpha",
                        "worker_id": "worker-1",
                        "worker_name": "mac-mini",
                        "role": "proposer",
                        "argument": "Argument text",
                    },
                    "children": [],
                }
            ],
        }
    }

    assert module.require_generated_node_metadata(debate) == "1 argument nodes; 1 models; 1 workers"
    evidence = module.generated_node_metadata_evidence(debate)
    assert evidence["argument_node_count"] == 1
    assert evidence["model_count"] == 1
    assert evidence["worker_count"] == 1
    assert evidence["model_ids"] == ["mock-alpha"]
    assert evidence["worker_names"] == ["mac-mini"]
    assert evidence["nodes"] == [
        {
            "id": "node-1",
            "node_type": "PRO",
            "status": "complete",
            "active_generation_id": "generation-1",
            "generation_id": "generation-1",
            "model_id": "mock-alpha",
            "worker_id": "worker-1",
            "worker_name": "mac-mini",
            "role": "proposer",
            "argument_present": True,
            "argument_length": len("Argument text"),
        }
    ]


def test_require_generated_node_metadata_rejects_missing_worker_name() -> None:
    module = load_acceptance_module()
    debate = {
        "tree": {
            "id": "root",
            "node_type": "ROOT_CLAIM",
            "children": [
                {
                    "id": "node-1",
                    "node_type": "CON",
                    "status": "complete",
                    "active_generation_id": "generation-1",
                    "active_generation": {
                        "id": "generation-1",
                        "model_id": "mock-alpha",
                        "worker_id": "worker-1",
                        "role": "opponent",
                        "argument": "Argument text",
                    },
                    "children": [],
                }
            ],
        }
    }

    with pytest.raises(module.AcceptanceError, match="missing worker_name"):
        module.require_generated_node_metadata(debate)


def test_require_synthesis_evidence_returns_structured_fields() -> None:
    module = load_acceptance_module()
    synthesis = {
        "id": "synthesis-1",
        "debate_id": "debate-1",
        "strongest_pro": "Pro text",
        "strongest_con": "Con text",
        "verdict": "Verdict text",
        "model_id": "codex-gpt-5",
        "worker_id": "worker-1",
        "worker_name": "mac-mini",
        "created_at": "2026-05-24T00:00:00+00:00",
    }

    assert module.require_synthesis_evidence(synthesis, "Initial") == synthesis


def test_require_synthesis_evidence_rejects_missing_verdict() -> None:
    module = load_acceptance_module()
    synthesis = {
        "id": "synthesis-1",
        "debate_id": "debate-1",
        "strongest_pro": "Pro text",
        "strongest_con": "Con text",
        "model_id": "codex-gpt-5",
        "worker_id": "worker-1",
        "worker_name": "mac-mini",
        "created_at": "2026-05-24T00:00:00+00:00",
    }

    with pytest.raises(module.AcceptanceError, match="Initial synthesis missing verdict"):
        module.require_synthesis_evidence(synthesis, "Initial")


def test_require_synthesis_evidence_rejects_bad_created_at() -> None:
    module = load_acceptance_module()
    synthesis = {
        "id": "synthesis-1",
        "debate_id": "debate-1",
        "strongest_pro": "Pro text",
        "strongest_con": "Con text",
        "verdict": "Verdict text",
        "model_id": "codex-gpt-5",
        "worker_id": "worker-1",
        "worker_name": "mac-mini",
        "created_at": "not-a-date",
    }

    with pytest.raises(module.AcceptanceError, match="created_at is not ISO formatted"):
        module.require_synthesis_evidence(synthesis, "Initial")


def test_require_synthesis_evidence_rejects_created_at_without_timezone() -> None:
    module = load_acceptance_module()
    synthesis = {
        "id": "synthesis-1",
        "debate_id": "debate-1",
        "strongest_pro": "Pro text",
        "strongest_con": "Con text",
        "verdict": "Verdict text",
        "model_id": "codex-gpt-5",
        "worker_id": "worker-1",
        "worker_name": "mac-mini",
        "created_at": "2026-05-24T00:00:00",
    }

    with pytest.raises(module.AcceptanceError, match="Initial synthesis created_at missing timezone"):
        module.require_synthesis_evidence(synthesis, "Initial")


def test_worker_status_payload_evidence_records_counts_and_rows() -> None:
    module = load_acceptance_module()
    workers = [
        {
            "id": WORKER_B_ID,
            "name": "adesso-mbp",
            "status": "offline",
            "capabilities": ["claude-sonnet-4.5"],
            "current_job_id": None,
            "last_seen": "2026-05-24T00:00:00+00:00",
        },
        {
            "id": WORKER_A_ID,
            "name": "mac-mini",
            "status": "online",
            "capabilities": ["codex-gpt-5", "claude-sonnet-4.5"],
            "current_job_id": JOB_ID,
            "last_seen": "2026-05-24T02:00:01+02:00",
        },
    ]

    evidence = module.worker_status_payload_evidence(workers, [workers[1]])

    assert module.worker_status_payload_detail(evidence) == "2 workers; 2 capabilities; 1 busy"
    assert module.require_worker_status_payload(workers, [workers[1]]) == "2 workers; 2 capabilities; 1 busy"
    assert evidence == {
        "worker_count": 2,
        "online_count": 1,
        "offline_count": 1,
        "degraded_count": 0,
        "busy_count": 1,
        "capability_count": 2,
        "capabilities": ["claude-sonnet-4.5", "codex-gpt-5"],
        "online_worker_names": ["mac-mini"],
        "offline_worker_names": ["adesso-mbp"],
        "degraded_worker_names": [],
        "workers": [
            {
                "id": WORKER_B_ID,
                "name": "adesso-mbp",
                "status": "offline",
                "capabilities": ["claude-sonnet-4.5"],
                "current_job_id": None,
                "last_seen": "2026-05-24T00:00:00+00:00",
            },
            {
                "id": WORKER_A_ID,
                "name": "mac-mini",
                "status": "online",
                "capabilities": ["claude-sonnet-4.5", "codex-gpt-5"],
                "current_job_id": JOB_ID,
                "last_seen": "2026-05-24T00:00:01+00:00",
            },
        ],
    }


def test_worker_status_payload_evidence_rejects_online_worker_without_capabilities() -> None:
    module = load_acceptance_module()
    worker = {
        "id": WORKER_A_ID,
        "name": "mac-mini",
        "status": "online",
        "capabilities": [],
        "current_job_id": None,
        "last_seen": "2026-05-24T00:00:01+00:00",
    }

    with pytest.raises(module.AcceptanceError, match="Online worker mac-mini has no capabilities"):
        module.worker_status_payload_evidence([worker], [worker])


def test_worker_status_payload_evidence_rejects_last_seen_without_timezone() -> None:
    module = load_acceptance_module()
    worker = {
        "id": WORKER_A_ID,
        "name": "mac-mini",
        "status": "online",
        "capabilities": ["codex-gpt-5"],
        "current_job_id": None,
        "last_seen": "2026-05-24T00:00:01",
    }

    with pytest.raises(module.AcceptanceError, match="Worker mac-mini last_seen missing timezone"):
        module.worker_status_payload_evidence([worker], [worker])


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda row: row.update({"id": "not-a-uuid"}), "Worker mac-mini id is not a UUID"),
        (lambda row: row.update({"current_job_id": "not-a-uuid"}), "Worker mac-mini current_job_id is not a UUID"),
        (lambda row: row.pop("current_job_id"), "Worker mac-mini missing current_job_id"),
    ],
)
def test_worker_status_payload_evidence_rejects_malformed_worker_identity(
    mutator,
    message: str,
) -> None:
    module = load_acceptance_module()
    worker = {
        "id": WORKER_A_ID,
        "name": "mac-mini",
        "status": "online",
        "capabilities": ["codex-gpt-5"],
        "current_job_id": JOB_ID,
        "last_seen": "2026-05-24T00:00:01+00:00",
    }
    mutator(worker)

    with pytest.raises(module.AcceptanceError, match=message):
        module.worker_status_payload_evidence([worker], [worker])


@pytest.mark.parametrize(
    ("capabilities", "message"),
    [
        (["codex-gpt-5", ""], "Worker mac-mini capability 2 is blank"),
        (["codex-gpt-5", "codex-gpt-5"], "Worker mac-mini duplicate capability: codex-gpt-5"),
        (["codex-gpt-5", 7], "Worker mac-mini capability 2 is not a string"),
    ],
)
def test_worker_status_payload_evidence_rejects_malformed_capabilities(capabilities, message: str) -> None:
    module = load_acceptance_module()
    worker = {
        "id": WORKER_A_ID,
        "name": "mac-mini",
        "status": "online",
        "capabilities": capabilities,
        "current_job_id": None,
        "last_seen": "2026-05-24T00:00:01+00:00",
    }

    with pytest.raises(module.AcceptanceError, match=message):
        module.worker_status_payload_evidence([worker], [worker])


def test_worker_status_evidence_normalizes_timezone_aware_last_seen_to_utc() -> None:
    module = load_acceptance_module()
    rows = module.worker_status_evidence(
        [
            {
                "id": WORKER_A_ID,
                "name": "mac-mini",
                "status": "online",
                "capabilities": ["codex-gpt-5"],
                "current_job_id": None,
                "last_seen": "2026-05-24T02:00:01+02:00",
            }
        ]
    )

    assert rows[0]["last_seen"] == "2026-05-24T00:00:01+00:00"


def test_worker_status_evidence_rejects_bad_worker_rows() -> None:
    module = load_acceptance_module()

    with pytest.raises(module.AcceptanceError, match="Worker mac-mini id is not a UUID"):
        module.worker_status_evidence(
            [
                {
                    "id": "worker-1",
                    "name": "mac-mini",
                    "status": "online",
                    "capabilities": ["codex-gpt-5"],
                    "current_job_id": None,
                    "last_seen": "2026-05-24T02:00:01+02:00",
                }
            ]
        )


def test_require_node_started_payloads_accepts_complete_metadata() -> None:
    module = load_acceptance_module()

    module.require_node_started_payloads(
        [{"node_id": "node-1", "model_id": "mock-alpha", "worker_id": "worker-1", "role": "proposer"}],
        "SSE stream",
    )


def test_require_node_started_payloads_rejects_incomplete_regenerate_event() -> None:
    module = load_acceptance_module()

    with pytest.raises(module.AcceptanceError, match="model_id"):
        module.require_node_started_payloads([{"node_id": "node-1", "regenerating": True}], "SSE stream")


def test_require_synthesis_started_payloads_rejects_missing_worker() -> None:
    module = load_acceptance_module()

    with pytest.raises(module.AcceptanceError, match="worker_id"):
        module.require_synthesis_started_payloads(
            [{"debate_id": "debate-1", "model_id": "mock-alpha"}],
            "SSE stream",
        )


def test_require_node_complete_payloads_rejects_missing_generation() -> None:
    module = load_acceptance_module()

    with pytest.raises(module.AcceptanceError, match="generation_id"):
        module.require_node_complete_payloads([{"node_id": "node-1"}], "SSE stream")


def test_require_synthesis_complete_payloads_rejects_missing_verdict() -> None:
    module = load_acceptance_module()

    with pytest.raises(module.AcceptanceError, match="verdict"):
        module.require_synthesis_complete_payloads(
            [{"synthesis": {"strongest_pro": "Pro.", "strongest_con": "Con."}}],
            "SSE stream",
        )


def test_require_debate_complete_payloads_rejects_mismatched_debate_id() -> None:
    module = load_acceptance_module()

    with pytest.raises(module.AcceptanceError, match="debate_id mismatch"):
        module.require_debate_complete_payloads([{"debate_id": "debate-2"}], "SSE stream", "debate-1")


def test_sse_stream_evidence_reports_required_event_counts() -> None:
    module = load_acceptance_module()

    class Recorder:
        stopped = False
        replay_history = True
        debate_id = "debate-1"

        def stop(self):  # noqa: ANN001
            self.stopped = True

        def snapshot(self):  # noqa: ANN001
            return (
                [
                    "connected",
                    "node_started",
                    "node_token",
                    "node_token",
                    "node_complete",
                    "synthesis_started",
                    "synthesis_token",
                    "synthesis_complete",
                    "debate_complete",
                ],
                [],
                [{"node_id": "node-1", "model_id": "mock-alpha", "worker_id": "worker-1", "role": "proposer"}],
                [{"node_id": "node-1", "generation_id": "generation-1"}],
                [{"debate_id": "debate-1", "model_id": "mock-beta", "worker_id": "worker-1"}],
                [{"synthesis": {"strongest_pro": "Pro.", "strongest_con": "Con.", "verdict": "Verdict."}}],
                [{"debate_id": "debate-1"}],
                2,
                1,
                None,
            )

    recorder = Recorder()
    evidence = module.sse_stream_evidence(recorder)

    assert recorder.stopped is True
    assert module.sse_stream_detail(evidence) == "9 events, 2 node tokens, 1 synthesis tokens"
    assert evidence["event_count"] == 9
    assert evidence["replay_history"] is True
    assert evidence["event_sequence"] == [
        "connected",
        "node_started",
        "node_token",
        "node_token",
        "node_complete",
        "synthesis_started",
        "synthesis_token",
        "synthesis_complete",
        "debate_complete",
    ]
    assert evidence["node_token_count"] == 2
    assert evidence["synthesis_token_count"] == 1
    assert evidence["event_type_counts"]["node_token"] == 2
    assert evidence["required_events_present"]["debate_complete"] is True
    assert evidence["node_started_count"] == 1
    assert evidence["node_complete_count"] == 1
    assert evidence["synthesis_started_count"] == 1
    assert evidence["synthesis_complete_count"] == 1
    assert evidence["debate_complete_count"] == 1
    assert evidence["synthesis_complete_payloads"][0]["synthesis"]["verdict"] == "Verdict."
    assert evidence["debate_complete_payloads"][0]["debate_id"] == "debate-1"


def test_sse_stream_evidence_rejects_out_of_order_events() -> None:
    module = load_acceptance_module()

    class Recorder:
        debate_id = "debate-1"

        def stop(self):  # noqa: ANN001
            pass

        def snapshot(self):  # noqa: ANN001
            return (
                [
                    "connected",
                    "node_started",
                    "node_token",
                    "synthesis_started",
                    "node_complete",
                    "synthesis_token",
                    "synthesis_complete",
                    "debate_complete",
                ],
                [],
                [{"node_id": "node-1", "model_id": "mock-alpha", "worker_id": "worker-1", "role": "proposer"}],
                [{"node_id": "node-1", "generation_id": "generation-1"}],
                [{"debate_id": "debate-1", "model_id": "mock-beta", "worker_id": "worker-1"}],
                [{"synthesis": {"strongest_pro": "Pro.", "strongest_con": "Con.", "verdict": "Verdict."}}],
                [{"debate_id": "debate-1"}],
                1,
                1,
                None,
            )

    with pytest.raises(module.AcceptanceError, match="before all node_complete events completed"):
        module.sse_stream_evidence(Recorder())


def test_sse_stream_evidence_requires_initial_tree_ready_payload() -> None:
    module = load_acceptance_module()

    class Recorder:
        debate_id = "debate-1"

        def stop(self):  # noqa: ANN001
            pass

        def snapshot(self):  # noqa: ANN001
            return (
                [
                    "connected",
                    "tree_ready",
                    "node_started",
                    "node_token",
                    "node_complete",
                    "synthesis_started",
                    "synthesis_token",
                    "synthesis_complete",
                    "debate_complete",
                ],
                [{"tree": {"id": "root-1", "children": [{"id": "child-1"}]}}],
                [{"node_id": "node-1", "model_id": "mock-alpha", "worker_id": "worker-1", "role": "proposer"}],
                [{"node_id": "node-1", "generation_id": "generation-1"}],
                [{"debate_id": "debate-1", "model_id": "mock-beta", "worker_id": "worker-1"}],
                [{"synthesis": {"strongest_pro": "Pro.", "strongest_con": "Con.", "verdict": "Verdict."}}],
                [{"debate_id": "debate-1"}],
                1,
                1,
                None,
            )

    evidence = module.sse_stream_evidence(Recorder(), require_tree_ready=True)

    assert evidence["required_events_present"]["tree_ready"] is True
    assert evidence["tree_ready_required"] is True
    assert evidence["tree_ready_count"] == 1
    assert evidence["tree_ready_payloads"][0]["tree"]["id"] == "root-1"


def test_sse_stream_evidence_rejects_missing_initial_tree_ready() -> None:
    module = load_acceptance_module()

    class Recorder:
        debate_id = "debate-1"

        def stop(self):  # noqa: ANN001
            pass

        def snapshot(self):  # noqa: ANN001
            return (
                [
                    "connected",
                    "node_started",
                    "node_token",
                    "node_complete",
                    "synthesis_started",
                    "synthesis_token",
                    "synthesis_complete",
                    "debate_complete",
                ],
                [],
                [{"node_id": "node-1", "model_id": "mock-alpha", "worker_id": "worker-1", "role": "proposer"}],
                [{"node_id": "node-1", "generation_id": "generation-1"}],
                [{"debate_id": "debate-1", "model_id": "mock-beta", "worker_id": "worker-1"}],
                [{"synthesis": {"strongest_pro": "Pro.", "strongest_con": "Con.", "verdict": "Verdict."}}],
                [{"debate_id": "debate-1"}],
                1,
                1,
                None,
            )

    with pytest.raises(module.AcceptanceError, match="missed tree_ready"):
        module.sse_stream_evidence(Recorder(), require_tree_ready=True)


def test_choose_decomposer_override_model_prefers_enabled_routing_candidate() -> None:
    module = load_acceptance_module()
    settings = {
        "routing": {"decomposer": {"primary": "claude", "fallback": ["codex"]}},
        "enabled_models": ["codex"],
    }
    online = [{"capabilities": ["claude", "codex"]}]

    assert module.choose_decomposer_override_model(settings, online) == "codex"


def test_choose_decomposer_override_model_falls_back_to_online_capability() -> None:
    module = load_acceptance_module()
    settings = {"routing": {"decomposer": {"primary": "claude", "fallback": []}}, "enabled_models": []}
    online = [{"capabilities": ["mock-beta", "mock-alpha"]}]

    assert module.choose_decomposer_override_model(settings, online) == "mock-alpha"


def test_require_decomposer_role_override_accepts_persisted_root_model() -> None:
    module = load_acceptance_module()
    debate = {
        "config": {"role_overrides": {"decomposer": {"primary": "codex", "fallback": []}}},
        "tree": {"active_generation": {"model_id": "codex"}},
    }

    assert module.require_decomposer_role_override(debate, "codex") == (
        "decomposer primary codex; persisted and used by root job"
    )
    evidence = module.role_override_evidence(debate, "codex")
    assert module.role_override_detail(evidence) == "decomposer primary codex; persisted and used by root job"
    assert evidence["persisted"] is True
    assert evidence["root_job_used_override"] is True
    assert evidence["root_generation_model_id"] == "codex"


def test_debate_lifecycle_evidence_records_create_skeleton_timing_and_persistence() -> None:
    module = load_acceptance_module()
    created = {
        "id": "debate-1",
        "topic": "Topic",
        "status": "generating",
        "config": {
            "max_depth": 1,
            "branching": 2,
            "role_overrides": {"decomposer": {"primary": "codex", "fallback": []}},
        },
        "created_at": "2026-05-24T00:00:00+00:00",
        "root_node_id": "root-1",
    }
    skeleton = {
        **created,
        "node_count": 3,
        "tree": {
            "id": "root-1",
            "status": "complete",
            "active_generation_id": "generation-root",
            "active_generation": {"id": "generation-root", "model_id": "codex"},
            "children": [
                {
                    "id": "node-1",
                    "node_type": "PRO",
                    "depth": 1,
                    "position": 0,
                    "status": "pending",
                    "claim": "Pro claim",
                    "active_generation_id": "generation-pro",
                    "active_generation": {
                        "id": "generation-pro",
                        "model_id": "codex",
                        "worker_name": "mac-mini",
                    },
                },
                {
                    "id": "node-2",
                    "node_type": "CON",
                    "depth": 1,
                    "position": 1,
                    "status": "pending",
                    "claim": "Con claim",
                    "active_generation_id": "generation-con",
                    "active_generation": {
                        "id": "generation-con",
                        "model_id": "gemini",
                        "worker_name": "adesso-mbp",
                    },
                },
            ],
        },
    }
    complete = {
        **skeleton,
        "status": "complete",
        "synthesis_id": "synthesis-1",
        "synthesis": {"model_id": "codex"},
    }

    create_evidence = module.create_debate_evidence(created, "Topic", 1, 2, "codex")
    skeleton_evidence = module.tree_skeleton_evidence(skeleton, "debate-1", 2)
    timing_evidence = module.tree_skeleton_timing_evidence(1.25, 20)
    persistence_evidence = module.persistence_evidence(complete, complete, "debate-1")

    assert create_evidence["debate_id"] == "debate-1"
    assert create_evidence["config_max_depth"] == 1
    assert module.tree_skeleton_detail(skeleton_evidence) == "3 nodes"
    assert skeleton_evidence["child_node_types"] == ["CON", "PRO"]
    assert module.tree_skeleton_timing_detail(timing_evidence) == "1.25s <= 20s"
    assert persistence_evidence["exact_payload_match"] is True
    assert persistence_evidence["topic"] == "Topic"
    assert persistence_evidence["model_ids"] == ["codex", "gemini"]
    assert persistence_evidence["worker_names"] == ["adesso-mbp", "mac-mini"]
    assert persistence_evidence["active_generation_ids"] == [
        "generation-con",
        "generation-pro",
        "generation-root",
    ]
    assert persistence_evidence["active_generation_count"] == 3
    assert module.persistence_detail(persistence_evidence) == "revisited debate-1; exact detail match"


def test_require_decomposer_role_override_rejects_wrong_root_model() -> None:
    module = load_acceptance_module()
    debate = {
        "config": {"role_overrides": {"decomposer": {"primary": "codex", "fallback": []}}},
        "tree": {"active_generation": {"model_id": "claude"}},
    }

    with pytest.raises(module.AcceptanceError, match="did not use override"):
        module.require_decomposer_role_override(debate, "codex")


def test_require_markdown_generation_history_accepts_preserved_archived_generation() -> None:
    module = load_acceptance_module()
    markdown = (
        "# Debate: Topic\n\n"
        "## Generation History\n\n"
        "- **Active** `generation-new` - *mock-beta* (worker: mac-mini)\n"
        "  > New argument.\n\n"
        "- **Archived** `generation-old` - *mock-alpha* (worker: mac-mini)\n"
        "  > Old argument.\n"
    )
    history_items = [
        {
            "id": "generation-new",
            "model_id": "mock-beta",
            "worker_name": "mac-mini",
            "argument": "New argument.",
            "is_active": True,
        },
        {
            "id": "generation-old",
            "model_id": "mock-alpha",
            "worker_name": "mac-mini",
            "argument": "Old argument.",
            "is_active": False,
        },
    ]

    assert module.require_markdown_generation_history(markdown, history_items) == "2 generations; 1 archived"


def test_require_markdown_generation_history_rejects_missing_archived_argument() -> None:
    module = load_acceptance_module()
    markdown = (
        "# Debate: Topic\n\n"
        "## Generation History\n\n"
        "- **Active** `generation-new` - *mock-beta* (worker: mac-mini)\n"
        "  > New argument.\n\n"
        "- **Archived** `generation-old` - *mock-alpha* (worker: mac-mini)\n"
    )
    history_items = [
        {
            "id": "generation-new",
            "model_id": "mock-beta",
            "worker_name": "mac-mini",
            "argument": "New argument.",
            "is_active": True,
        },
        {
            "id": "generation-old",
            "model_id": "mock-alpha",
            "worker_name": "mac-mini",
            "argument": "Old argument.",
            "is_active": False,
        },
    ]

    with pytest.raises(module.AcceptanceError, match="argument"):
        module.require_markdown_generation_history(markdown, history_items)


def test_generation_history_evidence_promotes_active_and_archived_rows() -> None:
    module = load_acceptance_module()
    archived = {
        "id": "generation-old",
        "model_id": "codex-gpt-5",
        "worker_id": "worker-1",
        "worker_name": "mac-mini",
        "role": "proposer",
        "is_active": False,
        "created_at": "2026-05-24T00:00:00+00:00",
        "argument": "Archived argument.",
        "latency_ms": 123,
        "tokens_in": 10,
        "tokens_out": 20,
    }
    active = {
        "id": "generation-new",
        "model_id": "claude-sonnet-4.5",
        "worker_id": "worker-1",
        "worker_name": "mac-mini",
        "role": "proposer",
        "is_active": True,
        "created_at": "2026-05-24T00:00:01+00:00",
        "argument": "Active argument.",
        "latency_ms": 456,
        "tokens_in": None,
        "tokens_out": 30,
    }

    evidence = module.generation_history_evidence("node-1", [archived, active], archived, active)

    assert evidence["node_id"] == "node-1"
    assert evidence["generation_count"] == 2
    assert evidence["active_count"] == 1
    assert evidence["archived_count"] == 1
    assert evidence["active_generation"]["id"] == "generation-new"
    assert evidence["active_generation"]["argument_present"] is True
    assert evidence["active_generation"]["argument_length"] == len("Active argument.")
    assert evidence["active_generation"]["latency_ms"] == 456
    assert evidence["active_generation"]["tokens_in"] is None
    assert evidence["active_generation"]["tokens_out"] == 30
    assert evidence["archived_generation"]["id"] == "generation-old"
    assert evidence["archived_generation"]["argument_present"] is True
    assert evidence["archived_generation"]["latency_ms"] == 123


def test_regenerate_request_evidence_records_job_and_previous_ids() -> None:
    module = load_acceptance_module()

    evidence = module.regenerate_request_evidence(
        {"job_id": "job-1", "status": "queued"},
        "debate-1",
        "node-1",
        "generation-old",
        "synthesis-initial",
    )

    assert evidence == {
        "debate_id": "debate-1",
        "node_id": "node-1",
        "job_id": "job-1",
        "status": "queued",
        "previous_generation_id": "generation-old",
        "previous_synthesis_id": "synthesis-initial",
        "accepted": True,
    }
    assert module.regenerate_request_detail(evidence) == "job job-1 for node node-1"


def test_regenerate_request_evidence_requires_queued_status() -> None:
    module = load_acceptance_module()

    with pytest.raises(module.AcceptanceError, match="status was not queued"):
        module.regenerate_request_evidence(
            {"job_id": "job-1", "status": "running"},
            "debate-1",
            "node-1",
            "generation-old",
            "synthesis-initial",
        )


def test_markdown_export_evidence_promotes_headers_sections_and_metadata() -> None:
    module = load_acceptance_module()
    response = httpx.Response(
        200,
        headers={
            "content-disposition": 'attachment; filename="debate-debate-1.md"',
            "content-type": "text/markdown; charset=utf-8",
        },
        text=(
            "# Debate: Topic\n\n"
            "## Synthesis\n\n"
            "## Tree\n\n"
            "**Workers:** mac-mini\n"
            "**Models:** codex-gpt-5\n"
            "## Generation History\n"
        ),
    )
    history_items = [
        {"id": "generation-old", "is_active": False},
        {"id": "generation-new", "is_active": True},
    ]

    evidence = module.markdown_export_evidence(
        response,
        "Topic",
        "debate-1",
        {"mac-mini"},
        {"codex-gpt-5"},
        history_items,
    )

    assert evidence["byte_count"] == len(response.text)
    assert evidence["debate_id"] == "debate-1"
    assert evidence["topic"] == "Topic"
    assert evidence["attachment"] is True
    assert evidence["filename"] is True
    assert evidence["filename_debate_id"] is True
    assert evidence["synthesis_section"] is True
    assert evidence["tree_section"] is True
    assert evidence["generation_history_section"] is True
    assert evidence["worker_names"] == ["mac-mini"]
    assert evidence["model_ids"] == ["codex-gpt-5"]
    assert evidence["history_generation_ids"] == ["generation-new", "generation-old"]
    assert evidence["active_generation_ids"] == ["generation-new"]
    assert evidence["archived_generation_ids"] == ["generation-old"]
    assert evidence["history_generation_count"] == 2
    assert evidence["archived_history_count"] == 1


def test_stable_json_sorts_nested_payloads() -> None:
    module = load_acceptance_module()

    assert module.stable_json({"b": 2, "a": {"d": 4, "c": 3}}) == '{"a":{"c":3,"d":4},"b":2}'


def test_write_report_promotes_structured_worker_model_evidence(tmp_path: Path) -> None:
    module = load_acceptance_module()
    report = tmp_path / "acceptance.json"
    args = argparse.Namespace(
        base_url="https://debate.example.com",
        web_base_url=None,
        phase="failover-one-worker",
        expected_workers=1,
        expected_worker_names="mac-mini",
        expected_offline_worker_names="adesso-mbp",
        require_expected_workers_in_tree=False,
        require_different_regen_model=True,
        require_named_https=True,
        skip_web_checks=False,
        skip_sse_check=False,
        topic="Topic",
        depth=1,
        branching=2,
    )
    results = [
        module.CheckResult(
            "workers-online",
            "mac-mini",
            [
                {
                    "id": "worker-mac-mini",
                    "name": "mac-mini",
                    "status": "online",
                    "capabilities": ["codex-gpt-5"],
                    "current_job_id": None,
                    "last_seen": "2026-05-24T00:00:00+00:00",
                }
            ],
        ),
        module.CheckResult(
            "workers-offline",
            "adesso-mbp",
            [
                {
                    "id": "worker-adesso-mbp",
                    "name": "adesso-mbp",
                    "status": "offline",
                    "capabilities": [],
                    "current_job_id": None,
                    "last_seen": "2026-05-24T00:00:00+00:00",
                }
            ],
        ),
        module.CheckResult("generated-workers", "mac-mini", ["mac-mini"]),
        module.CheckResult("regenerated-workers", "mac-mini", ["mac-mini"]),
        module.CheckResult("generated-models", "codex-gpt-5", ["codex-gpt-5"]),
        module.CheckResult("regenerated-models", "claude-sonnet-4.5", ["claude-sonnet-4.5"]),
        module.CheckResult(
            "regeneration-model-switch",
            "codex-gpt-5 -> claude-sonnet-4.5",
            {"old_model": "codex-gpt-5", "new_model": "claude-sonnet-4.5"},
        ),
    ]

    module.write_report(str(report), args, "passed", results, "2026-05-24T00:00:00+00:00")

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["online_workers"][0]["id"] == "worker-mac-mini"
    assert payload["phase"] == "failover-one-worker"
    assert payload["online_workers"][0]["name"] == "mac-mini"
    assert payload["require_named_https"] is True
    assert payload["offline_workers"][0]["id"] == "worker-adesso-mbp"
    assert payload["offline_workers"][0]["name"] == "adesso-mbp"
    assert payload["observed_worker_names"] == ["adesso-mbp", "mac-mini"]
    assert payload["observed_model_ids"] == ["claude-sonnet-4.5", "codex-gpt-5"]
    assert payload["regeneration_model_switch"] == {
        "new_model": "claude-sonnet-4.5",
        "old_model": "codex-gpt-5",
    }
    switch_result = next(result for result in payload["results"] if result["name"] == "regeneration-model-switch")
    assert switch_result["evidence"]["new_model"] == "claude-sonnet-4.5"


def test_require_settings_round_trip_verifies_generic_model_caps() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = "{}"

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Client:
        def __init__(self):
            self.settings = {
                "routing": {
                    "decomposer": {"primary": "mock-local", "fallback": []},
                    "proposer": {"pool": ["mock-local", "grok-4"], "strategy": "round_robin"},
                },
                "configured_models": ["grok-4", "mock-local"],
                "enabled_models": ["grok-4", "mock-local"],
                "grok_monthly_cap_usd": 25.0,
                "grok_monthly_spend_usd": 0.0,
                "grok_pricing_usd_per_million_tokens": {"input": 1.25, "output": 2.5},
                "model_monthly_caps_usd": {"grok-4": 25.0},
                "model_monthly_spend_usd": {"grok-4": 0.0, "mock-local": 0.0},
                "model_pricing_usd_per_million_tokens": {"grok-4": {"input": 1.25, "output": 2.5}},
            }
            self.put_payloads = []

        def request(self, method, path, **kwargs):  # noqa: ANN001
            assert path == "/api/settings"
            if method == "PUT":
                payload = kwargs["json"]
                self.put_payloads.append(payload)
                self.settings["enabled_models"] = payload["enabled_models"]
                self.settings["grok_monthly_cap_usd"] = payload["grok_monthly_cap_usd"]
                caps = dict(payload["model_monthly_caps_usd"])
                caps["grok-4"] = payload["grok_monthly_cap_usd"]
                self.settings["model_monthly_caps_usd"] = caps
            return Response(dict(self.settings))

    client = Client()

    detail = module.require_settings_round_trip(client, "user-token")

    assert "model cap restored for mock-local" in detail
    assert client.settings["enabled_models"] == ["grok-4", "mock-local"]
    assert client.settings["model_monthly_caps_usd"] == {"grok-4": 25.0}
    assert any(payload["model_monthly_caps_usd"].get("mock-local") == 1.0 for payload in client.put_payloads)
    evidence = module.settings_round_trip_evidence(client, "user-token")
    assert module.settings_round_trip_detail(evidence) == (
        "2 configured models; model cap restored for mock-local; Grok cap $25.00"
    )
    assert evidence["configured_model_count"] == 2
    assert evidence["configured_models"] == ["grok-4", "mock-local"]
    assert evidence["cap_model"] == "mock-local"
    assert evidence["temporary_enabled_models"] == ["mock-local"]
    assert evidence["enabled_models_restored"] is True
    assert evidence["grok_cap_restored"] is True
    assert evidence["model_cap_restored"] is True
    assert evidence["temporary_model_cap_usd"] == 1.0
    assert evidence["restored_model_cap_usd"] == 0.0
    assert evidence["model_monthly_spend_models"] == ["grok-4", "mock-local"]


def test_require_settings_round_trip_handles_grok_only_routing() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = "{}"

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Client:
        def __init__(self):
            self.settings = {
                "routing": {"decomposer": {"primary": "grok-4", "fallback": []}},
                "configured_models": ["grok-4"],
                "enabled_models": ["grok-4"],
                "grok_monthly_cap_usd": 25.0,
                "grok_monthly_spend_usd": 0.0,
                "grok_pricing_usd_per_million_tokens": {"input": 1.25, "output": 2.5},
                "model_monthly_caps_usd": {"grok-4": 25.0},
                "model_monthly_spend_usd": {"grok-4": 0.0},
                "model_pricing_usd_per_million_tokens": {"grok-4": {"input": 1.25, "output": 2.5}},
            }

        def request(self, method, path, **kwargs):  # noqa: ANN001
            assert path == "/api/settings"
            if method == "PUT":
                payload = kwargs["json"]
                self.settings["enabled_models"] = payload["enabled_models"]
                self.settings["grok_monthly_cap_usd"] = payload["grok_monthly_cap_usd"]
                self.settings["model_monthly_caps_usd"] = {"grok-4": payload["grok_monthly_cap_usd"]}
            return Response(dict(self.settings))

    detail = module.require_settings_round_trip(Client(), "user-token")

    assert "model cap restored for grok-4" in detail


def test_require_settings_round_trip_rejects_missing_model_spend() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "routing": {"decomposer": {"primary": "mock-local", "fallback": []}},
                "configured_models": ["mock-local"],
                "enabled_models": ["mock-local"],
                "grok_monthly_cap_usd": 25.0,
                "grok_monthly_spend_usd": 0.0,
                "grok_pricing_usd_per_million_tokens": {"input": 1.25, "output": 2.5},
                "model_monthly_caps_usd": {},
                "model_monthly_spend_usd": {},
                "model_pricing_usd_per_million_tokens": {"grok-4": {"input": 1.25, "output": 2.5}},
            }

    class Client:
        def request(self, method, path, **kwargs):  # noqa: ANN001
            return Response()

    with pytest.raises(module.AcceptanceError, match="missing spend"):
        module.require_settings_round_trip(Client(), "user-token")


def test_require_write_auth_boundaries_accepts_rejected_node_and_archive_routes() -> None:
    module = load_acceptance_module()

    class Response:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    class Client:
        def get(self, path, headers=None):  # noqa: ANN001
            if headers:
                assert headers["Authorization"] == "Bearer invalid-token"
                return Response(403)
            return Response(401)

        def post(self, path, headers=None, json=None):  # noqa: ANN001
            assert json == {}
            if headers:
                assert headers["Authorization"] == "Bearer invalid-token"
                return Response(403)
            return Response(401)

        def delete(self, path, headers=None):  # noqa: ANN001
            if headers:
                assert headers["Authorization"] == "Bearer invalid-token"
                return Response(403)
            return Response(401)

    assert module.require_write_auth_boundaries(Client(), "debate-1", "node-1") == (
        "history, regenerate, and archive reject missing or invalid user tokens"
    )
    evidence = module.write_auth_boundaries_evidence(Client(), "debate-1", "node-1")
    assert evidence == {
        "debate_id": "debate-1",
        "node_id": "node-1",
        "history_blocked": True,
        "regenerate_blocked": True,
        "archive_blocked": True,
        "invalid_token_blocked": True,
        "checks": [
            {
                "label": "unauthenticated generation history",
                "method": "GET",
                "path": "/api/nodes/node-1/generations",
                "status_code": 401,
                "expected_statuses": [401, 403],
                "rejected": True,
            },
            {
                "label": "invalid-token generation history",
                "method": "GET",
                "path": "/api/nodes/node-1/generations",
                "status_code": 403,
                "expected_statuses": [403],
                "rejected": True,
            },
            {
                "label": "unauthenticated regenerate",
                "method": "POST",
                "path": "/api/nodes/node-1/regenerate",
                "status_code": 401,
                "expected_statuses": [401, 403],
                "rejected": True,
            },
            {
                "label": "invalid-token regenerate",
                "method": "POST",
                "path": "/api/nodes/node-1/regenerate",
                "status_code": 403,
                "expected_statuses": [403],
                "rejected": True,
            },
            {
                "label": "unauthenticated archive",
                "method": "DELETE",
                "path": "/api/debates/debate-1",
                "status_code": 401,
                "expected_statuses": [401, 403],
                "rejected": True,
            },
            {
                "label": "invalid-token archive",
                "method": "DELETE",
                "path": "/api/debates/debate-1",
                "status_code": 403,
                "expected_statuses": [403],
                "rejected": True,
            },
        ],
    }


def test_auth_boundaries_evidence_records_public_and_rejected_routes() -> None:
    module = load_acceptance_module()

    class Response:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    evidence = module.auth_boundaries_evidence(
        3,
        Response(401),
        Response(403),
        Response(403),
    )

    assert evidence == {
        "public_read_open": True,
        "write_blocked_without_token": True,
        "settings_blocked_without_token": True,
        "invalid_token_blocked": True,
        "checks": [
            {
                "label": "public-list",
                "method": "GET",
                "path": "/api/debates",
                "status_code": 200,
                "accepted": True,
                "debate_count": 3,
            },
            {
                "label": "unauthenticated create",
                "method": "POST",
                "path": "/api/debates",
                "status_code": 401,
                "expected_statuses": [401, 403],
                "rejected": True,
            },
            {
                "label": "unauthenticated settings",
                "method": "GET",
                "path": "/api/settings",
                "status_code": 403,
                "expected_statuses": [401, 403],
                "rejected": True,
            },
            {
                "label": "invalid-token settings",
                "method": "GET",
                "path": "/api/settings",
                "status_code": 403,
                "expected_statuses": [403],
                "rejected": True,
            },
        ],
    }


def test_require_write_auth_boundaries_rejects_open_regenerate_route() -> None:
    module = load_acceptance_module()

    class Response:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    class Client:
        def get(self, path, headers=None):  # noqa: ANN001
            return Response(403 if headers else 401)

        def post(self, path, headers=None, json=None):  # noqa: ANN001
            return Response(200 if headers is None else 403)

        def delete(self, path, headers=None):  # noqa: ANN001
            return Response(403 if headers else 401)

    with pytest.raises(module.AcceptanceError, match="unauthenticated regenerate"):
        module.require_write_auth_boundaries(Client(), "debate-1", "node-1")


def test_check_web_page_all_rejects_missing_markers() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = "<main>Debate topic Export Markdown</main>"
        headers = {"content-type": "text/html; charset=utf-8"}

    class Client:
        def get(self, path, headers):  # noqa: ANN001
            assert path == "/debate/1"
            assert headers["Accept"] == "text/html"
            return Response()

    with pytest.raises(module.AcceptanceError, match="Strongest Pro"):
        module.check_web_page_all(Client(), "/debate/1", ["Debate topic", "Strongest Pro"])


def test_check_web_auth_gate_requires_all_token_markers() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = "<main>Bearer Token Unlock</main>"
        headers = {"content-type": "text/html; charset=utf-8"}

    class Client:
        def get(self, path, headers):  # noqa: ANN001
            assert path == "/new"
            assert headers["Accept"] == "text/html"
            return Response()

    with pytest.raises(module.AcceptanceError, match="User token"):
        module.check_web_page_all(Client(), "/new", ["Bearer Token", "User token", "Unlock"])


def test_web_home_evidence_records_markers() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = (
            '<main><h1>Debates</h1><p>Public archive</p><a href="/new">New</a>'
            '<a href="/debate/1">A topic</a><span>complete</span><span>codex-gpt-5</span></main>'
        )
        headers = {"content-type": "text/html; charset=utf-8"}

    class Client:
        def get(self, path, headers):  # noqa: ANN001
            assert path == "/"
            assert headers["Accept"] == "text/html"
            return Response()

    evidence = module.web_home_evidence(
        Client(),
        "https://debate.example.com",
        "1",
        "A topic",
        "complete",
        ["codex-gpt-5"],
    )

    assert module.web_home_detail(evidence) == "https://debate.example.com/ returned HTML with /debate/1 for A topic"
    assert evidence["byte_count"] == len(Response.text)
    assert evidence["markers_present"] == {"Debates": True, "Public archive": True}
    assert evidence["debates_heading"] is True
    assert evidence["public_archive_copy"] is True
    assert evidence["new_debate_link"] is True
    assert evidence["debate_link_count"] == 1
    assert evidence["current_debate_id"] == "1"
    assert evidence["current_debate_link"] is True
    assert evidence["current_topic"] == "A topic"
    assert evidence["current_topic_present"] is True
    assert evidence["current_status"] == "complete"
    assert evidence["current_status_present"] is True
    assert evidence["current_model_ids"] == ["codex-gpt-5"]
    assert evidence["current_model_markers_present"] == {"codex-gpt-5": True}


def test_web_auth_gates_evidence_records_each_protected_route() -> None:
    module = load_acceptance_module()
    seen_paths: list[str] = []

    class Response:
        status_code = 200
        text = "<main>Bearer Token User token Unlock</main>"
        headers = {"content-type": "text/html; charset=utf-8"}

    class Client:
        def get(self, path, headers):  # noqa: ANN001
            seen_paths.append(path)
            assert headers["Accept"] == "text/html"
            return Response()

    evidence = module.web_auth_gates_evidence(Client())

    assert seen_paths == ["/new", "/settings", "/admin/workers"]
    assert evidence["route_count"] == 3
    assert evidence["required_markers"] == ["Bearer Token", "User token", "Unlock"]
    assert [route["path"] for route in evidence["routes"]] == ["/new", "/settings", "/admin/workers"]
    for route in evidence["routes"]:
        assert route["byte_count"] == len(Response.text)
        assert route["content_type"] == "text/html; charset=utf-8"
        assert route["bearer_token_prompt"] is True
        assert route["user_token_prompt"] is True
        assert route["unlock_button"] is True


def test_require_web_auth_surfaces_checks_authenticated_page_sources(tmp_path: Path, monkeypatch) -> None:
    module = load_acceptance_module()
    surfaces = {
        "/new": (tmp_path / "new.tsx", ("<AuthGate>", "NewDebateForm", "createDebate(")),
        "/settings": (tmp_path / "settings.tsx", ("<AuthGate>", "SettingsForm", '"/api/settings"')),
        "/admin/workers": (tmp_path / "workers.tsx", ("<AuthGate>", "WorkersView", "backendStatus()")),
    }
    for source_path, markers in surfaces.values():
        source_path.write_text("\n".join(markers), encoding="utf-8")
    monkeypatch.setattr(module, "WEB_AUTH_SURFACES", surfaces)

    assert module.require_web_auth_surfaces() == (
        "post-unlock source markers present for /new, /settings, /admin/workers"
    )
    evidence = module.source_marker_evidence(surfaces, "post-unlock")
    assert evidence["surface_count"] == 3
    assert evidence["marker_count"] == 9
    assert [row["label"] for row in evidence["surfaces"]] == ["/new", "/settings", "/admin/workers"]
    assert evidence["surfaces"][0]["marker_count"] == 3
    assert evidence["surfaces"][0]["markers_present"] is True
    assert "NewDebateForm" in evidence["surfaces"][0]["required_markers"]
    assert "SettingsForm" in evidence["surfaces"][1]["required_markers"]
    assert "WorkersView" in evidence["surfaces"][2]["required_markers"]

    surfaces["/settings"][0].write_text("<AuthGate>\n", encoding="utf-8")
    with pytest.raises(module.AcceptanceError, match="/settings.*SettingsForm"):
        module.require_web_auth_surfaces()


def test_require_web_auth_token_flow_checks_auth_gate_and_api_client(tmp_path: Path, monkeypatch) -> None:
    module = load_acceptance_module()
    sources = {
        "AuthGate": (
            tmp_path / "AuthGate.tsx",
            (
                "getStoredToken()",
                "validateUserToken(stored)",
                "clearStoredToken()",
                "setStoredToken(value)",
                "setToken(value)",
                "children(token)",
            ),
        ),
        "api-client": (
            tmp_path / "api.ts",
            (
                "window.localStorage.getItem(\"dialectical:userToken\")",
                "headers.set(\"Authorization\", `Bearer ${token}`)",
                "apiFetch<Record<string, unknown>>(\"/api/settings\", {}, token)",
            ),
        ),
    }
    for source_path, markers in sources.values():
        source_path.write_text("\n".join(markers), encoding="utf-8")
    monkeypatch.setattr(module, "WEB_AUTH_TOKEN_FLOW", sources)

    assert module.require_web_auth_token_flow() == (
        "token validation, storage, bearer header, rejection clearing, and child render source markers present"
    )
    evidence = module.source_marker_evidence(sources, "auth token-flow")
    assert evidence["surface_count"] == 2
    assert evidence["marker_count"] == 9
    assert [row["label"] for row in evidence["surfaces"]] == ["AuthGate", "api-client"]
    assert evidence["surfaces"][0]["marker_count"] == 6
    assert evidence["surfaces"][0]["markers_present"] is True
    assert "validateUserToken(stored)" in evidence["surfaces"][0]["required_markers"]
    assert evidence["surfaces"][1]["marker_count"] == 3
    assert 'headers.set("Authorization", `Bearer ${token}`)' in evidence["surfaces"][1]["required_markers"]

    sources["api-client"][0].write_text("window.localStorage.getItem(\"dialectical:userToken\")\n", encoding="utf-8")
    with pytest.raises(module.AcceptanceError, match="api-client.*Authorization"):
        module.require_web_auth_token_flow()


def test_require_web_debate_actions_checks_regenerate_and_history_sources(tmp_path: Path, monkeypatch) -> None:
    module = load_acceptance_module()
    sources = {
        "debate-page": (
            tmp_path / "DebatePageClient.tsx",
            (
                "Unlock Actions",
                "Lock Actions",
                "token={actionToken}",
                "onQueued={refresh}",
                "onAuthRejected={rejectActionToken}",
            ),
        ),
        "debate-tree": (
            tmp_path / "DebateTree.tsx",
            (
                "regenerateNode(id, token)",
                "nodeGenerations(node.id, token)",
                "onQueued()",
                "onAuthRejected()",
                "Regenerate",
                "History",
                "Active",
                "Archived",
            ),
        ),
        "api-client": (
            tmp_path / "api.ts",
            (
                "regenerateNode(nodeId: string, token: string",
                "`/api/nodes/${nodeId}/regenerate`",
                "nodeGenerations(nodeId: string, token: string)",
                "`/api/nodes/${nodeId}/generations`",
            ),
        ),
    }
    for source_path, markers in sources.values():
        source_path.write_text("\n".join(markers), encoding="utf-8")
    monkeypatch.setattr(module, "WEB_DEBATE_ACTION_SURFACES", sources)

    assert module.require_web_debate_actions() == (
        "unlock, regenerate, history, archived-generation, API, refresh, and auth-rejection source markers present"
    )
    evidence = module.source_marker_evidence(sources, "debate-action")
    assert evidence["surface_count"] == 3
    assert evidence["marker_count"] == 17
    assert [row["label"] for row in evidence["surfaces"]] == ["debate-page", "debate-tree", "api-client"]
    assert evidence["surfaces"][0]["marker_count"] == 5
    assert evidence["surfaces"][0]["markers_present"] is True
    assert "Unlock Actions" in evidence["surfaces"][0]["required_markers"]
    assert evidence["surfaces"][1]["marker_count"] == 8
    assert "nodeGenerations(node.id, token)" in evidence["surfaces"][1]["required_markers"]
    assert evidence["surfaces"][2]["marker_count"] == 4
    assert "`/api/nodes/${nodeId}/generations`" in evidence["surfaces"][2]["required_markers"]

    sources["debate-tree"][0].write_text("Regenerate\nHistory\n", encoding="utf-8")
    with pytest.raises(module.AcceptanceError, match="debate-tree.*nodeGenerations"):
        module.require_web_debate_actions()


def test_require_web_streaming_client_checks_sse_and_stream_render_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_acceptance_module()
    sources = {
        "debate-page": (
            tmp_path / "DebatePageClient.tsx",
            (
                "new EventSource(`${API_BASE}/api/debates/${id}/events`)",
                'events.addEventListener("node_token"',
                "appendToken(current.tree, nodeId, delta)",
                'events.addEventListener("synthesis_token"',
                "partialJsonField(synthesisDraft?.raw || \"\", \"verdict\")",
                "events.onerror = () =>",
                "scheduleReconnect()",
            ),
        ),
        "debate-tree": (
            tmp_path / "DebateTree.tsx",
            (
                'node.status === "generating" || node.status === "pending" ? "argument cursor" : "argument"',
                "data-model-id={generation?.model_id}",
                "data-worker-name={workerName}",
                '"--model-color"',
            ),
        ),
    }
    for source_path, markers in sources.values():
        source_path.write_text("\n".join(markers), encoding="utf-8")
    monkeypatch.setattr(module, "WEB_STREAMING_CLIENT_SURFACES", sources)

    assert module.require_web_streaming_client() == (
        "SSE subscription, node/synthesis token rendering, reconnect, metadata color, and refresh source markers present"
    )
    evidence = module.source_marker_evidence(sources, "streaming-client")
    assert evidence["surface_count"] == 2
    assert evidence["marker_count"] == 11
    assert [row["label"] for row in evidence["surfaces"]] == ["debate-page", "debate-tree"]
    assert evidence["surfaces"][0]["marker_count"] == 7
    assert evidence["surfaces"][0]["markers_present"] is True
    assert 'events.addEventListener("synthesis_token"' in evidence["surfaces"][0]["required_markers"]
    assert evidence["surfaces"][1]["marker_count"] == 4
    assert "data-worker-name={workerName}" in evidence["surfaces"][1]["required_markers"]

    sources["debate-page"][0].write_text('events.addEventListener("node_token"\n', encoding="utf-8")
    with pytest.raises(module.AcceptanceError, match="debate-page.*synthesis_token"):
        module.require_web_streaming_client()


def test_check_web_debate_detail_requires_worker_model_and_color_markers() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = (
            '<main>Debate topic Export Markdown href="/api/debates/1/export.md" '
            "User token Unlock Actions "
            "Strongest Pro Strongest Con Verdict "
            "mac-mini mock-alpha data-model-id=\"mock-alpha\" "
            "data-worker-name=\"mac-mini\" data-model-color=\"#123456\" "
            "style=\"--model-color:#123456;--node-model-color:#123456\"</main>"
        )
        headers = {"content-type": "text/html; charset=utf-8"}

    class Client:
        def get(self, path, headers):  # noqa: ANN001
            assert path == "/debate/1"
            assert headers["Accept"] == "text/html"
            return Response()

    summary, evidence = module.web_debate_detail_result(
        Client(),
        "/debate/1",
        "Debate topic",
        {"mac-mini"},
        {"mock-alpha"},
    )

    assert summary == "1 workers; 1 models"
    assert evidence["byte_count"] == len(Response.text)
    assert evidence["content_type"] == "text/html; charset=utf-8"
    assert evidence["path"] == "/debate/1"
    assert evidence["debate_id"] == "1"
    assert evidence["topic"] == "Debate topic"
    assert evidence["topic_present"] is True
    assert evidence["export_href"] == "/api/debates/1/export.md"
    assert evidence["same_origin_export_link"] is True
    assert evidence["localhost_export_link"] is False
    assert evidence["auth_gate_controls"] is True
    assert evidence["synthesis_markers"] is True
    assert evidence["model_color_markers"] is True
    assert evidence["worker_names"] == ["mac-mini"]
    assert evidence["model_ids"] == ["mock-alpha"]
    assert module.check_web_debate_detail(
        Client(),
        "/debate/1",
        "Debate topic",
        {"mac-mini"},
        {"mock-alpha"},
    ) == "1 workers; 1 models"


def test_check_web_debate_detail_rejects_missing_worker_marker() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = (
            '<main>Debate topic Export Markdown href="/api/debates/1/export.md" '
            "User token Unlock Actions "
            "Strongest Pro Strongest Con Verdict "
            "mock-alpha data-model-id=\"mock-alpha\" data-model-color=\"#123456\" "
            "style=\"--model-color:#123456;--node-model-color:#123456\"</main>"
        )
        headers = {"content-type": "text/html; charset=utf-8"}

    class Client:
        def get(self, path, headers):  # noqa: ANN001
            return Response()

    with pytest.raises(module.AcceptanceError, match="mac-mini"):
        module.check_web_debate_detail(Client(), "/debate/1", "Debate topic", {"mac-mini"}, {"mock-alpha"})


def test_check_web_debate_detail_rejects_missing_model_color_style() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = (
            '<main>Debate topic Export Markdown href="/api/debates/1/export.md" '
            "User token Unlock Actions "
            "Strongest Pro Strongest Con Verdict "
            "mac-mini mock-alpha data-model-id=\"mock-alpha\" "
            "data-worker-name=\"mac-mini\" data-model-color=\"#123456\"</main>"
        )
        headers = {"content-type": "text/html; charset=utf-8"}

    class Client:
        def get(self, path, headers):  # noqa: ANN001
            return Response()

    with pytest.raises(module.AcceptanceError, match="--model-color"):
        module.check_web_debate_detail(Client(), "/debate/1", "Debate topic", {"mac-mini"}, {"mock-alpha"})


def test_check_web_debate_detail_rejects_localhost_export_link() -> None:
    module = load_acceptance_module()

    class Response:
        status_code = 200
        text = (
            '<main>Debate topic Export Markdown href="/api/debates/1/export.md" '
            'href="http://localhost:8000/api/debates/1/export.md" '
            "User token Unlock Actions "
            "Strongest Pro Strongest Con Verdict mac-mini mock-alpha "
            "data-model-id=\"mock-alpha\" data-worker-name=\"mac-mini\" "
            "data-model-color=\"#123456\" "
            "style=\"--model-color:#123456;--node-model-color:#123456\"</main>"
        )
        headers = {"content-type": "text/html; charset=utf-8"}

    class Client:
        def get(self, path, headers):  # noqa: ANN001
            return Response()

    with pytest.raises(module.AcceptanceError, match="localhost:8000"):
        module.check_web_debate_detail(Client(), "/debate/1", "Debate topic", {"mac-mini"}, {"mock-alpha"})
