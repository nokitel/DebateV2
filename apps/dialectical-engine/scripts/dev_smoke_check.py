#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = Path("/private/tmp/dialectical-dev-smoke.json")
LOG_PATH = Path("/private/tmp/dialectical-dev-smoke.log")
DEFAULT_USER_TOKEN = "user_dev_token"
DEFAULT_TIMEOUT_SECONDS = 360


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch_text(url: str, *, accept: str = "text/plain", timeout: float = 3) -> str:
    request = urllib.request.Request(url, headers={"Accept": accept})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict[str, Any]:
    payload = json.loads(fetch_text(url, accept="application/json"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} returned non-object JSON")
    return payload


def wait_for(name: str, deadline: float, check: Callable[[], Any]) -> Any:
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            return check()
        except (OSError, RuntimeError, json.JSONDecodeError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"{name} did not become ready before timeout: {last_error or 'no detail'}")


def log_tail(path: Path, lines: int = 80) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def stop_process_group(process: subprocess.Popen[object]) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def require_worker(payload: dict[str, Any], expected_name: str) -> dict[str, Any]:
    workers = payload.get("workers")
    if not isinstance(workers, list):
        raise RuntimeError("worker status payload missing workers")
    for worker in workers:
        if not isinstance(worker, dict) or worker.get("name") != expected_name:
            continue
        capabilities = worker.get("capabilities")
        if worker.get("status") != "online":
            raise RuntimeError(f"{expected_name} is {worker.get('status')!r}, not online")
        if not isinstance(capabilities, list) or "mock-local" not in capabilities:
            raise RuntimeError(f"{expected_name} is missing mock-local capability")
        return worker
    raise RuntimeError(f"{expected_name} is not registered")


def run_smoke(report_path: Path, timeout: float) -> dict[str, Any]:
    coordinator_port = free_port()
    web_port = free_port()
    next_port = free_port()
    worker_name = "mac-mini"
    deadline = time.monotonic() + timeout
    pycache_prefix = Path(tempfile.gettempdir()) / "dialectical-dev-smoke-pycache"

    with tempfile.TemporaryDirectory(prefix="dialectical-dev-smoke-") as tmp:
        env = os.environ.copy()
        env.update(
            {
                "DIALECTICAL_DEV_HOME": tmp,
                "DIALECTICAL_DEV_COORDINATOR_PORT": str(coordinator_port),
                "DIALECTICAL_DEV_WEB_PORT": str(web_port),
                "DIALECTICAL_DEV_NEXT_PORT": str(next_port),
                "DIALECTICAL_DEV_NEXT_MODE": "start",
                "DIALECTICAL_DEV_RELOAD": "0",
                "DIALECTICAL_NEXT_DIST_DIR": ".next-dev-smoke",
                "NEXT_TSCONFIG_PATH": "tsconfig.dev-smoke.json",
                "PYTHONPYCACHEPREFIX": str(pycache_prefix),
                "DIALECTICAL_USER_TOKEN": DEFAULT_USER_TOKEN,
                "DIALECTICAL_WORKER_NAME": worker_name,
                "DIALECTICAL_ENABLE_MOCK": "1",
                "DIALECTICAL_ENABLE_REAL_ADAPTERS": "0",
            }
        )

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("w", encoding="utf-8") as log_file:
            build = subprocess.run(
                ["pnpm", "--dir", "web", "build"],
                cwd=ROOT,
                env={**env, "NEXT_DIST_DIR": ".next-dev-smoke"},
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if build.returncode != 0:
                raise RuntimeError(f"Next smoke build failed with code {build.returncode}\n{log_tail(LOG_PATH)}")

            process = subprocess.Popen(
                ["make", "dev"],
                cwd=ROOT,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                health = wait_for(
                    "coordinator health",
                    deadline,
                    lambda: fetch_json(f"http://127.0.0.1:{coordinator_port}/healthz"),
                )
                if health.get("status") != "ok":
                    raise RuntimeError(f"unexpected health payload: {health}")

                wait_for(
                    "Next upstream",
                    deadline,
                    lambda: "Debates" in fetch_text(f"http://127.0.0.1:{next_port}/", accept="text/html")
                    or (_ for _ in ()).throw(RuntimeError("Next home missing Debates marker")),
                )
                wait_for(
                    "web proxy",
                    deadline,
                    lambda: "Debates" in fetch_text(f"http://127.0.0.1:{web_port}/", accept="text/html")
                    or (_ for _ in ()).throw(RuntimeError("web home missing Debates marker")),
                )
                worker_payload = wait_for(
                    "Worker A registration",
                    deadline,
                    lambda: require_worker(
                        fetch_json(f"http://127.0.0.1:{web_port}/api/backends/status"),
                        worker_name,
                    ),
                )
                worker = worker_payload
            except Exception:
                if process.poll() is not None:
                    raise RuntimeError(f"make dev exited early with code {process.returncode}\n{log_tail(LOG_PATH)}")
                raise
            finally:
                stop_process_group(process)

    report = {
        "status": "passed",
        "completed_at": utc_now(),
        "command": "make dev",
        "ports": {"coordinator": coordinator_port, "web": web_port, "next": next_port},
        "worker": {
            "name": worker_name,
            "status": worker.get("status"),
            "capabilities": worker.get("capabilities") or [],
        },
        "checks": [
            "coordinator-health",
            "next-upstream",
            "web-home",
            "worker-a-online",
            "worker-a-mock-capability",
        ],
        "log_path": str(LOG_PATH),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Boot make dev on isolated ports and verify its goal topology")
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()

    try:
        report = run_smoke(args.report_path, args.timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"dev smoke failed: {exc}", file=sys.stderr)
        tail = log_tail(LOG_PATH)
        if tail:
            print(tail, file=sys.stderr)
        return 1

    ports = report["ports"]
    print(
        "dev smoke passed: "
        f"coordinator :{ports['coordinator']}; web :{ports['web']}; next :{ports['next']}; "
        f"worker {report['worker']['name']} online"
    )
    print(f"wrote dev smoke report: {args.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
