#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CHECK_REPORT = Path("/private/tmp/dialectical-local-single-machine-check.json")
DEFAULT_ACCEPTANCE_REPORT = Path("/private/tmp/dialectical-local-single-machine-acceptance.json")
DEFAULT_AUTH_REPORT = Path("/private/tmp/dialectical-model-auth-check.json")
DEFAULT_HOSTING_REPORT = Path("/private/tmp/dialectical-hosting-status.json")
DEFAULT_OUTPUT = Path("ManualSetup_TODO.md")
SETUP_TRACKING_ISSUE = "https://github.com/DebateAIRO/debateairo/issues/5"
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


def checkbox(ok: bool, text: str) -> str:
    return f"- [{'x' if ok else ' '}] {text}"


def online_workers(checks: dict[str, Any]) -> list[dict[str, Any]]:
    workers = (
        checks.get("local_endpoints", {})
        .get("coordinator_backends", {})
        .get("payload", {})
        .get("workers", [])
    )
    if not isinstance(workers, list):
        return []
    return [worker for worker in workers if isinstance(worker, dict) and worker.get("status") == "online"]


def capabilities(workers: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for worker in workers:
        raw = worker.get("capabilities") or []
        if isinstance(raw, list):
            values.update(str(item) for item in raw)
    return values


def probe(checks: dict[str, Any], name: str) -> dict[str, Any]:
    raw = checks.get("cli_status", {}).get(name, {}).get("probe", {})
    return raw if isinstance(raw, dict) else {}


def probe_ok(checks: dict[str, Any], name: str) -> bool:
    return bool(probe(checks, name).get("ok"))


def probe_text(checks: dict[str, Any], name: str) -> str:
    current = probe(checks, name)
    return "\n".join(
        str(current.get(key) or "")
        for key in ("stdout", "stderr", "error")
        if current.get(key)
    )


def auth_summary(checks: dict[str, Any], name: str) -> str:
    current = probe(checks, name)
    text = probe_text(checks, name)
    env_names = set(current.get("env_overrides", []) if isinstance(current.get("env_overrides"), list) else [])
    if current.get("ok"):
        return "ok"
    if "Invalid authentication credentials" in text or "401" in text:
        return "current probe returns 401"
    if "timed out" in text and "GOOGLE_GENAI_USE_GCA" in env_names:
        return "waiting for Google OAuth"
    if text:
        return "probe failed"
    return "not probed"


def hosting_section_value(hosting_report: dict[str, Any], checks: dict[str, Any], key: str) -> dict[str, Any]:
    value = hosting_report.get(key)
    if isinstance(value, dict):
        return value
    fallback = checks.get(key)
    return fallback if isinstance(fallback, dict) else {}


def hosting_dns(hosting_report: dict[str, Any], checks: dict[str, Any]) -> dict[str, Any]:
    value = hosting_report.get("dns")
    if isinstance(value, dict):
        return value
    fallback = checks.get("dns")
    return fallback if isinstance(fallback, dict) else {}


def hosting_cloudflared(hosting_report: dict[str, Any], checks: dict[str, Any]) -> dict[str, Any]:
    value = hosting_report.get("cloudflared")
    if isinstance(value, dict):
        return value
    fallback = checks.get("cloudflared")
    return fallback if isinstance(fallback, dict) else {}


def hosting_quick_tunnel_ok(hosting_report: dict[str, Any], endpoints: dict[str, Any], public_url: dict[str, Any]) -> bool:
    quick = hosting_report.get("quick_tunnel")
    if isinstance(quick, dict):
        api = quick.get("api")
        web = quick.get("web")
        return bool(isinstance(api, dict) and api.get("ok") and isinstance(web, dict) and web.get("ok"))
    return bool(
        isinstance(public_url, dict)
        and public_url.get("source") == "quick_tunnel"
        and endpoints.get("public_backends", {}).get("ok")
    )


def hosting_named_endpoint_ok(hosting_report: dict[str, Any]) -> bool:
    named = hosting_report.get("named_endpoint")
    return bool(isinstance(named, dict) and named.get("ok"))


def hosting_named_web_ok(hosting_report: dict[str, Any]) -> bool:
    named = hosting_report.get("named_web")
    return bool(isinstance(named, dict) and named.get("ok"))


def nameserver_summary(dns: dict[str, Any]) -> str:
    nameservers = dns.get("nameservers") or dns.get("registry_nameservers") or []
    if not isinstance(nameservers, list) or not nameservers:
        return "<none>"
    return ", ".join(str(nameserver) for nameserver in nameservers)


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a current manual setup checklist for the single-Mac setup.")
    parser.add_argument("--check-report", type=Path, default=DEFAULT_CHECK_REPORT)
    parser.add_argument("--acceptance-report", type=Path, default=DEFAULT_ACCEPTANCE_REPORT)
    parser.add_argument("--auth-report", type=Path, default=DEFAULT_AUTH_REPORT)
    parser.add_argument("--hosting-report", type=Path, default=DEFAULT_HOSTING_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    check_report = load_json(args.check_report)
    acceptance_report = load_json(args.acceptance_report)
    auth_report = load_json(args.auth_report)
    hosting_report = load_json(args.hosting_report)
    checks = check_report.get("checks", {}) if isinstance(check_report.get("checks"), dict) else {}
    auth_checks = auth_report.get("checks", {}) if isinstance(auth_report.get("checks"), dict) else {}
    workers = online_workers(checks)
    caps = capabilities(workers)
    endpoints = checks.get("local_endpoints", {})
    lm_studio = checks.get("lm_studio", {})
    gemini_auth = checks.get("gemini_auth", {})
    gemini_google_auth_configured = bool(isinstance(gemini_auth, dict) and gemini_auth.get("ok"))
    dns = hosting_dns(hosting_report, checks)
    cloudflared = hosting_cloudflared(hosting_report, checks)
    hosting_next_action = str(hosting_report.get("next_action") or "")
    public_url = checks.get("public_url", {})
    generated_at = datetime.now(timezone.utc).isoformat()

    lines = [
        "# Manual Setup TODO",
        "",
        "Generated from local reports. Re-run with:",
        "",
        "```sh",
        "make setup-status",
        "```",
        "",
        f"Generated at: `{generated_at}`",
        f"Tracking issue: {SETUP_TRACKING_ISSUE}",
        "",
        "## Current Proof",
        "",
        checkbox(bool(endpoints.get("coordinator_health", {}).get("ok")), "Coordinator is reachable at `http://127.0.0.1:8000`."),
        checkbox(
            bool(endpoints.get("web_home", {}).get("ok") and endpoints.get("web_static_assets", {}).get("ok")),
            "Web app is reachable at `http://127.0.0.1:3000` with static assets.",
        ),
        checkbox(bool(workers), "At least one local worker is online."),
        checkbox(CODEX_MODEL in caps, "`codex-gpt-5.5` is enabled on the local worker."),
        checkbox(
            LMSTUDIO_MODEL in caps and bool(lm_studio.get("expected_model_loaded")),
            "`lmstudio:google_gemma-4-e4b-it` is enabled and loaded.",
        ),
        checkbox(bool(acceptance_report.get("ok")), "`make local-single-machine-acceptance` passes."),
        checkbox(
            hosting_quick_tunnel_ok(hosting_report, endpoints, public_url if isinstance(public_url, dict) else {}),
            "Temporary Cloudflare quick tunnel currently works.",
        ),
        "",
        "## Remaining Account/Auth Work",
        "",
        checkbox(CLAUDE_MODEL in caps or probe_ok(auth_checks, "claude"), f"Claude personal auth works. Current detail: {auth_summary(auth_checks, 'claude')}."),
        checkbox(
            gemini_google_auth_configured,
            "Gemini CLI is configured for Google-account OAuth and the worker has no `GEMINI_API_KEY`.",
        ),
        checkbox(GEMINI_MODEL in caps or probe_ok(auth_checks, "gemini"), f"Gemini Google-account auth works. Current detail: {auth_summary(auth_checks, 'gemini')}."),
        "",
        "Commands after completing Claude/Gemini login:",
        "If you use `make interactive-manual-setup`, accept its local model routing refresh. If you log in manually, run:",
        "",
        "```sh",
        "make probe-model-auth",
        "make refresh-local-models",
        "make local-status",
        "```",
        "",
        "## Remaining Domain/Hosting Work",
        "",
        checkbox(bool(dns.get("delegated_to_cloudflare")), "`dezbatere.ro` delegates to Cloudflare nameservers."),
        checkbox(bool(cloudflared.get("cert_exists")), "`cloudflared tunnel login` has created `~/.cloudflared/cert.pem`."),
        checkbox(bool(cloudflared.get("named_tunnel_ready")), "Named Cloudflare tunnel config and credentials are ready."),
        checkbox(bool(cloudflared.get("service_loaded")), "Named Cloudflare tunnel launchd service is loaded."),
        checkbox(hosting_named_endpoint_ok(hosting_report), "`https://dezbatere.ro/api/backends/status` serves the local app."),
        checkbox(hosting_named_web_ok(hosting_report), "`https://dezbatere.ro/` serves the web UI and static assets."),
        "",
        f"Current registry nameservers: `{nameserver_summary(dns)}`",
        f"Hosting next action: {hosting_next_action or 'run `make hosting-status`.'}",
        "",
        "Manual order:",
        "",
        "1. In a normal Terminal, run `make interactive-manual-setup` if you want guided Claude/Gemini/Cloudflare login prompts.",
        "2. Complete `Cloudfare_TODO.md` step 1 in Cloudflare and copy the assigned nameservers.",
        "3. Run `CLOUDFLARE_NAMESERVERS=\"first.ns.cloudflare.com second.ns.cloudflare.com\" make prepare-romarg-nameservers` with the real Cloudflare values.",
        "4. Complete `Romarg_TODO.md` by replacing Romarg nameservers with only the validated Cloudflare nameservers.",
        "5. Run `make wait-dezbatere-dns`.",
        "6. Run `make hosting-status`.",
        "7. Run `cloudflared tunnel login` if `make interactive-manual-setup` did not already complete it.",
        "8. Run `make resume-dezbatere-hosting`.",
        "9. After manual HTTPS verification, run `INSTALL_SERVICE=1 STOP_QUICK_TUNNEL=1 make resume-dezbatere-hosting`.",
        "10. Run `make final-single-machine-check` for the strict completion gate.",
        "",
        "## Reference Files",
        "",
        "- `Romarg_TODO.md`",
        "- `Romarg_Nameservers_To_Set.md`",
        "- `Cloudfare_TODO.md`",
        "- `Cloudflare_TODO.md`",
        "- `ModelAuth_TODO.md`",
        "- `deploy/local-single-computer-dezbatere.md`",
        f"- GitHub tracking issue: {SETUP_TRACKING_ISSUE}",
        "",
    ]

    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
