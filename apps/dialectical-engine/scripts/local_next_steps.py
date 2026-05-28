#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_CHECK_REPORT = Path("/private/tmp/dialectical-local-single-machine-check.json")
DEFAULT_ACCEPTANCE_REPORT = Path("/private/tmp/dialectical-local-single-machine-acceptance.json")
DEFAULT_AUTH_REPORT = Path("/private/tmp/dialectical-model-auth-check.json")
DEFAULT_GEMINI_SETTINGS = Path("~/.gemini/settings.json").expanduser()
CLAUDE_MODEL = "claude-sonnet-4-6"
CODEX_MODEL = "codex-gpt-5.5"
GEMINI_MODEL = "gemini-2.5-flash"
LMSTUDIO_MODEL = "lmstudio:google_gemma-4-e4b-it"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def probe_ok(cli: dict[str, Any], name: str) -> bool:
    probe = cli.get(name, {}).get("probe", {})
    return bool(isinstance(probe, dict) and probe.get("ok"))


def probe_present(cli: dict[str, Any], name: str) -> bool:
    probe = cli.get(name, {}).get("probe", {})
    return isinstance(probe, dict)


def probe_text(cli: dict[str, Any], name: str) -> str:
    probe = cli.get(name, {}).get("probe", {})
    if not isinstance(probe, dict):
        return ""
    parts = [
        str(probe.get("stdout") or ""),
        str(probe.get("stderr") or ""),
        str(probe.get("error") or ""),
    ]
    return "\n".join(part for part in parts if part)


def probe_env_overrides(cli: dict[str, Any], name: str) -> set[str]:
    probe = cli.get(name, {}).get("probe", {})
    if not isinstance(probe, dict):
        return set()
    values = probe.get("env_overrides", [])
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values}


def auth_detail(cli: dict[str, Any], name: str) -> str:
    text = probe_text(cli, name)
    env_names = probe_env_overrides(cli, name)
    if "Invalid authentication credentials" in text or "401" in text:
        return "current probe returns 401"
    if "timed out" in text and "GOOGLE_GENAI_USE_GCA" in env_names:
        return "current probe is waiting for Google OAuth"
    if "Please set an Auth method" in text or "GEMINI_API_KEY" in text:
        return "auth method is missing"
    if "Not logged in" in text:
        return "not logged in"
    if text:
        return "current probe fails"
    return "not enabled yet"


def online_workers(checks: dict[str, Any]) -> list[dict[str, Any]]:
    backends = checks.get("local_endpoints", {}).get("coordinator_backends", {})
    workers = backends.get("payload", {}).get("workers", [])
    if not isinstance(workers, list):
        return []
    return [worker for worker in workers if isinstance(worker, dict) and worker.get("status") == "online"]


def worker_capabilities(workers: list[dict[str, Any]]) -> set[str]:
    capabilities: set[str] = set()
    for worker in workers:
        raw = worker.get("capabilities") or []
        if isinstance(raw, list):
            capabilities.update(str(item) for item in raw)
    return capabilities


def nested_get(payload: dict[str, Any], dotted_key: str) -> Any:
    current: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def gemini_oauth_configured(settings_path: Path = DEFAULT_GEMINI_SETTINGS) -> bool:
    settings = load_json(settings_path)
    return (
        settings.get("selectedAuthType") == "oauth-personal"
        or nested_get(settings, "security.auth.selectedType") == "oauth-personal"
    )


