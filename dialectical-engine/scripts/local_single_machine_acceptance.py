#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECK_REPORT = Path("/private/tmp/dialectical-local-single-machine-check.json")
DEFAULT_LMSTUDIO_REPORT = Path("/private/tmp/dialectical-lmstudio-job-probe.json")
DEFAULT_REPORT = Path("/private/tmp/dialectical-local-single-machine-acceptance.json")
EXPECTED_WORKERS = {
    "mac-mini": "codex-gpt-5.5",
}
REQUIRED_CAPABILITIES = ["lmstudio:google_gemma-4-e4b-it"]


def run(command: list[str], *, timeout: int = 120) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "ok": proc.returncode == 0,
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def worker_has_capability(workers: list[dict[str, Any]], name: str, capability: str) -> bool:
    for worker in workers:
        if worker.get("name") != name or worker.get("status") != "online":
            continue
        capabilities = worker.get("capabilities") or []
        return capability in capabilities
    return False


def online_worker_has_capability(workers: list[dict[str, Any]], capability: str) -> bool:
    for worker in workers:
        if worker.get("status") != "online":
            continue
        capabilities = worker.get("capabilities") or []
        if capability in capabilities:
            return True
    return False


def evaluate_check(check_report: dict[str, Any], *, require_public_tunnel: bool) -> list[str]:
    checks = check_report["checks"]
    endpoints = checks["local_endpoints"]
    lm_studio = checks["lm_studio"]
    workers = endpoints.get("coordinator_backends", {}).get("payload", {}).get("workers", [])
    failures: list[str] = []

    if not endpoints.get("coordinator_health", {}).get("ok"):
        failures.append("coordinator health endpoint failed")
    if not endpoints.get("web_home", {}).get("ok"):
        failures.append("web home failed")
    if not endpoints.get("web_static_assets", {}).get("ok"):
        failures.append("web static assets failed")
    if not endpoints.get("web_backends", {}).get("ok"):
        failures.append("web backends API failed")
    for name, capability in EXPECTED_WORKERS.items():
        if not worker_has_capability(workers, name, capability):
            failures.append(f"worker {name} is not online with {capability}")
    for capability in REQUIRED_CAPABILITIES:
        if not online_worker_has_capability(workers, capability):
            failures.append(f"no online local worker has {capability}")
    if not lm_studio.get("models_endpoint", {}).get("ok"):
        failures.append("LM Studio /v1/models failed")
    if not lm_studio.get("expected_model_loaded"):
        failures.append(f"LM Studio expected model not loaded: {lm_studio.get('expected_model')}")
    if not lm_studio.get("probe", {}).get("ok"):
        failures.append("LM Studio chat probe failed")
    if not checks.get("runtime_routing", {}).get("ok"):
        failures.append("runtime routing does not include LM Studio capability")
    if require_public_tunnel and not endpoints.get("public_backends", {}).get("ok"):
        failures.append("public quick tunnel API failed")
    return failures


def external_blockers(check_report: dict[str, Any]) -> list[str]:
    checks = check_report["checks"]
    blockers: list[str] = []
    dns = checks.get("dns", {})
    cloudflared = checks.get("cloudflared", {})
    cli = checks.get("cli_status", {})
    hydration = checks.get("checkout_hydration", {})
    if dns.get("delegated_to_romarg"):
        blockers.append("dezbatere.ro still delegates to Romarg nameservers")
    if dns.get("romarg_authoritative_status") == "REFUSED":
        blockers.append("Romarg authoritative DNS returns REFUSED for dezbatere.ro")
    if not cloudflared.get("named_tunnel_ready"):
        blockers.append("Cloudflare named tunnel credentials/config are not ready")
    if hydration.get("offloaded"):
        blockers.append("some source files remain iCloud-offloaded")
    claude_probe = cli.get("claude", {}).get("probe", {})
    if claude_probe and not claude_probe.get("ok"):
        blockers.append("Claude CLI auth is not ready")
    gemini_probe = cli.get("gemini", {}).get("probe", {})
    if gemini_probe and not gemini_probe.get("ok"):
        blockers.append("Gemini CLI auth is not ready")
    return blockers


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict acceptance for the simplified single-Mac runtime.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check-report", type=Path, default=DEFAULT_CHECK_REPORT)
    parser.add_argument("--lmstudio-report", type=Path, default=DEFAULT_LMSTUDIO_REPORT)
    parser.add_argument("--probe-model-auth", action="store_true")
    parser.add_argument("--require-public-tunnel", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    command = [sys.executable, str(ROOT / "scripts" / "local_single_machine_check.py")]
    if args.probe_model_auth:
        command.append("--probe-models")
    command.extend(["--report-path", str(args.check_report)])
    check_run = run(command, timeout=180)

    lmstudio_run = run(
        [
            sys.executable,
            str(ROOT / "scripts" / "probe_lmstudio_worker_job.py"),
            "--report-path",
            str(args.lmstudio_report),
        ],
        timeout=180,
    )

    check_report = load_json(args.check_report)
    lmstudio_report = load_json(args.lmstudio_report)
    failures = evaluate_check(check_report, require_public_tunnel=args.require_public_tunnel)
    if not lmstudio_run["ok"] or not lmstudio_report.get("ok"):
        failures.append("LM Studio job probe failed")

    report = {
        "ok": not failures,
        "failures": failures,
        "external_blockers": external_blockers(check_report),
        "check_run": check_run,
        "lmstudio_run": lmstudio_run,
        "check_report": str(args.check_report),
        "lmstudio_report": str(args.lmstudio_report),
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Report: {args.report_path}")
    if failures:
        print("Local single-machine acceptance: failed")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Local single-machine acceptance: ok")
    blockers = report["external_blockers"]
    if blockers:
        print("External follow-ups:")
        for blocker in blockers:
            print(f"- {blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
