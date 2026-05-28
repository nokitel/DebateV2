from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "final_single_machine_check.py"


def load_module():
    spec = importlib.util.spec_from_file_location("final_single_machine_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local_report(*, named_public: bool = True) -> dict[str, object]:
    return {
        "checks": {
            "local_endpoints": {
                "web_home": {"ok": True},
                "web_static_assets": {"ok": True},
                "web_backends": {"ok": True},
                "coordinator_backends": {
                    "payload": {
                        "workers": [
                            {
                                "name": "mac-mini",
                                "status": "online",
                                "capabilities": ["codex-gpt-5", "lmstudio:google_gemma-4-e4b-it"],
                            }
                        ]
                    }
                },
            },
            "lm_studio": {
                "expected_model_loaded": True,
                "probe": {"ok": True},
            },
            "runtime_routing": {"ok": True},
            "gemini_auth": {
                "ok": True,
                "worker_google_account_env": True,
                "worker_gemini_api_key_present": False,
                "shell_gemini_api_key_present": False,
            },
            "public_url": {"source": "named_tunnel" if named_public else "quick_tunnel"},
        }
    }


def auth_report(*, claude_ok: bool = True, gemini_ok: bool = True) -> dict[str, object]:
    return {
        "checks": {
            "cli_status": {
                "codex": {"probe": {"ok": True}},
                "claude": {"probe": {"ok": claude_ok}},
                "gemini": {"probe": {"ok": gemini_ok}},
            }
        }
    }


def hosting_report(*, delegated: bool = True, named_web: bool = True) -> dict[str, object]:
    return {
        "dns": {"delegated_to_cloudflare": delegated},
        "cloudflared": {
            "cert_exists": True,
            "named_tunnel_ready": True,
            "service_loaded": True,
        },
        "named_endpoint": {"ok": True},
        "named_web": {"ok": named_web},
    }


def failed_names(checks: list[dict[str, object]]) -> set[str]:
    return {str(check["name"]) for check in checks if not check["ok"]}


def test_final_check_passes_when_auth_hosting_and_local_runtime_are_ready() -> None:
    module = load_module()

    checks = module.evaluate(
        local_report(),
        {"ok": True},
        auth_report(),
        hosting_report(),
        require_claude=True,
        require_gemini=True,
        require_named_hosting=True,
    )

    assert failed_names(checks) == set()


def test_final_check_reports_pending_manual_gates() -> None:
    module = load_module()

    checks = module.evaluate(
        local_report(named_public=False),
        {"ok": True},
        auth_report(claude_ok=False, gemini_ok=False),
        hosting_report(delegated=False, named_web=False),
        require_claude=True,
        require_gemini=True,
        require_named_hosting=True,
    )

    assert {
        "claude-auth",
        "gemini-auth",
        "cloudflare-delegation",
        "named-web",
        "public-url-source",
    } <= failed_names(checks)


def test_final_check_can_allow_missing_optional_personal_cli_auth() -> None:
    module = load_module()

    checks = module.evaluate(
        local_report(),
        {"ok": True},
        auth_report(claude_ok=False, gemini_ok=False),
        hosting_report(),
        require_claude=False,
        require_gemini=False,
        require_named_hosting=True,
    )

    assert "claude-auth" not in failed_names(checks)
    assert "gemini-auth" not in failed_names(checks)
