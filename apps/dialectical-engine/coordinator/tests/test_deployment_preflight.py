from __future__ import annotations

import importlib.util
import plistlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALID_CREDENTIALS = (
    '{"AccountTag":"account-tag","TunnelID":"11111111-1111-1111-1111-111111111111","TunnelSecret":"secret"}'
)


def load_deployment_preflight_module():
    name = "dialectical_deployment_preflight"
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "deployment_preflight.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def checks_by_name(checks):
    return {check.name: check for check in checks}


def test_worker_config_checks_report_pinned_allowed_models(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.WORKER_CONFIG = tmp_path / "worker.toml"
    module.WORKER_CONFIG.write_text(
        "\n".join(
            [
                'worker_token = "worker_secret"',
                'allowed_models = [" codex-gpt-5.5 ", "gemini-2.5-flash", "codex-gpt-5.5", ""]',
                "enable_mock = false",
                "enable_real_adapters = true",
                "",
            ]
        )
    )

    checks = checks_by_name(module.worker_config_checks(require_registered=True))

    assert checks["worker-config"].status == "PASS"
    assert checks["worker-token-persisted"].status == "PASS"
    assert checks["user-token-not-persisted"].status == "PASS"
    assert checks["worker-config-parse"].status == "PASS"
    assert checks["worker-allowed-models"].status == "PASS"
    assert checks["worker-allowed-models"].detail == "codex-gpt-5.5, gemini-2.5-flash"
    assert checks["worker-mock-adapter"].status == "PASS"
    assert checks["worker-real-adapters"].status == "PASS"


def test_worker_config_checks_warn_when_allowlist_is_missing(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.WORKER_CONFIG = tmp_path / "worker.toml"
    module.WORKER_CONFIG.write_text('worker_token = "worker_secret"\n')

    checks = checks_by_name(module.worker_config_checks(require_registered=True))

    assert checks["worker-allowed-models"].status == "WARN"
    assert "no allowed_models pin" in checks["worker-allowed-models"].detail


def test_worker_config_checks_fail_malformed_toml(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.WORKER_CONFIG = tmp_path / "worker.toml"
    module.WORKER_CONFIG.write_text('worker_token = "worker_secret"\nallowed_models = [\n')

    checks = checks_by_name(module.worker_config_checks(require_registered=True))

    assert checks["worker-config-parse"].status == "FAIL"


def test_worker_launch_agent_checks_report_adapter_api_env(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    plist_path = tmp_path / "com.dialectical.worker.plist"
    with plist_path.open("wb") as file:
        plistlib.dump(
            {
                "ProgramArguments": ["/python", "-m", "app.main"],
                "WorkingDirectory": str(ROOT / "worker"),
                "EnvironmentVariables": {
                    "GEMINI_API_KEY": "gemini-secret",
                    "PATH": "/usr/bin:/bin",
                },
            },
            file,
        )

    checks = checks_by_name(
        module.installed_launch_agent_checks(
            "worker",
            {
                "path": plist_path,
                "working_directory": ROOT / "worker",
                "required_args": ["-m", "app.main"],
            },
            required=True,
        )
    )

    assert checks["launch-agent:worker:env:GEMINI_API_KEY"].status == "PASS"
    assert checks["launch-agent:worker:env:GEMINI_API_KEY"].detail == "set"
    assert checks["launch-agent:worker:env:XAI_API_KEY"].status == "WARN"
    assert "not set" in checks["launch-agent:worker:env:XAI_API_KEY"].detail


def test_worker_launch_agent_checks_warn_for_placeholder_adapter_api_env(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    plist_path = tmp_path / "com.dialectical.worker.plist"
    with plist_path.open("wb") as file:
        plistlib.dump(
            {
                "ProgramArguments": ["/python", "-m", "app.main"],
                "WorkingDirectory": str(ROOT / "worker"),
                "EnvironmentVariables": {
                    "GEMINI_API_KEY": "<optional-google-ai-studio-api-key>",
                    "XAI_API_KEY": "<optional-xai-api-key>",
                },
            },
            file,
        )

    checks = checks_by_name(
        module.installed_launch_agent_checks(
            "worker",
            {
                "path": plist_path,
                "working_directory": ROOT / "worker",
                "required_args": ["-m", "app.main"],
            },
            required=True,
        )
    )

    assert checks["launch-agent:worker:env:GEMINI_API_KEY"].status == "WARN"
    assert checks["launch-agent:worker:env:GEMINI_API_KEY"].detail == "placeholder value in launchd environment"
    assert checks["launch-agent:worker:env:XAI_API_KEY"].status == "WARN"
    assert checks["launch-agent:worker:env:XAI_API_KEY"].detail == "placeholder value in launchd environment"


def test_installed_worker_adapter_api_environment_reads_launch_agent_keys(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    plist_path = tmp_path / "com.dialectical.worker.plist"
    with plist_path.open("wb") as file:
        plistlib.dump(
            {
                "EnvironmentVariables": {
                    "GEMINI_API_KEY": "gemini-secret",
                    "XAI_API_KEY": "xai-secret",
                    "PATH": "/usr/bin:/bin",
                },
            },
            file,
        )
    module.INSTALLED_AGENT_SPECS["worker"] = {
        **module.INSTALLED_AGENT_SPECS["worker"],
        "path": plist_path,
    }

    assert module.installed_worker_adapter_api_environment() == {
        "GEMINI_API_KEY": "gemini-secret",
        "XAI_API_KEY": "xai-secret",
    }


def test_required_worker_api_key_checks_pass_when_launchd_has_required_key(monkeypatch) -> None:
    module = load_deployment_preflight_module()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    checks = checks_by_name(
        module.required_worker_api_key_checks(
            "codex-gpt-5.5,gemini-2.5-flash",
            {"GEMINI_API_KEY": "gemini-secret"},
        )
    )

    assert checks["worker-api-key:gemini-2.5-flash"].status == "PASS"
    assert checks["worker-api-key:gemini-2.5-flash"].detail == "GEMINI_API_KEY is set in worker launchd environment"


def test_required_worker_api_key_checks_fail_when_key_is_only_in_shell(monkeypatch) -> None:
    module = load_deployment_preflight_module()
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")

    checks = checks_by_name(module.required_worker_api_key_checks("gemini-2.5-flash", {}))

    assert checks["worker-api-key:gemini-2.5-flash"].status == "FAIL"
    assert "set in the shell but not in the installed worker launchd environment" in checks[
        "worker-api-key:gemini-2.5-flash"
    ].detail


def test_required_worker_api_key_checks_fail_when_required_key_is_missing(monkeypatch) -> None:
    module = load_deployment_preflight_module()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    checks = checks_by_name(module.required_worker_api_key_checks("gemini-2.5-flash,grok-4", {}))

    assert checks["worker-api-key:gemini-2.5-flash"].status == "FAIL"
    assert "GEMINI_API_KEY is not set in the installed worker launchd environment" in checks[
        "worker-api-key:gemini-2.5-flash"
    ].detail
    assert checks["worker-api-key:grok-4"].status == "FAIL"
    assert "XAI_API_KEY is not set in the installed worker launchd environment" in checks[
        "worker-api-key:grok-4"
    ].detail


def test_cloudflared_launch_agent_checks_match_config_path_and_tunnel(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    credentials = tmp_path / "tunnel.json"
    credentials.write_text(VALID_CREDENTIALS)
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text(
        "\n".join(
            [
                "tunnel: dialectical-prod",
                f"credentials-file: {credentials}",
                "ingress:",
                "  - hostname: debate.example.com",
                "    service: http://localhost:3000",
                "  - service: http_status:404",
                "",
            ]
        )
    )
    plist_path = tmp_path / "com.dialectical.cloudflared.plist"
    with plist_path.open("wb") as file:
        plistlib.dump(
            {
                "ProgramArguments": [
                    "/opt/homebrew/bin/cloudflared",
                    "tunnel",
                    "--config",
                    str(module.CLOUDFLARED_CONFIG),
                    "run",
                    "dialectical-prod",
                ],
            },
            file,
        )

    checks = checks_by_name(
        module.installed_launch_agent_checks(
            "cloudflared",
            {"path": plist_path, "required_args": ["tunnel", "run"]},
            required=True,
        )
    )

    assert checks["launch-agent:cloudflared:config"].status == "PASS"
    assert checks["launch-agent:cloudflared:config"].detail == str(module.CLOUDFLARED_CONFIG)
    assert checks["launch-agent:cloudflared:tunnel"].status == "PASS"
    assert checks["launch-agent:cloudflared:tunnel"].detail == "dialectical-prod"


def test_cloudflared_launch_agent_checks_reject_wrong_config_path(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text("tunnel: dialectical-prod\n")
    plist_path = tmp_path / "com.dialectical.cloudflared.plist"
    with plist_path.open("wb") as file:
        plistlib.dump(
            {
                "ProgramArguments": [
                    "/opt/homebrew/bin/cloudflared",
                    "tunnel",
                    "--config",
                    str(tmp_path / "other.yml"),
                    "run",
                    "dialectical-prod",
                ],
            },
            file,
        )

    checks = checks_by_name(
        module.installed_launch_agent_checks(
            "cloudflared",
            {"path": plist_path, "required_args": ["tunnel", "run"]},
            required=True,
        )
    )

    assert checks["launch-agent:cloudflared:config"].status == "FAIL"
    assert f"expected {module.CLOUDFLARED_CONFIG}" in checks["launch-agent:cloudflared:config"].detail


def test_cloudflared_launch_agent_checks_reject_tunnel_mismatch(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text("tunnel: dialectical-prod\n")
    plist_path = tmp_path / "com.dialectical.cloudflared.plist"
    with plist_path.open("wb") as file:
        plistlib.dump(
            {
                "ProgramArguments": [
                    "/opt/homebrew/bin/cloudflared",
                    "tunnel",
                    "--config",
                    str(module.CLOUDFLARED_CONFIG),
                    "run",
                    "other-tunnel",
                ],
            },
            file,
        )

    checks = checks_by_name(
        module.installed_launch_agent_checks(
            "cloudflared",
            {"path": plist_path, "required_args": ["tunnel", "run"]},
            required=True,
        )
    )

    assert checks["launch-agent:cloudflared:tunnel"].status == "FAIL"
    assert "does not match config tunnel dialectical-prod" in checks["launch-agent:cloudflared:tunnel"].detail


def test_cloudflared_config_checks_validate_named_tunnel_ingress(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    credentials = tmp_path / "tunnel.json"
    credentials.write_text(VALID_CREDENTIALS)
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text(
        "\n".join(
            [
                "tunnel: dialectical",
                f"credentials-file: {credentials}",
                "ingress:",
                "  - hostname: debate.example.com",
                "    path: /api/*",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    path: /healthz",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    service: http://localhost:3000",
                "  - service: http_status:404",
                "",
            ]
        )
    )

    checks = checks_by_name(module.cloudflared_config_checks(required=True))

    assert checks["cloudflared-config"].status == "PASS"
    assert checks["cloudflared-config:tunnel"].status == "PASS"
    assert checks["cloudflared-config:credentials-file"].status == "PASS"
    assert checks["cloudflared-config:ingress"].status == "PASS"
    assert checks["cloudflared-config:ingress"].detail == "debate.example.com"


def test_cloudflared_credentials_checks_report_missing_directory(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.CLOUDFLARED_HOME = tmp_path / ".cloudflared"

    checks = checks_by_name(module.cloudflared_credentials_checks(required=True))

    assert checks["cloudflared-credentials"].status == "FAIL"
    assert f"directory missing: {module.CLOUDFLARED_HOME}" in checks["cloudflared-credentials"].detail


def test_cloudflared_credentials_checks_report_valid_credentials(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.CLOUDFLARED_HOME = tmp_path / ".cloudflared"
    module.CLOUDFLARED_HOME.mkdir()
    (module.CLOUDFLARED_HOME / "valid.json").write_text(VALID_CREDENTIALS)
    (module.CLOUDFLARED_HOME / "invalid.json").write_text('{"AccountTag":"account-tag"}')

    checks = checks_by_name(module.cloudflared_credentials_checks(required=True))

    assert checks["cloudflared-credentials"].status == "PASS"
    assert checks["cloudflared-credentials"].detail == "valid.json"


def test_cloudflared_credentials_checks_report_ambiguous_credentials(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.CLOUDFLARED_HOME = tmp_path / ".cloudflared"
    module.CLOUDFLARED_HOME.mkdir()
    (module.CLOUDFLARED_HOME / "first.json").write_text(VALID_CREDENTIALS)
    (module.CLOUDFLARED_HOME / "second.json").write_text(VALID_CREDENTIALS)

    checks = checks_by_name(module.cloudflared_credentials_checks(required=True))

    assert checks["cloudflared-credentials"].status == "FAIL"
    assert checks["cloudflared-credentials"].detail == (
        "multiple valid tunnel credentials JSON files: first.json, second.json; "
        "set CLOUDFLARED_CREDENTIALS explicitly"
    )


def test_cloudflared_config_checks_fail_placeholders_and_missing_routes(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text(
        "\n".join(
            [
                "tunnel: <tunnel-name>",
                "credentials-file: /Users/<you>/.cloudflared/<tunnel-id>.json",
                "ingress:",
                "  - hostname: debate.<your-domain>",
                "    path: /api/*",
                "    service: http://localhost:8000",
                "  - service: http_status:404",
                "",
            ]
        )
    )

    checks = checks_by_name(module.cloudflared_config_checks(required=True))

    assert checks["cloudflared-config"].status == "PASS"
    assert checks["cloudflared-config:tunnel"].status == "FAIL"
    assert checks["cloudflared-config:credentials-file"].status == "FAIL"
    assert checks["cloudflared-config:ingress"].status == "FAIL"
    assert "placeholder hostnames" in checks["cloudflared-config:ingress"].detail


def test_cloudflared_config_checks_reject_invalid_tunnel_name(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    credentials = tmp_path / "tunnel.json"
    credentials.write_text(VALID_CREDENTIALS)
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text(
        "\n".join(
            [
                "tunnel: https://example.com/tunnel",
                f"credentials-file: {credentials}",
                "ingress:",
                "  - hostname: debate.example.com",
                "    path: /api/*",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    path: /healthz",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    service: http://localhost:3000",
                "  - service: http_status:404",
                "",
            ]
        )
    )

    checks = checks_by_name(module.cloudflared_config_checks(required=True))

    assert checks["cloudflared-config:tunnel"].status == "FAIL"
    assert "invalid tunnel name" in checks["cloudflared-config:tunnel"].detail


def test_cloudflared_config_checks_reject_quick_tunnel_hostname(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    credentials = tmp_path / "tunnel.json"
    credentials.write_text(VALID_CREDENTIALS)
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text(
        "\n".join(
            [
                "tunnel: dialectical",
                f"credentials-file: {credentials}",
                "ingress:",
                "  - hostname: evaluations-postage-proceed-happiness.trycloudflare.com",
                "    path: /api/*",
                "    service: http://localhost:8000",
                "  - hostname: evaluations-postage-proceed-happiness.trycloudflare.com",
                "    path: /healthz",
                "    service: http://localhost:8000",
                "  - hostname: evaluations-postage-proceed-happiness.trycloudflare.com",
                "    service: http://localhost:3000",
                "  - service: http_status:404",
                "",
            ]
        )
    )

    checks = checks_by_name(module.cloudflared_config_checks(required=True))

    assert checks["cloudflared-config:ingress"].status == "FAIL"
    assert "trycloudflare.com quick tunnel" in checks["cloudflared-config:ingress"].detail


def test_cloudflared_config_checks_warn_for_missing_credentials_before_install(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text(
        "\n".join(
            [
                "tunnel: dialectical",
                f"credentials-file: {tmp_path / 'missing.json'}",
                "ingress:",
                "  - hostname: debate.example.com",
                "    path: /api/*",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    path: /healthz",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    service: http://localhost:3000",
                "  - service: http_status:404",
                "",
            ]
        )
    )

    checks = checks_by_name(module.cloudflared_config_checks(required=False))

    assert checks["cloudflared-config:credentials-file"].status == "WARN"


def test_cloudflared_config_checks_fail_malformed_credentials(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    credentials = tmp_path / "tunnel.json"
    credentials.write_text('{"AccountTag":"account-tag"}')
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text(
        "\n".join(
            [
                "tunnel: dialectical",
                f"credentials-file: {credentials}",
                "ingress:",
                "  - hostname: debate.example.com",
                "    path: /api/*",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    path: /healthz",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    service: http://localhost:3000",
                "  - service: http_status:404",
                "",
            ]
        )
    )

    checks = checks_by_name(module.cloudflared_config_checks(required=True))

    assert checks["cloudflared-config:credentials-file"].status == "FAIL"
    assert "missing required keys: TunnelID, TunnelSecret" in checks["cloudflared-config:credentials-file"].detail


def test_cloudflared_config_checks_fail_non_uuid_tunnel_id(tmp_path: Path) -> None:
    module = load_deployment_preflight_module()
    credentials = tmp_path / "tunnel.json"
    credentials.write_text('{"AccountTag":"account-tag","TunnelID":"not-a-uuid","TunnelSecret":"secret"}')
    module.CLOUDFLARED_CONFIG = tmp_path / "config.yml"
    module.CLOUDFLARED_CONFIG.write_text(
        "\n".join(
            [
                "tunnel: dialectical",
                f"credentials-file: {credentials}",
                "ingress:",
                "  - hostname: debate.example.com",
                "    path: /api/*",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    path: /healthz",
                "    service: http://localhost:8000",
                "  - hostname: debate.example.com",
                "    service: http://localhost:3000",
                "  - service: http_status:404",
                "",
            ]
        )
    )

    checks = checks_by_name(module.cloudflared_config_checks(required=True))

    assert checks["cloudflared-config:credentials-file"].status == "FAIL"
    assert "TunnelID is not a UUID" in checks["cloudflared-config:credentials-file"].detail


def test_ollama_capability_id_matches_worker_adapter_normalization() -> None:
    module = load_deployment_preflight_module()

    assert module.ollama_capability_id("qwen-3.6:latest") == "ollama:qwen-3.6"
    assert module.ollama_capability_id("gemma-4-9b") == "ollama:gemma-4-9b"


def test_real_adapter_checks_report_normalized_ollama_capabilities(monkeypatch) -> None:
    module = load_deployment_preflight_module()
    monkeypatch.setattr(module.shutil, "which", lambda command: None)
    monkeypatch.setattr(module, "ollama_models", lambda: ["qwen-3.6:latest", "qwen-3.6:Q4", "gemma-4-9b"])
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    checks = checks_by_name(module.real_adapter_checks(allow_no_real_adapters=False))

    assert checks["adapter-service:ollama"].status == "PASS"
    assert checks["adapter-service:ollama"].detail == "qwen-3.6:latest, qwen-3.6:Q4, gemma-4-9b"
    assert checks["real-adapter-invocation"].status == "PASS"
    assert checks["real-adapter-invocation"].detail.startswith("ollama:gemma-4-9b, ollama:qwen-3.6;")
    assert "ollama:qwen-3.6:latest" not in checks["real-adapter-invocation"].detail


class FakeRunResult:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_real_adapter_checks_accept_grok_cli_prompt_mode(monkeypatch) -> None:
    module = load_deployment_preflight_module()
    monkeypatch.setattr(module.shutil, "which", lambda command: "/usr/local/bin/grok" if command == "grok" else None)
    monkeypatch.setattr(module, "ollama_models", lambda: [])
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: FakeRunResult("Usage: grok [options]\n  -p, --prompt <prompt>\n"),
    )
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    checks = checks_by_name(module.real_adapter_checks(allow_no_real_adapters=False))

    assert checks["adapter-command:grok-4"].status == "PASS"
    assert "supports -p prompt mode" in checks["adapter-command:grok-4"].detail
    assert checks["real-adapter-invocation"].status == "PASS"
    assert checks["real-adapter-invocation"].detail.startswith("grok-4;")


def test_real_adapter_checks_do_not_count_grok_cli_without_prompt_mode(monkeypatch) -> None:
    module = load_deployment_preflight_module()
    monkeypatch.setattr(module.shutil, "which", lambda command: "/usr/local/bin/grok" if command == "grok" else None)
    monkeypatch.setattr(module, "ollama_models", lambda: [])
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: FakeRunResult("Usage: grok [options]\n  --chat\n"))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    checks = checks_by_name(module.real_adapter_checks(allow_no_real_adapters=False))

    assert checks["adapter-command:grok-4"].status == "WARN"
    assert "does not advertise noninteractive" in checks["adapter-command:grok-4"].detail
    assert checks["adapter-auth:grok-4"].status == "WARN"
    assert "XAI_API_KEY" in checks["adapter-auth:grok-4"].detail
    assert checks["real-adapter-invocation"].status == "FAIL"


def test_real_adapter_checks_count_gemini_api_key(monkeypatch) -> None:
    module = load_deployment_preflight_module()
    monkeypatch.setattr(module.shutil, "which", lambda command: None)
    monkeypatch.setattr(module, "ollama_models", lambda: [])
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")

    checks = checks_by_name(module.real_adapter_checks(allow_no_real_adapters=False))

    assert checks["adapter-credential:gemini-api"].status == "PASS"
    assert checks["adapter-auth:gemini-api"].status == "WARN"
    assert checks["real-adapter-invocation"].status == "PASS"
    assert checks["real-adapter-invocation"].detail.startswith("gemini-2.5-flash;")


def test_real_adapter_checks_count_launchd_api_keys_when_shell_env_is_absent(monkeypatch) -> None:
    module = load_deployment_preflight_module()
    monkeypatch.setattr(module.shutil, "which", lambda command: None)
    monkeypatch.setattr(module, "ollama_models", lambda: [])
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    checks = checks_by_name(
        module.real_adapter_checks(
            allow_no_real_adapters=False,
            adapter_api_env={"GEMINI_API_KEY": "gemini-test", "XAI_API_KEY": "xai-test"},
        )
    )

    assert checks["adapter-credential:gemini-api"].status == "PASS"
    assert checks["adapter-credential:gemini-api"].detail == "GEMINI_API_KEY is set in worker launchd environment"
    assert checks["adapter-credential:xai-api"].status == "PASS"
    assert checks["adapter-credential:xai-api"].detail == "XAI_API_KEY is set in worker launchd environment"
    assert checks["real-adapter-invocation"].status == "PASS"
    assert checks["real-adapter-invocation"].detail.startswith("gemini-2.5-flash, grok-4;")


def test_real_adapter_checks_ignore_placeholder_api_keys(monkeypatch) -> None:
    module = load_deployment_preflight_module()
    monkeypatch.setattr(module.shutil, "which", lambda command: None)
    monkeypatch.setattr(module, "ollama_models", lambda: [])
    monkeypatch.setenv("GEMINI_API_KEY", "<optional-google-ai-studio-api-key>")
    monkeypatch.setenv("XAI_API_KEY", "<optional-xai-api-key>")

    checks = checks_by_name(
        module.real_adapter_checks(
            allow_no_real_adapters=False,
            adapter_api_env={"GEMINI_API_KEY": "<optional-google-ai-studio-api-key>", "XAI_API_KEY": "<optional-xai-api-key>"},
        )
    )

    assert checks["adapter-credential:gemini-api"].status == "WARN"
    assert checks["adapter-credential:gemini-api"].detail == "GEMINI_API_KEY is not set to a real value"
    assert checks["adapter-credential:xai-api"].status == "WARN"
    assert checks["adapter-credential:xai-api"].detail == "XAI_API_KEY is not set to a real value"
    assert checks["real-adapter-invocation"].status == "FAIL"
