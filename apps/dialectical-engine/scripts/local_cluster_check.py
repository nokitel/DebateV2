from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
MOCK_MODELS = "mock-alpha,mock-beta"
MOCK_TOKEN_DELAY_SECONDS = "0.05"
DEFAULT_REPORT_DIR = Path("/private/tmp")
REPORT_NAMES = {
    "two-worker": "dialectical-local-cluster-two-worker.json",
    "failover-one-worker": "dialectical-local-cluster-failover-one-worker.json",
    "rejoin-two-worker": "dialectical-local-cluster-rejoin-two-worker.json",
}
CURRENT_JOB_REPORT_NAME = "dialectical-local-cluster-current-job.json"
INFLIGHT_FAILOVER_REPORT_NAME = "dialectical-local-cluster-inflight-failover.json"
RESTART_PERSISTENCE_REPORT_NAME = "dialectical-local-cluster-restart-persistence.json"
NODE_FAILURE_SSE_REPORT_NAME = "dialectical-local-cluster-node-failure-sse.json"
NODE_FAILURE_SSE_WORKER_NAME = "failure-probe-local"
NODE_FAILURE_SSE_REASON = "local retryable node failure SSE probe"


def runtime_python() -> Path:
    return Path(sys.executable)


def local_routing_config() -> str:
    return textwrap.dedent(
        """
        [roles.decomposer]
        primary = "mock-alpha"
        fallback = ["mock-beta"]

        [roles.proposer]
        pool = ["mock-alpha", "mock-beta"]
        strategy = "round_robin"

        [roles.opponent]
        pool = ["mock-alpha", "mock-beta"]
        strategy = "round_robin"
        constraint = "not_same_as_claim_author"

        [roles.synthesizer]
        primary = "mock-beta"
        fallback = ["mock-alpha"]
        """
    ).strip() + "\n"


def pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(base_url: str, timeout: int = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=2)
            if response.status_code == 200:
                return
        except httpx.RequestError:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Coordinator did not become healthy at {base_url}")


def wait_for_web(web_url: str, timeout: int = 210) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(web_url, headers={"Accept": "text/html"}, timeout=2)
            if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
                return
        except httpx.RequestError:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Web proxy did not become ready at {web_url}")


