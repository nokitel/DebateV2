from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_local_cluster_module():
    spec = importlib.util.spec_from_file_location("dialectical_local_cluster_check", ROOT / "scripts" / "local_cluster_check.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_acceptance_includes_web_base_url_by_default(monkeypatch, tmp_path: Path) -> None:
    module = load_local_cluster_module()
    captured: dict[str, object] = {}

    def fake_run(command, cwd, env, check):  # noqa: ANN001
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        captured["check"] = check

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.run_acceptance(
        "http://127.0.0.1:8100",
        "http://127.0.0.1:3100",
        "user-token",
        "two-worker",
        workers=2,
        names="mac-mini-local,adesso-mbp-local",
        offline_names="",
        require_tree=True,
        report_path=tmp_path / "report.json",
        skip_web_checks=False,
    )

    command = captured["command"]
    assert "--web-base-url" in command
    assert "http://127.0.0.1:3100" in command
    assert command[command.index("--phase") + 1] == "two-worker"
    assert "--skip-web-checks" not in command
    assert "--expected-offline-worker-names" in command
    assert "--require-expected-workers-in-tree" in command
    assert "--require-different-regen-model" in command
    assert captured["env"]["USER_TOKEN"] == "user-token"


def test_run_acceptance_can_skip_web_checks(monkeypatch, tmp_path: Path) -> None:
    module = load_local_cluster_module()
    captured: dict[str, object] = {}

    def fake_run(command, cwd, env, check):  # noqa: ANN001
        captured["command"] = command

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.run_acceptance(
        "http://127.0.0.1:8100",
        None,
        "user-token",
        "failover-one-worker",
        workers=1,
        names="mac-mini-local",
        offline_names="adesso-mbp-local",
        require_tree=False,
        report_path=tmp_path / "report.json",
        skip_web_checks=True,
    )

    command = captured["command"]
    assert "--web-base-url" not in command
    assert "--skip-web-checks" in command
    assert command[command.index("--phase") + 1] == "failover-one-worker"
    assert command[command.index("--expected-offline-worker-names") + 1] == "adesso-mbp-local"
    assert "--require-expected-workers-in-tree" not in command


def test_web_proxy_args_use_next_start_for_production_style_local_checks() -> None:
    module = load_local_cluster_module()

    command = module.web_proxy_args(Path("/python"), 8100, 3100, 3101)

    assert command[0] == "/python"
    assert "--coordinator-port" in command
    assert command[command.index("--coordinator-port") + 1] == "8100"
    assert "--public-port" in command
    assert command[command.index("--public-port") + 1] == "3100"
    assert "--next-port" in command
    assert command[command.index("--next-port") + 1] == "3101"
    assert "--next-mode" in command
    assert command[command.index("--next-mode") + 1] == "start"


def test_local_cluster_uses_current_python_interpreter() -> None:
    module = load_local_cluster_module()

    assert module.runtime_python() == Path(sys.executable)


def test_require_current_job_visibility_filters_for_expected_worker(monkeypatch) -> None:
    module = load_local_cluster_module()

    class Response:
        def __init__(self, payload):  # noqa: ANN001
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):  # noqa: ANN001
            return self.payload

    class Client:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self.args = args
            self.kwargs = kwargs
            self.status_calls = 0

        def __enter__(self):  # noqa: ANN001
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

        def post(self, path, headers=None, json=None):  # noqa: ANN001
            assert path == "/api/debates"
            return Response({"id": "debate-1"})

        def get(self, path, headers=None):  # noqa: ANN001
            if path == "/api/backends/status":
                return Response(
                    {
                        "workers": [
                            {
                                "id": "11111111-1111-4111-8111-111111111111",
                                "name": "mac-mini-local",
                                "status": "online",
                                "capabilities": ["mock-alpha", "mock-beta"],
                                "current_job_id": "33333333-3333-4333-8333-333333333333",
                                "last_seen": "2026-05-24T00:00:00+00:00",
                            },
                            {
                                "id": "22222222-2222-4222-8222-222222222222",
                                "name": "adesso-mbp-local",
                                "status": "online",
                                "capabilities": ["mock-alpha", "mock-beta"],
                                "current_job_id": "44444444-4444-4444-8444-444444444444",
                                "last_seen": "2026-05-24T00:00:00+00:00",
                            },
                        ]
                    }
                )
            assert path == "/api/debates/debate-1"
            return Response({"status": "complete"})

    monkeypatch.setattr(module.httpx, "Client", Client)

    report = module.require_current_job_visibility("http://127.0.0.1:8000", "user-token", "adesso-mbp-local")

    assert report["worker_name"] == "adesso-mbp-local"
    assert report["current_job_id"] == "44444444-4444-4444-8444-444444444444"
    assert report["worker_row"]["name"] == "adesso-mbp-local"
    assert report["worker_row"]["current_job_id"] == "44444444-4444-4444-8444-444444444444"


