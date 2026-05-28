#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_LOCAL_CHECK_REPORT = Path("/private/tmp/dialectical-local-single-machine-check.json")
DEFAULT_ACCEPTANCE_REPORT = Path("/private/tmp/dialectical-local-single-machine-acceptance.json")
DEFAULT_AUTH_REPORT = Path("/private/tmp/dialectical-model-auth-check.json")
DEFAULT_HOSTING_REPORT = Path("/private/tmp/dialectical-hosting-status.json")
DEFAULT_REPORT = Path("/private/tmp/dialectical-final-single-machine-check.json")
CODEX_MODEL = "codex-gpt-5"
CLAUDE_MODEL = "claude-sonnet-4.5"
GEMINI_MODEL = "gemini-2.5-pro"
LMSTUDIO_MODEL = "lmstudio:google_gemma-4-e4b-it"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def nested_get(payload: dict[str, Any], path: list[str], default: Any = None) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def online_workers(local_report: dict[str, Any]) -> list[dict[str, Any]]:
    workers = nested_get(
        local_report,
        ["checks", "local_endpoints", "coordinator_backends", "payload", "workers"],
        [],
    )
    if not isinstance(workers, list):
        return []
    return [worker for worker in workers if isinstance(worker, dict) and worker.get("status") == "online"]