def print_section(title: str, lines: list[str]) -> None:
    print(title)
    if not lines:
        print("- none")
        return
    for line in lines:
        print(f"- {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Print concise next steps for the single-Mac dezbatere.ro setup.")
    parser.add_argument("--check-report", type=Path, default=DEFAULT_CHECK_REPORT)
    parser.add_argument("--acceptance-report", type=Path, default=DEFAULT_ACCEPTANCE_REPORT)
    parser.add_argument("--auth-report", type=Path, default=DEFAULT_AUTH_REPORT)
    args = parser.parse_args()

    check_report = load_json(args.check_report)
    acceptance_report = load_json(args.acceptance_report)
    auth_report = load_json(args.auth_report)
    checks = check_report.get("checks", {}) if isinstance(check_report.get("checks"), dict) else {}
    auth_checks = auth_report.get("checks", {}) if isinstance(auth_report.get("checks"), dict) else {}

    workers = online_workers(checks)
    capabilities = worker_capabilities(workers)
    endpoints = checks.get("local_endpoints", {})
    lm_studio = checks.get("lm_studio", {})
    gemini_auth = checks.get("gemini_auth", {})
    gemini_google_auth_configured = bool(isinstance(gemini_auth, dict) and gemini_auth.get("ok"))
    dns = checks.get("dns", {})
    cloudflared = checks.get("cloudflared", {})
    quick_tunnel = checks.get("quick_tunnel", {})
    public_url = checks.get("public_url", {})
    cli = checks.get("cli_status", {})
    auth_cli = auth_checks.get("cli_status", {}) if isinstance(auth_checks.get("cli_status"), dict) else {}
    if not any(probe_present(auth_cli, name) for name in ("claude", "codex", "gemini")):
        auth_cli = cli
    acceptance_ok = acceptance_report.get("ok")

    ready: list[str] = []
    if endpoints.get("coordinator_health", {}).get("ok"):
        ready.append("Coordinator: http://127.0.0.1:8000")
    if endpoints.get("web_home", {}).get("ok") and endpoints.get("web_static_assets", {}).get("ok"):
        ready.append("Web app: http://127.0.0.1:3000")
    if workers:
        worker_summary = ", ".join(
            f"{worker.get('name')} {worker.get('capabilities')}" for worker in workers
        )
        ready.append(f"Online local workers: {worker_summary}")
    if CODEX_MODEL in capabilities:
        ready.append("Codex CLI model is enabled")
    if CLAUDE_MODEL in capabilities:
        ready.append("Claude CLI model is enabled")
    if GEMINI_MODEL in capabilities:
        ready.append("Gemini CLI model is enabled")
    elif gemini_google_auth_configured:
        ready.append("Gemini is pinned to Google-account auth; browser OAuth login is still pending")
    if LMSTUDIO_MODEL in capabilities and lm_studio.get("expected_model_loaded"):
        ready.append("LM Studio Gemma is enabled natively on mac-mini")
    if isinstance(public_url, dict) and public_url.get("url") and endpoints.get("public_backends", {}).get("ok"):
        if public_url.get("source") == "named_tunnel":
            ready.append(f"Named public URL works: {public_url['url']}")
        elif public_url.get("source") == "quick_tunnel":
            ready.append(f"Temporary quick tunnel works: {public_url['url']}")
        else:
            ready.append(f"Public URL works: {public_url['url']}")
    elif quick_tunnel.get("current_url") and endpoints.get("public_backends", {}).get("ok"):
        ready.append(f"Temporary quick tunnel works: {quick_tunnel['current_url']}")
    if acceptance_ok is True:
        ready.append("Strict local acceptance passed")

    todo: list[str] = []
    if CLAUDE_MODEL not in capabilities and not probe_ok(auth_cli, "claude"):
        todo.append(
            f"Claude: {auth_detail(auth_cli, 'claude')}; run `claude auth login --claudeai`, "
            "then `make refresh-local-models`"
        )
    if GEMINI_MODEL not in capabilities and not probe_ok(auth_cli, "gemini"):
        gemini_text = probe_text(auth_cli, "gemini")
        if gemini_google_auth_configured or "timed out" in gemini_text or gemini_oauth_configured():
            todo.append(
                f"Gemini: {auth_detail(auth_cli, 'gemini')}; run `gemini` in a normal Terminal, finish Login with Google, then `make refresh-local-models`"
            )
        else:
            todo.append(
                f"Gemini: {auth_detail(auth_cli, 'gemini')}; run `make configure-gemini-google-auth`, then `gemini` and finish Login with Google"
            )
    if dns.get("delegated_to_romarg"):
        todo.append(
            "Domain: add dezbatere.ro to Cloudflare, then run `make prepare-romarg-nameservers` with the assigned nameservers"
        )
        todo.append("Romarg: use `Romarg_Nameservers_To_Set.md`, then run `make wait-dezbatere-dns`")
    elif dns.get("delegated_to_cloudflare") and not cloudflared.get("cert_exists"):
        todo.append("Cloudflare: run `cloudflared tunnel login`")
    if dns.get("delegated_to_cloudflare") and not cloudflared.get("named_tunnel_ready"):
        todo.append("Tunnel: run `make resume-dezbatere-hosting`")
    if cloudflared.get("named_tunnel_ready"):
        todo.append("Named tunnel ready: run `INSTALL_SERVICE=1 STOP_QUICK_TUNNEL=1 make resume-dezbatere-hosting`")

    verify = [
        "make local-single-machine-check",
        "make local-single-machine-acceptance",
        "make probe-model-auth",
    ]
    if not cloudflared.get("named_tunnel_ready"):
        verify.append("make prepare-romarg-nameservers after Cloudflare assigns nameservers")
        verify.append("make wait-dezbatere-dns after Romarg nameserver change")
    else:
        verify.append("curl https://dezbatere.ro/api/backends/status")

    print_section("Ready Now", ready)
    print()
    print_section("Next Actions", todo)
    print()
    print_section("Verification Commands", verify)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