def wait_for_workers(base_url: str, expected_names: set[str], timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/api/backends/status", timeout=2)
            if response.status_code == 200:
                workers = response.json().get("workers", [])
                online = {worker.get("name") for worker in workers if worker.get("status") == "online"}
                if expected_names <= online:
                    return
        except httpx.RequestError:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Workers did not come online: {sorted(expected_names)}")


class LocalSseRecorder:
    def __init__(self, base_url: str, debate_id: str) -> None:
        self.base_url = base_url
        self.debate_id = debate_id
        self.events: list[str] = []
        self.payloads: dict[str, list[dict[str, object]]] = {}
        self.error: str | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=f"local-sse-{self.debate_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def snapshot(self) -> tuple[list[str], dict[str, list[dict[str, object]]], str | None]:
        with self._lock:
            return (
                list(self.events),
                {event: [dict(payload) for payload in payloads] for event, payloads in self.payloads.items()},
                self.error,
            )

    def wait_for_event(self, event: str, timeout: float = 10) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            events, _, error = self.snapshot()
            if error:
                raise RuntimeError(f"SSE stream failed: {error}")
            if event in events:
                return True
            time.sleep(0.05)
        return False

    def _record(self, event: str, data: str) -> None:
        payload: dict[str, object] = {}
        if data:
            try:
                decoded = json.loads(data)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                payload = decoded
        with self._lock:
            self.events.append(event)
            self.payloads.setdefault(event, []).append(payload)

    def _run(self) -> None:
        current_event = "message"
        current_data: list[str] = []
        try:
            timeout = httpx.Timeout(None, connect=10, read=20)
            with httpx.Client(base_url=self.base_url, timeout=timeout, follow_redirects=True) as client:
                with client.stream(
                    "GET",
                    f"/api/debates/{self.debate_id}/events",
                    headers={"Accept": "text/event-stream"},
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if self._stop.is_set():
                            return
                        if not line:
                            self._record(current_event, "\n".join(current_data))
                            current_event = "message"
                            current_data = []
                        elif line.startswith("event:"):
                            current_event = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            current_data.append(line.split(":", 1)[1].lstrip())
        except Exception as exc:
            if not self._stop.is_set():
                with self._lock:
                    self.error = str(exc)


def require_event_order(events: list[str], first_event: str, second_event: str) -> None:
    try:
        first = events.index(first_event)
        second = events.index(second_event)
    except ValueError as exc:
        raise RuntimeError(f"Missing SSE event while checking order: {first_event}, {second_event}") from exc
    if first >= second:
        raise RuntimeError(f"SSE emitted {second_event} before {first_event}: {events}")


def event_type_counts(events: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event] = counts.get(event, 0) + 1
    return dict(sorted(counts.items()))


def require_current_job_visibility(
    base_url: str,
    user_token: str,
    expected_worker_name: str,
    timeout: int = 20,
) -> dict[str, object]:
    started_at = datetime.now(timezone.utc).isoformat()
    headers = {"Authorization": f"Bearer {user_token}"}
    read_headers = {"CF-Connecting-IP": "198.51.100.240"}
    with httpx.Client(base_url=base_url, timeout=httpx.Timeout(5, connect=2)) as client:
        created = client.post(
            "/api/debates",
            headers=headers,
            json={
                "topic": "Current-job visibility probe",
                "config": {"max_depth": 1, "branching": 2},
            },
        )
        created.raise_for_status()
        debate_id = created.json()["id"]

        deadline = time.monotonic() + timeout
        observed: tuple[str, str, str, dict[str, object]] | None = None
        while time.monotonic() < deadline:
            status = client.get("/api/backends/status", headers=read_headers)
            status.raise_for_status()
            for worker in status.json().get("workers", []):
                if not isinstance(worker, dict):
                    continue
                if worker.get("name") != expected_worker_name:
                    continue
                current_job_id = worker.get("current_job_id")
                if current_job_id:
                    worker_id = worker.get("id")
                    if not isinstance(current_job_id, str) or not current_job_id.strip():
                        raise RuntimeError(f"{expected_worker_name} exposed a non-string current_job_id")
                    if not isinstance(worker_id, str) or not worker_id.strip():
                        raise RuntimeError(f"{expected_worker_name} exposed current_job_id without worker id")
                    observed = (
                        str(worker.get("name") or "unknown"),
                        current_job_id.strip(),
                        worker_id.strip(),
                        dict(worker),
                    )
                    break
            if observed:
                break
            time.sleep(0.1)
        if not observed:
            raise RuntimeError(f"No current_job_id became visible for {expected_worker_name} in /api/backends/status")

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            debate = client.get(f"/api/debates/{debate_id}", headers=read_headers)
            debate.raise_for_status()
            if debate.json().get("status") == "complete":
                return {
                    "status": "passed",
                    "started_at": started_at,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "base_url": base_url,
                    "debate_id": debate_id,
                    "worker_name": observed[0],
                    "current_job_id": observed[1],
                    "worker_id": observed[2],
                    "worker_row": observed[3],
                    "detail": (
                        f"{observed[0]} ({observed[2]}) exposed current_job_id {observed[1]} "
                        f"during debate {debate_id}"
                    ),
                }
            time.sleep(0.5)
        raise RuntimeError(f"Current-job probe debate did not complete: {debate_id}")


def require_node_failure_sse(
    base_url: str,
    user_token: str,
    timeout: int = 20,
) -> dict[str, object]:
    started_at = datetime.now(timezone.utc).isoformat()
    user_headers = {"Authorization": f"Bearer {user_token}"}
    with httpx.Client(base_url=base_url, timeout=httpx.Timeout(10, connect=2)) as client:
        registered = client.post(
            "/api/workers/register",
            headers=user_headers,
            json={"name": NODE_FAILURE_SSE_WORKER_NAME, "capabilities": ["mock-alpha"]},
        )
        registered.raise_for_status()
        worker = registered.json()
        worker_id = str(worker.get("worker_id") or "")
        worker_token = str(worker.get("worker_token") or "")
        if not worker_id or not worker_token:
            raise RuntimeError("Failure SSE probe worker registration did not return worker credentials")
        worker_headers = {"Authorization": f"Bearer {worker_token}", "X-Worker-ID": worker_id}

        created = client.post(
            "/api/debates",
            headers=user_headers,
            json={
                "topic": "Retryable node failure SSE probe",
                "config": {
                    "max_depth": 1,
                    "branching": 2,
                    "role_overrides": {
                        "decomposer": {
                            "primary": "mock-alpha",
                            "fallback": [],
                        }
                    },
                },
            },
        )
        created.raise_for_status()
        created_payload = created.json()
        debate_id = str(created_payload.get("id") or "")
        root_node_id = str(created_payload.get("root_node_id") or "")
        if not debate_id or not root_node_id:
            raise RuntimeError("Failure SSE probe debate did not return debate/root ids")

        recorder = LocalSseRecorder(base_url, debate_id)
        recorder.start()
        try:
            if not recorder.wait_for_event("connected", timeout=timeout):
                raise RuntimeError("Failure SSE probe did not receive connected event")
            polled = client.post(f"/api/workers/{worker_id}/poll", headers=worker_headers)
            polled.raise_for_status()
            job = polled.json().get("job")
            if not isinstance(job, dict):
                raise RuntimeError("Failure SSE probe worker did not receive a job")
            job_id = str(job.get("id") or "")
            node_id = str(job.get("node_id") or "")
            if not job_id or not node_id:
                raise RuntimeError(f"Failure SSE probe job missing ids: {job}")
            if job.get("required_model") != "mock-alpha":
                raise RuntimeError(f"Failure SSE probe job used unexpected model: {job.get('required_model')}")
            if not recorder.wait_for_event("node_started", timeout=timeout):
                raise RuntimeError("Failure SSE probe did not receive node_started event")

            failed = client.post(
                f"/api/jobs/{job_id}/fail",
                headers=worker_headers,
                json={"reason": NODE_FAILURE_SSE_REASON, "retryable": True},
            )
            failed.raise_for_status()
            fail_payload = failed.json()
            if fail_payload.get("status") != "queued":
                raise RuntimeError(f"Failure SSE probe fail endpoint did not requeue job: {fail_payload}")
            if not recorder.wait_for_event("node_failed", timeout=timeout):
                raise RuntimeError("Failure SSE probe did not receive node_failed event")
        finally:
            recorder.stop()

        events, payloads, error = recorder.snapshot()
        if error:
            raise RuntimeError(f"Failure SSE probe stream failed: {error}")
        require_event_order(events, "connected", "node_started")
        require_event_order(events, "node_started", "node_failed")
        node_started_payloads = payloads.get("node_started", [])
        node_failed_payloads = payloads.get("node_failed", [])
        if not node_started_payloads:
            raise RuntimeError("Failure SSE probe did not capture node_started payloads")
        if not node_failed_payloads:
            raise RuntimeError("Failure SSE probe did not capture node_failed payloads")
        first_started = node_started_payloads[0]
        first_failed = node_failed_payloads[0]
        if first_started.get("node_id") != node_id or first_started.get("worker_id") != worker_id:
            raise RuntimeError(f"Failure SSE probe node_started payload mismatch: {first_started}")
        if first_started.get("model_id") != "mock-alpha":
            raise RuntimeError(f"Failure SSE probe node_started model mismatch: {first_started}")
        if first_failed.get("node_id") != node_id or first_failed.get("reason") != NODE_FAILURE_SSE_REASON:
            raise RuntimeError(f"Failure SSE probe node_failed payload mismatch: {first_failed}")
        retry_in_s = first_failed.get("retry_in_s")
        if not isinstance(retry_in_s, int) or retry_in_s <= 0:
            raise RuntimeError(f"Failure SSE probe node_failed retry_in_s invalid: {first_failed}")

        degraded_status = client.get("/api/backends/status")
        degraded_status.raise_for_status()
        degraded_worker_row = next(
            (
                row
                for row in degraded_status.json().get("workers", [])
                if isinstance(row, dict) and row.get("name") == NODE_FAILURE_SSE_WORKER_NAME
            ),
            None,
        )
        if not isinstance(degraded_worker_row, dict):
            raise RuntimeError("Failure SSE probe worker row missing after retryable failure")
        failure_status = degraded_worker_row.get("status")
        if failure_status not in {"degraded", "offline"} or degraded_worker_row.get("current_job_id"):
            raise RuntimeError(f"Failure SSE probe worker was not degraded/offline and idle: {degraded_worker_row}")

        heartbeat = client.post(
            f"/api/workers/{worker_id}/heartbeat",
            headers=worker_headers,
            json={"capabilities": ["mock-alpha"], "status": "offline"},
        )
        heartbeat.raise_for_status()
        status = client.get("/api/backends/status")
        status.raise_for_status()
        worker_row = next(
            (
                row
                for row in status.json().get("workers", [])
                if isinstance(row, dict) and row.get("name") == NODE_FAILURE_SSE_WORKER_NAME
            ),
            None,
        )
        if not isinstance(worker_row, dict):
            raise RuntimeError("Failure SSE probe worker row missing after offline heartbeat")
        if worker_row.get("status") != "offline" or worker_row.get("current_job_id"):
            raise RuntimeError(f"Failure SSE probe worker was not offline and idle: {worker_row}")
        debate = client.get(f"/api/debates/{debate_id}")
        debate.raise_for_status()
        root = debate.json().get("tree")
        if not isinstance(root, dict) or root.get("id") != root_node_id or root.get("status") != "pending":
            raise RuntimeError(f"Failure SSE probe root was not requeued as pending: {root}")

    counts = event_type_counts(events)
    return {
        "status": "passed",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "debate_id": debate_id,
        "root_node_id": root_node_id,
        "job_id": job_id,
        "node_id": node_id,
        "worker_name": NODE_FAILURE_SSE_WORKER_NAME,
        "worker_id": worker_id,
        "model_id": "mock-alpha",
        "retryable": True,
        "failure_reason": NODE_FAILURE_SSE_REASON,
        "fail_response_status": fail_payload.get("status"),
        "worker_degraded": True,
        "worker_degraded_current_job_cleared": True,
        "worker_failure_status": failure_status,
        "degraded_worker_row": dict(degraded_worker_row),
        "worker_offline": True,
        "worker_current_job_cleared": True,
        "offline_worker_row": dict(worker_row),
        "root_requeued": True,
        "root_node_row": dict(root),
        "event_count": len(events),
        "event_sequence": events,
        "event_type_counts": counts,
        "node_started_count": len(node_started_payloads),
        "node_failed_count": len(node_failed_payloads),
        "node_started_payloads": node_started_payloads,
        "node_failed_payloads": node_failed_payloads,
        "detail": f"{NODE_FAILURE_SSE_WORKER_NAME} failed {job_id}; node_failed SSE for {node_id}",
    }


def write_current_job_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def stable_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(item.strip() for item in value if isinstance(item, str) and item.strip())


def debate_id_from_acceptance_report(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = payload.get("results")
    if not isinstance(results, list):
        raise RuntimeError(f"Acceptance report has no results list: {path}")
    for result in results:
        if isinstance(result, dict) and result.get("name") == "create-debate":
            debate_id = result.get("detail")
            if isinstance(debate_id, str) and debate_id:
                return debate_id
    raise RuntimeError(f"Acceptance report has no create-debate result: {path}")


def fetch_debate_detail(base_url: str, debate_id: str) -> dict[str, object]:
    response = httpx.get(f"{base_url}/api/debates/{debate_id}", timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Debate detail is not an object: {debate_id}")
    return payload


def require_restart_persistence(
    base_url: str,
    debate_id: str,
    coordinator: subprocess.Popen,
    python: Path,
    port: int,
    coordinator_env: dict[str, str],
    processes: list[tuple[str, subprocess.Popen]],
) -> dict[str, object]:
    started_at = datetime.now(timezone.utc).isoformat()
    before = fetch_debate_detail(base_url, debate_id)
    stop_process("coordinator", coordinator)
    restarted = start_process(
        "coordinator",
        [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        ROOT / "coordinator",
        coordinator_env,
    )
    processes.append(("coordinator", restarted))
    wait_for_health(base_url)
    after = fetch_debate_detail(base_url, debate_id)
    before_stable = stable_json(before)
    after_stable = stable_json(after)
    if before_stable != after_stable:
        raise RuntimeError(f"Debate detail changed after coordinator restart: {debate_id}")
    return {
        "status": "passed",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "debate_id": debate_id,
        "topic": before.get("topic"),
        "debate_status": before.get("status"),
        "root_node_id": before.get("root_node_id"),
        "synthesis_id": before.get("synthesis_id"),
        "node_count": before.get("node_count"),
        "worker_names": string_list(before.get("workers")),
        "model_ids": string_list(before.get("models")),
        "exact_payload_match": True,
        "before_stable_json_length": len(before_stable),
        "after_stable_json_length": len(after_stable),
        "before_stable_json_sha256": hashlib.sha256(before_stable.encode("utf-8")).hexdigest(),
        "after_stable_json_sha256": hashlib.sha256(after_stable.encode("utf-8")).hexdigest(),
        "detail": f"restarted coordinator and revisited {debate_id}; exact detail match",
    }


def start_process(name: str, args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env={**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(f"started {name}: pid={process.pid}")
    return process


def start_mock_worker(
    name: str,
    python: Path,
    base_url: str,
    tmp: Path,
    user_token: str,
    token_delay_seconds: str = MOCK_TOKEN_DELAY_SECONDS,
) -> subprocess.Popen:
    return start_process(
        name,
        [str(python), "-m", "app.main"],
        ROOT / "worker",
        {
            "DIALECTICAL_WORKER_CONFIG": str(tmp / f"{name}.toml"),
            "DIALECTICAL_COORDINATOR_URL": base_url,
            "DIALECTICAL_USER_TOKEN": user_token,
            "DIALECTICAL_WORKER_NAME": name,
            "DIALECTICAL_ENABLE_REAL_ADAPTERS": "0",
            "DIALECTICAL_ENABLE_MOCK": "1",
            "DIALECTICAL_MOCK_MODELS": MOCK_MODELS,
            "DIALECTICAL_MOCK_TOKEN_DELAY_SECONDS": token_delay_seconds,
        },
    )


def web_proxy_args(python: Path, coordinator_port: int, web_port: int, next_port: int) -> list[str]:
    return [
        str(python),
        str(ROOT / "scripts" / "web_proxy.py"),
        "--root",
        str(ROOT),
        "--coordinator-host",
        "127.0.0.1",
        "--coordinator-port",
        str(coordinator_port),
        "--public-host",
        "127.0.0.1",
        "--public-port",
        str(web_port),
        "--next-host",
        "127.0.0.1",
        "--next-port",
        str(next_port),
        "--next-mode",
        "start",
    ]


def stop_process(name: str, process: subprocess.Popen, timeout: int = 8) -> None:
    if process.poll() is not None:
        return
    print(f"stopping {name}: pid={process.pid}")
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def drain_process(name: str, process: subprocess.Popen, lines: int = 80) -> None:
    if process.stdout is None:
        return
    output = process.stdout.read()
    if not output:
        return
    tail = "\n".join(output.splitlines()[-lines:])
    print(f"\n--- {name} output tail ---\n{tail}\n--- end {name} output tail ---")


def running_process(processes: list[tuple[str, subprocess.Popen]], name: str) -> subprocess.Popen:
    for process_name, process in reversed(processes):
        if process_name == name and process.poll() is None:
            return process
    raise RuntimeError(f"{name} is not running")


def stop_if_running(processes: list[tuple[str, subprocess.Popen]], name: str) -> None:
    try:
        process = running_process(processes, name)
    except RuntimeError:
        return
    stop_process(name, process)


def worker_status_rows(client: httpx.Client) -> list[dict[str, object]]:
    status = client.get("/api/backends/status")
    status.raise_for_status()
    rows = status.json().get("workers", [])
    return [row for row in rows if isinstance(row, dict)]


def generated_workers_from_debate(debate: dict[str, object]) -> set[str]:
    workers: set[str] = set()

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        generation = node.get("active_generation")
        if isinstance(generation, dict):
            worker_name = generation.get("worker_name") or generation.get("worker_id")
            if isinstance(worker_name, str) and worker_name:
                workers.add(worker_name)
        children = node.get("children", [])
        if isinstance(children, list):
            for child in children:
                walk(child)

    walk(debate.get("tree"))
    synthesis = debate.get("synthesis")
    if isinstance(synthesis, dict):
        worker_id = synthesis.get("worker_id")
        if isinstance(worker_id, str) and worker_id:
            workers.add(worker_id)
    return workers


def require_inflight_failover(
    base_url: str,
    user_token: str,
    python: Path,
    tmp: Path,
    processes: list[tuple[str, subprocess.Popen]],
    timeout: int = 120,
) -> dict[str, object]:
    started_at = datetime.now(timezone.utc).isoformat()
    headers = {"Authorization": f"Bearer {user_token}"}
    with httpx.Client(base_url=base_url, timeout=httpx.Timeout(5, connect=2)) as client:
        created = client.post(
            "/api/debates",
            headers=headers,
            json={
                "topic": "In-flight Worker B failover probe",
                "config": {"max_depth": 1, "branching": 2},
            },
        )
        created.raise_for_status()
        debate_id = created.json()["id"]

        deadline = time.monotonic() + 30
        abandoned_job_id: str | None = None
        failed_worker_row: dict[str, object] | None = None
        while time.monotonic() < deadline:
            for worker in worker_status_rows(client):
                if worker.get("name") == "adesso-mbp-local" and worker.get("current_job_id"):
                    abandoned_job_id = str(worker["current_job_id"])
                    failed_worker_row = dict(worker)
                    break
            if abandoned_job_id:
                break
            time.sleep(0.1)
        if not abandoned_job_id:
            raise RuntimeError("Worker B did not expose an in-flight job before failover")

        mac_mini = start_mock_worker("mac-mini-local", python, base_url, tmp, user_token)
        processes.append(("mac-mini-local", mac_mini))
        wait_for_workers(base_url, {"mac-mini-local", "adesso-mbp-local"})

        adesso = running_process(processes, "adesso-mbp-local")
        stop_process("adesso-mbp-local", adesso)

        deadline = time.monotonic() + 30
        offline_worker_row: dict[str, object] | None = None
        while time.monotonic() < deadline:
            rows = worker_status_rows(client)
            adesso_row = next((row for row in rows if row.get("name") == "adesso-mbp-local"), None)
            if adesso_row and adesso_row.get("status") == "offline" and not adesso_row.get("current_job_id"):
                offline_worker_row = dict(adesso_row)
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Worker B did not transition offline with current_job_id cleared")

        deadline = time.monotonic() + timeout
        final: dict[str, object] | None = None
        while time.monotonic() < deadline:
            debate = client.get(f"/api/debates/{debate_id}")
            debate.raise_for_status()
            payload = debate.json()
            if payload.get("status") == "complete":
                final = payload
                break
            time.sleep(0.5)
        if final is None:
            raise RuntimeError(f"In-flight failover probe debate did not complete: {debate_id}")

    takeover_workers = sorted(worker for worker in generated_workers_from_debate(final) if worker == "mac-mini-local")
    if "mac-mini-local" not in takeover_workers:
        raise RuntimeError(f"Worker A did not generate the failed-over debate: {debate_id}")
    final_worker_names = sorted(
        value.strip()
        for value in final.get("workers", [])
        if isinstance(value, str) and value.strip()
    )
    final_model_ids = sorted(
        value.strip()
        for value in final.get("models", [])
        if isinstance(value, str) and value.strip()
    )

    return {
        "status": "passed",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "debate_id": debate_id,
        "final_debate_id": str(final.get("id") or ""),
        "final_status": str(final.get("status") or ""),
        "final_node_count": final.get("node_count"),
        "final_worker_names": final_worker_names,
        "final_model_ids": final_model_ids,
        "failed_worker_name": "adesso-mbp-local",
        "takeover_worker_names": takeover_workers,
        "abandoned_job_id": abandoned_job_id,
        "failed_worker_row": failed_worker_row or {},
        "offline_worker_row": offline_worker_row or {},
        "detail": f"stopped adesso-mbp-local during {abandoned_job_id}; mac-mini-local completed {debate_id}",
    }


def run_acceptance(
    base_url: str,
    web_url: str | None,
    user_token: str,
    phase: str,
    workers: int,
    names: str,
    offline_names: str,
    require_tree: bool,
    report_path: Path | None,
    skip_web_checks: bool,
) -> None:
    command = [
        str(runtime_python()),
        str(ROOT / "scripts" / "acceptance_check.py"),
        "--base-url",
        base_url,
        "--phase",
        phase,
        "--expected-workers",
        str(workers),
        "--expected-worker-names",
        names,
        "--expected-offline-worker-names",
        offline_names,
        "--completion-timeout",
        "60",
        "--regeneration-timeout",
        "60",
        "--skeleton-timeout",
        "20",
    ]
    if web_url is not None:
        command.extend(["--web-base-url", web_url])
    if skip_web_checks:
        command.append("--skip-web-checks")
    if require_tree:
        command.append("--require-expected-workers-in-tree")
    command.append("--require-different-regen-model")
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if report_path.exists():
            report_path.unlink()
        command.extend(["--report-path", str(report_path)])
    subprocess.run(command, cwd=ROOT, env={**os.environ, "USER_TOKEN": user_token}, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local two-worker/failover/rejoin acceptance check")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--web-port", type=int, default=0)
    parser.add_argument("--next-port", type=int, default=0)
    parser.add_argument("--skip-web-checks", action="store_true")
    parser.add_argument("--user-token", default="user_local_cluster_token")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="directory for durable per-phase JSON acceptance reports",
    )
    args = parser.parse_args()

    python = runtime_python()
    port = args.port or pick_port()
    web_port = args.web_port or pick_port()
    next_port = args.next_port or pick_port()
    base_url = f"http://127.0.0.1:{port}"
    web_url = None if args.skip_web_checks else f"http://127.0.0.1:{web_port}"
    tmp = Path(tempfile.mkdtemp(prefix="dialectical-local-cluster-"))
    report_paths = {phase: args.report_dir / filename for phase, filename in REPORT_NAMES.items()}
    current_job_report_path = args.report_dir / CURRENT_JOB_REPORT_NAME
    inflight_failover_report_path = args.report_dir / INFLIGHT_FAILOVER_REPORT_NAME
    restart_persistence_report_path = args.report_dir / RESTART_PERSISTENCE_REPORT_NAME
    node_failure_sse_report_path = args.report_dir / NODE_FAILURE_SSE_REPORT_NAME
    config_path = tmp / "coordinator.toml"
    config_path.write_text(local_routing_config())
    processes: list[tuple[str, subprocess.Popen]] = []

    coordinator_env = {
        "DIALECTICAL_HOME": str(tmp / "home"),
        "DIALECTICAL_COORDINATOR_CONFIG": str(config_path),
        "DIALECTICAL_DATABASE_URL": f"sqlite:///{tmp / 'db.sqlite3'}",
        "DIALECTICAL_USER_TOKEN": args.user_token,
        "DIALECTICAL_WORKER_POLL_SECONDS": "2",
        "DIALECTICAL_WORKER_OFFLINE_SECONDS": "4",
        "DIALECTICAL_JOB_FALLBACK_SECONDS": "4",
    }
    try:
        coordinator = start_process(
            "coordinator",
            [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            ROOT / "coordinator",
            coordinator_env,
        )
        processes.append(("coordinator", coordinator))
        wait_for_health(base_url)

        if web_url is not None:
            web = start_process(
                "web",
                web_proxy_args(python, port, web_port, next_port),
                ROOT,
                {},
            )
            processes.append(("web", web))
            wait_for_web(web_url)

        adesso = start_mock_worker(
            "adesso-mbp-local",
            python,
            base_url,
            tmp,
            args.user_token,
            token_delay_seconds="0.75",
        )
        processes.append(("adesso-mbp-local", adesso))
        wait_for_workers(base_url, {"adesso-mbp-local"})

        inflight_failover_report = require_inflight_failover(base_url, args.user_token, python, tmp, processes)
        write_current_job_report(inflight_failover_report_path, inflight_failover_report)
        print(f"PASS in-flight-failover: {inflight_failover_report['detail']}")

        restarted_adesso = start_mock_worker("adesso-mbp-local", python, base_url, tmp, args.user_token)
        processes.append(("adesso-mbp-local", restarted_adesso))

        wait_for_workers(base_url, {"mac-mini-local", "adesso-mbp-local"})
        mac_mini = running_process(processes, "mac-mini-local")
        stop_process("mac-mini-local", mac_mini)
        current_job_report = require_current_job_visibility(base_url, args.user_token, "adesso-mbp-local")
        write_current_job_report(current_job_report_path, current_job_report)
        print(f"PASS current-job-visibility: {current_job_report['detail']}")
        mac_mini = start_mock_worker("mac-mini-local", python, base_url, tmp, args.user_token)
        processes.append(("mac-mini-local", mac_mini))
        wait_for_workers(base_url, {"mac-mini-local", "adesso-mbp-local"})
        run_acceptance(
            base_url,
            web_url,
            args.user_token,
            "two-worker",
            workers=2,
            names="mac-mini-local,adesso-mbp-local",
            offline_names="",
            require_tree=True,
            report_path=report_paths["two-worker"],
            skip_web_checks=args.skip_web_checks,
        )

        adesso = running_process(processes, "adesso-mbp-local")
        stop_process("adesso-mbp-local", adesso)
        time.sleep(5)
        run_acceptance(
            base_url,
            web_url,
            args.user_token,
            "failover-one-worker",
            workers=1,
            names="mac-mini-local",
            offline_names="adesso-mbp-local",
            require_tree=False,
            report_path=report_paths["failover-one-worker"],
            skip_web_checks=args.skip_web_checks,
        )

        restarted_adesso = start_mock_worker("adesso-mbp-local", python, base_url, tmp, args.user_token)
        processes.append(("adesso-mbp-local", restarted_adesso))
        wait_for_workers(base_url, {"mac-mini-local", "adesso-mbp-local"})
        run_acceptance(
            base_url,
            web_url,
            args.user_token,
            "rejoin-two-worker",
            workers=2,
            names="mac-mini-local,adesso-mbp-local",
            offline_names="",
            require_tree=True,
            report_path=report_paths["rejoin-two-worker"],
            skip_web_checks=args.skip_web_checks,
        )
        persistence_debate_id = debate_id_from_acceptance_report(report_paths["rejoin-two-worker"])
        coordinator = running_process(processes, "coordinator")
        restart_persistence_report = require_restart_persistence(
            base_url,
            persistence_debate_id,
            coordinator,
            python,
            port,
            coordinator_env,
            processes,
        )
        write_current_job_report(restart_persistence_report_path, restart_persistence_report)
        print(f"PASS restart-persistence: {restart_persistence_report['detail']}")
        stop_if_running(processes, "mac-mini-local")
        stop_if_running(processes, "adesso-mbp-local")
        node_failure_sse_report = require_node_failure_sse(base_url, args.user_token)
        write_current_job_report(node_failure_sse_report_path, node_failure_sse_report)
        print(f"PASS node-failure-sse: {node_failure_sse_report['detail']}")
        print("local cluster acceptance passed")
        print(f"wrote local cluster in-flight failover report: {inflight_failover_report_path}")
        print(f"wrote local cluster current-job report: {current_job_report_path}")
        print(f"wrote local cluster restart-persistence report: {restart_persistence_report_path}")
        print(f"wrote local cluster node-failure-sse report: {node_failure_sse_report_path}")
        for phase, path in report_paths.items():
            print(f"wrote local cluster {phase} report: {path}")
        return 0
    finally:
        for name, process in reversed(processes):
            stop_process(name, process)
        for name, process in processes:
            if process.returncode not in (0, -signal.SIGTERM):
                drain_process(name, process)


if __name__ == "__main__":
    raise SystemExit(main())