def capabilities(workers: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for worker in workers:
        raw = worker.get("capabilities") or []
        if isinstance(raw, list):
            result.update(str(item) for item in raw)
    return result


def probe_ok(auth_report: dict[str, Any], cli_name: str) -> bool:
    return bool(nested_get(auth_report, ["checks", "cli_status", cli_name, "probe", "ok"], False))


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": ok, "detail": detail})


def freshness_checks(paths: dict[str, Path], *, max_age_minutes: int, now: float | None = None) -> list[dict[str, Any]]:
    current = time.time() if now is None else now
    max_age_seconds = max(max_age_minutes, 0) * 60
    checks: list[dict[str, Any]] = []
    for name, path in paths.items():
        if not path.exists():
            add_check(checks, f"{name}-fresh", False, f"missing report: {path}")
            continue
        age_seconds = max(0.0, current - path.stat().st_mtime)
        add_check(
            checks,
            f"{name}-fresh",
            age_seconds <= max_age_seconds,
            f"{path} age {age_seconds:.0f}s, max {max_age_seconds}s",
        )
    return checks


def evaluate(
    local_report: dict[str, Any],
    acceptance_report: dict[str, Any],
    auth_report: dict[str, Any],
    hosting_report: dict[str, Any],
    *,
    require_claude: bool,
    require_gemini: bool,
    require_named_hosting: bool,
) -> list[dict[str, Any]]:
    workers = online_workers(local_report)
    caps = capabilities(workers)
    checks: list[dict[str, Any]] = []

    add_check(checks, "local-acceptance", bool(acceptance_report.get("ok")), "make local-single-machine-acceptance")
    add_check(
        checks,
        "local-web",
        bool(
            nested_get(local_report, ["checks", "local_endpoints", "web_home", "ok"], False)
            and nested_get(local_report, ["checks", "local_endpoints", "web_static_assets", "ok"], False)
            and nested_get(local_report, ["checks", "local_endpoints", "web_backends", "ok"], False)
        ),
        "local web, static assets, and same-origin API",
    )
    add_check(checks, "codex-worker", CODEX_MODEL in caps, f"online worker advertises {CODEX_MODEL}")
    add_check(checks, "lmstudio-worker", LMSTUDIO_MODEL in caps, f"online worker advertises {LMSTUDIO_MODEL}")
    add_check(
        checks,
        "lmstudio-runtime",
        bool(
            nested_get(local_report, ["checks", "lm_studio", "expected_model_loaded"], False)
            and nested_get(local_report, ["checks", "lm_studio", "probe", "ok"], False)
            and nested_get(local_report, ["checks", "runtime_routing", "ok"], False)
        ),
        "LM Studio Gemma is loaded, probeable, and in runtime routing",
    )
    add_check(checks, "codex-auth", probe_ok(auth_report, "codex"), "Codex CLI non-interactive probe")
    if require_claude:
        add_check(checks, "claude-auth", probe_ok(auth_report, "claude"), "Claude personal CLI probe")
    if require_gemini:
        gemini_auth = nested_get(local_report, ["checks", "gemini_auth"], {})
        gemini_uses_google_account = bool(
            isinstance(gemini_auth, dict)
            and gemini_auth.get("ok")
            and gemini_auth.get("worker_google_account_env")
            and not gemini_auth.get("worker_gemini_api_key_present")
            and not gemini_auth.get("shell_gemini_api_key_present")
        )
        add_check(checks, "gemini-google-auth-config", gemini_uses_google_account, "Gemini uses Google-account auth, not GEMINI_API_KEY")
        add_check(checks, "gemini-auth", probe_ok(auth_report, "gemini"), "Gemini Google-account CLI probe")

    if require_named_hosting:
        add_check(
            checks,
            "cloudflare-delegation",
            bool(nested_get(hosting_report, ["dns", "delegated_to_cloudflare"], False)),
            "dezbatere.ro registry nameservers are all Cloudflare",
        )
        add_check(
            checks,
            "cloudflared-login",
            bool(nested_get(hosting_report, ["cloudflared", "cert_exists"], False)),
            "cloudflared login created cert.pem",
        )
        add_check(
            checks,
            "named-tunnel-config",
            bool(nested_get(hosting_report, ["cloudflared", "named_tunnel_ready"], False)),
            "named tunnel config and credentials exist",
        )
        add_check(
            checks,
            "named-tunnel-service",
            bool(nested_get(hosting_report, ["cloudflared", "service_loaded"], False)),
            "named cloudflared launchd service is loaded",
        )
        add_check(
            checks,
            "named-api",
            bool(nested_get(hosting_report, ["named_endpoint", "ok"], False)),
            "https://dezbatere.ro/api/backends/status works",
        )
        add_check(
            checks,
            "named-web",
            bool(nested_get(hosting_report, ["named_web", "ok"], False)),
            "https://dezbatere.ro/ and static assets work",
        )
        add_check(
            checks,
            "public-url-source",
            nested_get(local_report, ["checks", "public_url", "source"]) == "named_tunnel",
            "local readiness selected the named tunnel as public URL",
        )

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict final gate for the simplified single-Mac dezbatere.ro setup.")
    parser.add_argument("--local-check-report", type=Path, default=DEFAULT_LOCAL_CHECK_REPORT)
    parser.add_argument("--acceptance-report", type=Path, default=DEFAULT_ACCEPTANCE_REPORT)
    parser.add_argument("--auth-report", type=Path, default=DEFAULT_AUTH_REPORT)
    parser.add_argument("--hosting-report", type=Path, default=DEFAULT_HOSTING_REPORT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--max-report-age-minutes", type=int, default=30)
    parser.add_argument("--allow-missing-claude", action="store_true")
    parser.add_argument("--allow-missing-gemini", action="store_true")
    parser.add_argument("--allow-missing-named-hosting", action="store_true")
    args = parser.parse_args()

    report_paths = {
        "local-check-report": args.local_check_report,
        "acceptance-report": args.acceptance_report,
        "auth-report": args.auth_report,
        "hosting-report": args.hosting_report,
    }
    checks = freshness_checks(report_paths, max_age_minutes=args.max_report_age_minutes)
    checks.extend(
        evaluate(
            load_json(args.local_check_report),
            load_json(args.acceptance_report),
            load_json(args.auth_report),
            load_json(args.hosting_report),
            require_claude=not args.allow_missing_claude,
            require_gemini=not args.allow_missing_gemini,
            require_named_hosting=not args.allow_missing_named_hosting,
        )
    )
    failures = [check for check in checks if not check["ok"]]
    report = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "ok": not failures,
        "checks": checks,
        "failures": failures,
        "inputs": {
            "local_check_report": str(args.local_check_report),
            "acceptance_report": str(args.acceptance_report),
            "auth_report": str(args.auth_report),
            "hosting_report": str(args.hosting_report),
        },
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Report: {args.report_path}")
    print(f"Final single-machine setup: {'ok' if report['ok'] else 'failed'}")
    if failures:
        for failure in failures:
            print(f"- {failure['name']}: {failure['detail']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