def test_require_node_failure_sse_records_retryable_failure(monkeypatch) -> None:
    module = load_local_cluster_module()

    class Response:
        def __init__(self, payload):  # noqa: ANN001
            self.payload = payload
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):  # noqa: ANN001
            return self.payload

    class Recorder:
        def __init__(self, base_url, debate_id):  # noqa: ANN001
            self.base_url = base_url
            self.debate_id = debate_id
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

        def wait_for_event(self, event, timeout=10):  # noqa: ANN001
            del timeout
            return event in {"connected", "node_started", "node_failed"}

        def snapshot(self):  # noqa: ANN001
            return (
                ["connected", "node_started", "node_failed"],
                {
                    "connected": [{}],
                    "node_started": [
                        {
                            "node_id": "11111111-1111-4111-8111-111111111111",
                            "model_id": "mock-alpha",
                            "worker_id": "22222222-2222-4222-8222-222222222222",
                            "role": "decomposer",
                        }
                    ],
                    "node_failed": [
                        {
                            "node_id": "11111111-1111-4111-8111-111111111111",
                            "reason": module.NODE_FAILURE_SSE_REASON,
                            "retry_in_s": 5,
                        }
                    ],
                },
                None,
            )

    class Client:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self.args = args
            self.kwargs = kwargs
            self.status_calls = 0

        def __enter__(self):  # noqa: ANN001
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

        def post(self, path, headers=None, json=None):  # noqa: ANN001
            del headers
            if path == "/api/workers/register":
                assert json == {"name": module.NODE_FAILURE_SSE_WORKER_NAME, "capabilities": ["mock-alpha"]}
                return Response(
                    {
                        "worker_id": "22222222-2222-4222-8222-222222222222",
                        "worker_token": "worker-token",
                    }
                )
            if path == "/api/debates":
                return Response(
                    {
                        "id": "33333333-3333-4333-8333-333333333333",
                        "root_node_id": "11111111-1111-4111-8111-111111111111",
                    }
                )
            if path == "/api/workers/22222222-2222-4222-8222-222222222222/poll":
                return Response(
                    {
                        "job": {
                            "id": "44444444-4444-4444-8444-444444444444",
                            "node_id": "11111111-1111-4111-8111-111111111111",
                            "required_model": "mock-alpha",
                        }
                    }
                )
            if path == "/api/jobs/44444444-4444-4444-8444-444444444444/fail":
                assert json == {"reason": module.NODE_FAILURE_SSE_REASON, "retryable": True}
                return Response({"status": "queued"})
            if path == "/api/workers/22222222-2222-4222-8222-222222222222/heartbeat":
                assert json == {"capabilities": ["mock-alpha"], "status": "offline"}
                return Response({"status": "offline"})
            raise AssertionError(f"unexpected POST {path}")

        def get(self, path):  # noqa: ANN001
            if path == "/api/backends/status":
                self.status_calls += 1
                status = "degraded" if self.status_calls == 1 else "offline"
                return Response(
                    {
                        "workers": [
                            {
                                "id": "22222222-2222-4222-8222-222222222222",
                                "name": module.NODE_FAILURE_SSE_WORKER_NAME,
                                "status": status,
                                "capabilities": ["mock-alpha"],
                                "current_job_id": None,
                                "last_seen": "2026-05-24T00:00:00+00:00",
                            }
                        ]
                    }
                )
            if path == "/api/debates/33333333-3333-4333-8333-333333333333":
                return Response(
                    {
                        "tree": {
                            "id": "11111111-1111-4111-8111-111111111111",
                            "claim": "Retryable node failure SSE probe",
                            "status": "pending",
                            "children": [],
                        }
                    }
                )
            raise AssertionError(f"unexpected GET {path}")

    monkeypatch.setattr(module, "LocalSseRecorder", Recorder)
    monkeypatch.setattr(module.httpx, "Client", Client)

    report = module.require_node_failure_sse("http://127.0.0.1:8000", "user-token")

    assert report["status"] == "passed"
    assert report["worker_name"] == module.NODE_FAILURE_SSE_WORKER_NAME
    assert report["fail_response_status"] == "queued"
    assert report["node_failed_count"] == 1
    assert report["event_type_counts"]["node_failed"] == 1
    assert report["worker_degraded"] is True
    assert report["worker_degraded_current_job_cleared"] is True
    assert report["worker_failure_status"] == "degraded"
    assert report["degraded_worker_row"]["status"] == "degraded"
    assert report["degraded_worker_row"]["current_job_id"] is None
    assert report["offline_worker_row"]["status"] == "offline"
    assert report["offline_worker_row"]["current_job_id"] is None
    assert report["root_requeued"] is True
    assert report["root_node_row"]["id"] == "11111111-1111-4111-8111-111111111111"
    assert report["root_node_row"]["status"] == "pending"


def test_debate_id_from_acceptance_report_reads_create_debate_result(tmp_path: Path) -> None:
    module = load_local_cluster_module()
    report = tmp_path / "acceptance.json"
    report.write_text(
        '{"results":[{"name":"public-list","detail":"ok"},{"name":"create-debate","detail":"debate-1"}]}',
        encoding="utf-8",
    )

    assert module.debate_id_from_acceptance_report(report) == "debate-1"


def test_debate_id_from_acceptance_report_rejects_missing_create_debate(tmp_path: Path) -> None:
    module = load_local_cluster_module()
    report = tmp_path / "acceptance.json"
    report.write_text('{"results":[{"name":"public-list","detail":"ok"}]}', encoding="utf-8")

    try:
        module.debate_id_from_acceptance_report(report)
    except RuntimeError as exc:
        assert "create-debate" in str(exc)
    else:
        raise AssertionError("missing create-debate result was accepted")
