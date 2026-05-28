#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any
from uuid import UUID


class VisibilityError(RuntimeError):
    pass


def require_uuid_value(label: str, value: Any) -> str:
    if not isinstance(value, str):
        raise VisibilityError(f"{label} is not a string")
    normalized = value.strip()
    if not normalized:
        raise VisibilityError(f"{label} is blank")
    try:
        UUID(normalized)
    except ValueError as exc:
        raise VisibilityError(f"{label} is not a UUID") from exc
    return normalized


def require_timezone_timestamp(label: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise VisibilityError(f"{label} missing")
    parse_value = value.strip()
    if parse_value.endswith("Z"):
        parse_value = parse_value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(parse_value)
    except ValueError as exc:
        raise VisibilityError(f"{label} not ISO formatted") from exc
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise VisibilityError(f"{label} missing timezone")


def is_mock_model_id(model_id: str) -> bool:
    return model_id == "mock-local" or model_id.startswith("mock-")


def is_placeholder_model_id(model_id: str) -> bool:
    value = model_id.strip().lower()
    return not value or "<" in value or ">" in value or "placeholder" in value


def capability_values(
    worker_name: str,
    capabilities: Any,
    reject_non_production_capabilities: bool = False,
) -> list[str]:
    if not isinstance(capabilities, list):
        raise VisibilityError(f"{worker_name} has no advertised capabilities")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, capability in enumerate(capabilities, start=1):
        if not isinstance(capability, str):
            raise VisibilityError(f"{worker_name} capability {index} is not a string")
        value = capability.strip()
        if not value:
            raise VisibilityError(f"{worker_name} capability {index} is blank")
        if value in seen:
            raise VisibilityError(f"{worker_name} duplicate capability: {value}")
        if reject_non_production_capabilities and is_placeholder_model_id(value):
            raise VisibilityError(f"{worker_name} has placeholder capability: {value}")
        if reject_non_production_capabilities and is_mock_model_id(value):
            raise VisibilityError(f"{worker_name} has mock capability: {value}")
        seen.add(value)
        normalized.append(value)
    return normalized


def worker_status_detail(
    payload: dict[str, Any],
    worker_name: str,
    expected_status: str,
    require_capabilities: bool = False,
    required_capabilities: list[str] | None = None,
    reject_non_production_capabilities: bool = False,
) -> str:
    workers = payload.get("workers")
    if not isinstance(workers, list):
        raise VisibilityError("/api/backends/status did not return a workers list")

    required = sorted({capability.strip() for capability in required_capabilities or [] if capability.strip()})
    seen: list[str] = []
    duplicate_names: set[str] = set()
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        name = str(worker.get("name") or "").strip()
        if name:
            if name in seen:
                duplicate_names.add(name)
            seen.append(name)
    if duplicate_names:
        raise VisibilityError(f"duplicate worker names: {', '.join(sorted(duplicate_names))}")

    for worker in workers:
        if not isinstance(worker, dict):
            continue
        name = str(worker.get("name") or "").strip()
        if name != worker_name:
            continue

        if "id" not in worker:
            raise VisibilityError(f"{worker_name} missing id")
        require_uuid_value(f"{worker_name} id", worker.get("id"))
        if "current_job_id" not in worker:
            raise VisibilityError(f"{worker_name} missing current_job_id")
        current_job_id = worker.get("current_job_id")
        if current_job_id is not None:
            require_uuid_value(f"{worker_name} current_job_id", current_job_id)
        require_timezone_timestamp(f"{worker_name} last_seen", worker.get("last_seen"))

        status = str(worker.get("status") or "").strip()
        if status != expected_status:
            raise VisibilityError(f"{worker_name} is {status or 'missing-status'}, not {expected_status}")
        capabilities = capability_values(
            worker_name,
            worker.get("capabilities"),
            reject_non_production_capabilities,
        )
        if require_capabilities and not capabilities:
            raise VisibilityError(f"{worker_name} is {expected_status} but has no advertised capabilities")
        if required:
            capability_set = set(capabilities)
            missing = sorted(set(required) - capability_set)
            if missing:
                raise VisibilityError(
                    f"{worker_name} is {expected_status} but missing required capabilities: {', '.join(missing)}"
                )
        required_detail = f"; required {', '.join(required)}" if required else ""
        return f"{worker_name}:{status} ({len(capabilities)} capabilities{required_detail})"

    detail = ", ".join(sorted(seen)) if seen else "no workers"
    raise VisibilityError(f"{worker_name} missing from /api/backends/status; saw {detail}")


def worker_visibility_detail(payload: dict[str, Any], worker_name: str) -> str:
    return worker_status_detail(payload, worker_name, "online", require_capabilities=True)


def fetch_status(base_url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/backends/status",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise VisibilityError("/api/backends/status did not return a JSON object")
    return payload


def wait_for_worker_visible(base_url: str, worker_name: str, timeout: float, interval: float) -> str:
    return wait_for_worker_status(base_url, worker_name, "online", True, [], False, timeout, interval)


def wait_for_worker_status(
    base_url: str,
    worker_name: str,
    expected_status: str,
    require_capabilities: bool,
    required_capabilities: list[str],
    reject_non_production_capabilities: bool,
    timeout: float,
    interval: float,
) -> str:
    deadline = time.monotonic() + max(timeout, 0)
    last_error = "not checked"
    while True:
        try:
            return worker_status_detail(
                fetch_status(base_url, max(min(interval, 10), 1)),
                worker_name,
                expected_status,
                require_capabilities,
                required_capabilities,
                reject_non_production_capabilities,
            )
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, VisibilityError) as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            raise VisibilityError(
                f"{worker_name} was not {expected_status} at {base_url.rstrip('/')} within {timeout:g}s: {last_error}"
            )
        time.sleep(max(interval, 0.25))


def parse_required_capabilities(values: list[str]) -> list[str]:
    capabilities: list[str] = []
    seen: set[str] = set()
    for value in values:
        for candidate in value.split(","):
            capability = candidate.strip()
            if not capability or capability in seen:
                continue
            capabilities.append(capability)
            seen.add(capability)
    return capabilities


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Dialectical worker is visible through /api/backends/status")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--worker-name", required=True)
    parser.add_argument("--expected-status", default="online", choices=["online", "offline", "degraded"])
    parser.add_argument("--require-capabilities", action="store_true")
    parser.add_argument("--required-capability", action="append", default=[])
    parser.add_argument("--required-capabilities", default="")
    parser.add_argument("--reject-non-production-capabilities", action="store_true")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--interval", type=float, default=3)
    args = parser.parse_args()

    required_capabilities = parse_required_capabilities([args.required_capabilities, *args.required_capability])
    try:
        detail = wait_for_worker_status(
            args.base_url,
            args.worker_name,
            args.expected_status,
            args.require_capabilities,
            required_capabilities,
            args.reject_non_production_capabilities,
            args.timeout,
            args.interval,
        )
    except VisibilityError as exc:
        print(f"worker visibility check failed: {exc}", file=sys.stderr)
        return 2
    print(f"Worker status verified: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
