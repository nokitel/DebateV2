from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - deploy target is 3.12+.
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
WORKER_CONFIG = Path("~/.dialectical-worker/config.toml").expanduser()
CLOUDFLARED_HOME = Path("~/.cloudflared").expanduser()
CLOUDFLARED_CONFIG = Path("~/.cloudflared/config.yml").expanduser()
LAUNCH_AGENTS = Path("~/Library/LaunchAgents").expanduser()
REQUIRED_CLOUDFLARED_INGRESS = (
    {"path": "/api/*", "service": "http://localhost:8000"},
    {"path": "/healthz", "service": "http://localhost:8000"},
    {"path": "", "service": "http://localhost:3000"},
)
REQUIRED_CLOUDFLARED_CREDENTIAL_KEYS = ("AccountTag", "TunnelID", "TunnelSecret")
GROK_PROMPT_FLAG_PATTERN = re.compile(r"(?<!\S)(?:-p|--prompt)(?:[=\s,]|$)")
ADAPTER_API_ENV_VARS = ("GEMINI_API_KEY", "XAI_API_KEY")
API_KEY_MODEL_REQUIREMENTS = {
    "gemini-2.5-flash": "GEMINI_API_KEY",
    "grok-4": "XAI_API_KEY",
}
INSTALLED_AGENT_SPECS = {
    "coordinator": {
        "path": LAUNCH_AGENTS / "com.dialectical.coordinator.plist",
        "working_directory": ROOT / "coordinator",
        "required_args": ["-m", "uvicorn", "app.main:app", "--port", "8000"],
    },
    "web": {
        "path": LAUNCH_AGENTS / "com.dialectical.web.plist",
        "working_directory": ROOT,
        "required_args": [str(ROOT / "scripts" / "web_proxy.py"), "--root", str(ROOT)],
    },
    "worker": {
        "path": LAUNCH_AGENTS / "com.dialectical.worker.plist",
        "working_directory": ROOT / "worker",
        "required_args": ["-m", "app.main"],
    },
    "cloudflared": {
        "path": LAUNCH_AGENTS / "com.dialectical.cloudflared.plist",
        "required_args": ["tunnel", "run"],
    },
}


@dataclass(frozen=True)
class Check:
    status: str
    name: str
    detail: str


def pass_check(name: str, detail: str) -> Check:
    return Check("PASS", name, detail)


def warn_check(name: str, detail: str) -> Check:
    return Check("WARN", name, detail)


def fail_check(name: str, detail: str) -> Check:
    return Check("FAIL", name, detail)


def command_check(command: str, required: bool = True) -> Check:
    path = shutil.which(command)
    if path:
        return pass_check(f"command:{command}", path)
    status = fail_check if required else warn_check
    return status(f"command:{command}", "not found on PATH")


def file_check(path: Path, name: str, required: bool = True) -> Check:
    if path.exists():
        return pass_check(name, str(path))
    status = fail_check if required else warn_check
    return status(name, f"missing: {path}")


def has_placeholder(value: str) -> bool:
    return "<" in value or ">" in value or "debate.<your-domain>" in value


def adapter_api_value_is_configured(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not has_placeholder(value)


HOSTNAME_RE = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
    re.IGNORECASE,
)
TUNNEL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def hostname_issue(value: str) -> str | None:
    hostname = value.strip().rstrip(".").lower()
    if not hostname:
        return "empty hostname"
    if has_placeholder(value):
        return "placeholder hostname"
    if "://" in hostname or any(character in hostname for character in "/?#:"):
        return "not a DNS hostname"
    if hostname == "trycloudflare.com" or hostname.endswith(".trycloudflare.com"):
        return "trycloudflare.com quick tunnel"
    if not HOSTNAME_RE.fullmatch(hostname):
        return "invalid DNS hostname"
    return None


def tunnel_name_issue(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return "empty tunnel name"
    if has_placeholder(value):
        return "placeholder tunnel name"
    if "://" in cleaned or any(character in cleaned for character in "/?#:"):
        return "not a Cloudflare tunnel name or UUID"
    if not TUNNEL_NAME_RE.fullmatch(cleaned):
        return "invalid tunnel name"
    return None


def load_plist(path: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        with path.open("rb") as file:
            payload = plistlib.load(file)
    except (OSError, plistlib.InvalidFileException) as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "plist root is not a dictionary"
    return payload, None


def installed_launch_agent_checks(name: str, spec: dict[str, object], required: bool) -> list[Check]:
    path = spec["path"]
    assert isinstance(path, Path)
    checks = [file_check(path, f"launch-agent:{path.name}", required=required)]
    if not path.exists():
        return checks

    payload, error = load_plist(path)
    if payload is None:
        checks.append(fail_check(f"launch-agent:{name}:plist", error or "invalid plist"))
        return checks

    arguments = payload.get("ProgramArguments")
    if not isinstance(arguments, list) or not all(isinstance(arg, str) for arg in arguments):
        checks.append(fail_check(f"launch-agent:{name}:program", "ProgramArguments is missing or invalid"))
        return checks

    required_args = spec.get("required_args", [])
    assert isinstance(required_args, list)
    missing = [arg for arg in required_args if isinstance(arg, str) and arg not in arguments]
    if missing:
        checks.append(
            fail_check(
                f"launch-agent:{name}:program",
                f"missing expected arguments: {', '.join(missing)}",
            )
        )
    elif any("<" in arg or ">" in arg or "__" in arg for arg in arguments):
        checks.append(fail_check(f"launch-agent:{name}:program", "contains unresolved placeholders"))
    else:
        checks.append(pass_check(f"launch-agent:{name}:program", "ProgramArguments match source deploy template"))

    working_directory = spec.get("working_directory")
    if isinstance(working_directory, Path):
        actual = payload.get("WorkingDirectory")
        if actual == str(working_directory):
            checks.append(pass_check(f"launch-agent:{name}:working-directory", actual))
        else:
            checks.append(
                fail_check(
                    f"launch-agent:{name}:working-directory",
                    f"expected {working_directory}, found {actual or 'missing'}",
                )
            )

    if name == "worker":
        environment = payload.get("EnvironmentVariables")
        if not isinstance(environment, dict):
            checks.append(warn_check("launch-agent:worker:env", "EnvironmentVariables is missing or invalid"))
        else:
            for variable in ADAPTER_API_ENV_VARS:
                value = environment.get(variable)
                if adapter_api_value_is_configured(value):
                    checks.append(pass_check(f"launch-agent:worker:env:{variable}", "set"))
                elif isinstance(value, str) and value.strip():
                    checks.append(warn_check(f"launch-agent:worker:env:{variable}", "placeholder value in launchd environment"))
                else:
                    checks.append(warn_check(f"launch-agent:worker:env:{variable}", "not set in launchd environment"))

    if name == "cloudflared":
        checks.extend(cloudflared_launch_agent_config_checks(arguments))

    return checks


def cloudflared_launch_agent_config_checks(arguments: list[str]) -> list[Check]:
    checks: list[Check] = []

    try:
        config_index = arguments.index("--config")
    except ValueError:
        checks.append(fail_check("launch-agent:cloudflared:config", "missing --config argument"))
    else:
        if config_index + 1 >= len(arguments):
            checks.append(fail_check("launch-agent:cloudflared:config", "missing value after --config"))
        else:
            config_value = arguments[config_index + 1]
            if has_placeholder(config_value) or "__" in config_value:
                checks.append(fail_check("launch-agent:cloudflared:config", "contains unresolved placeholder"))
            else:
                configured_path = Path(config_value).expanduser()
                if configured_path != CLOUDFLARED_CONFIG:
                    checks.append(
                        fail_check(
                            "launch-agent:cloudflared:config",
                            f"expected {CLOUDFLARED_CONFIG}, found {configured_path}",
                        )
                    )
                else:
                    checks.append(pass_check("launch-agent:cloudflared:config", str(configured_path)))

    try:
        run_index = len(arguments) - 1 - arguments[::-1].index("run")
    except ValueError:
        checks.append(fail_check("launch-agent:cloudflared:tunnel", "missing tunnel run argument"))
        return checks

    if run_index + 1 >= len(arguments) or arguments[run_index + 1].startswith("-"):
        checks.append(fail_check("launch-agent:cloudflared:tunnel", "missing tunnel name after run"))
        return checks

    tunnel = arguments[run_index + 1].strip()
    if has_placeholder(tunnel) or "__" in tunnel:
        checks.append(fail_check("launch-agent:cloudflared:tunnel", "contains unresolved placeholder"))
        return checks
    if issue := tunnel_name_issue(tunnel):
        checks.append(fail_check("launch-agent:cloudflared:tunnel", f"invalid tunnel name: {issue}"))
        return checks

    if CLOUDFLARED_CONFIG.exists():
        try:
            top_level, _ingress = parse_cloudflared_config(CLOUDFLARED_CONFIG.read_text())
        except OSError as exc:
            checks.append(fail_check("launch-agent:cloudflared:tunnel", f"cannot read config: {exc}"))
            return checks
        config_tunnel = top_level.get("tunnel", "").strip()
        if config_tunnel and tunnel != config_tunnel:
            checks.append(
                fail_check(
                    "launch-agent:cloudflared:tunnel",
                    f"launchd tunnel {tunnel} does not match config tunnel {config_tunnel}",
                )
            )
            return checks

    checks.append(pass_check("launch-agent:cloudflared:tunnel", tunnel))
    return checks


def installed_worker_adapter_api_environment() -> dict[str, str]:
    spec = INSTALLED_AGENT_SPECS["worker"]
    path = spec["path"]
    assert isinstance(path, Path)
    if not path.exists():
        return {}
    payload, error = load_plist(path)
    if payload is None:
        return {}
    environment = payload.get("EnvironmentVariables")
    if not isinstance(environment, dict):
        return {}
    return {
        variable: value
        for variable in ADAPTER_API_ENV_VARS
        if adapter_api_value_is_configured(value := environment.get(variable))
    }


def python_version_check() -> Check:
    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 12):
        return pass_check("python>=3.12", current)
    return fail_check("python>=3.12", f"{current}; deploy target requires Python 3.12+")


def python_stdlib_check() -> Check:
    try:
        import pyexpat
    except ImportError as exc:
        return fail_check("python-stdlib:pyexpat", str(exc))
    return pass_check("python-stdlib:pyexpat", pyexpat.EXPAT_VERSION)


def macos_check() -> Check:
    system = platform.system()
    if system == "Darwin":
        return pass_check("platform:macos", platform.platform())
    return fail_check("platform:macos", f"{system}; goal topology is Mac mini + adesso MacBook")


def template_checks() -> list[Check]:
    paths = [
        ROOT / "deploy" / "launchd" / "coordinator.plist",
        ROOT / "deploy" / "launchd" / "web.plist",
        ROOT / "deploy" / "launchd" / "worker.plist",
        ROOT / "deploy" / "launchd" / "cloudflared.plist",
        ROOT / "deploy" / "cloudflared.config.yml",
    ]
    return [file_check(path, f"template:{path.relative_to(ROOT)}") for path in paths]


def launch_agent_checks(require_installed: bool, names: list[str]) -> list[Check]:
    checks: list[Check] = []
    for name in names:
        spec = INSTALLED_AGENT_SPECS[name]
        checks.extend(installed_launch_agent_checks(name, spec, require_installed))
    return checks


def unquote_config_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_cloudflared_config(text: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    top_level: dict[str, str] = {}
    ingress: list[dict[str, str]] = []
    in_ingress = False
    current: dict[str, str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped == "ingress:":
            in_ingress = True
            continue
        if not in_ingress:
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                top_level[key.strip()] = unquote_config_value(value)
            continue

        if stripped.startswith("- "):
            current = {}
            ingress.append(current)
            stripped = stripped[2:].strip()
        if current is None or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        current[key.strip()] = unquote_config_value(value)

    return top_level, ingress


def cloudflare_credentials_file_issue(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return f"unreadable ({type(exc).__name__}: {exc})"
    except json.JSONDecodeError as exc:
        return f"invalid JSON ({exc.msg})"
    if not isinstance(payload, dict):
        return "not a JSON object"
    missing = [
        key
        for key in REQUIRED_CLOUDFLARED_CREDENTIAL_KEYS
        if not isinstance(payload.get(key), str) or not payload.get(key, "").strip()
    ]
    if missing:
        return "missing required keys: " + ", ".join(missing)
    placeholders = [
        key
        for key in REQUIRED_CLOUDFLARED_CREDENTIAL_KEYS
        if has_placeholder(str(payload.get(key, "")))
    ]
    if placeholders:
        return "contains placeholder values: " + ", ".join(placeholders)
    try:
        UUID(str(payload["TunnelID"]).strip())
    except ValueError:
        return "TunnelID is not a UUID"
    return None


def cloudflared_credentials_checks(required: bool) -> list[Check]:
    status = fail_check if required else warn_check
    if not CLOUDFLARED_HOME.exists():
        return [status("cloudflared-credentials", f"directory missing: {CLOUDFLARED_HOME}")]
    if not CLOUDFLARED_HOME.is_dir():
        return [fail_check("cloudflared-credentials", f"not a directory: {CLOUDFLARED_HOME}")]
    candidates = sorted(path for path in CLOUDFLARED_HOME.glob("*.json") if path.is_file())
    if not candidates:
        return [status("cloudflared-credentials", f"no tunnel credentials JSON files in {CLOUDFLARED_HOME}")]

    valid: list[Path] = []
    invalid: list[str] = []
    for candidate in candidates:
        if issue := cloudflare_credentials_file_issue(candidate):
            invalid.append(f"{candidate.name}: {issue}")
        else:
            valid.append(candidate)
    if len(valid) == 1:
        return [pass_check("cloudflared-credentials", valid[0].name)]
    if valid:
        detail = ", ".join(path.name for path in valid)
        return [
            status(
                "cloudflared-credentials",
                f"multiple valid tunnel credentials JSON files: {detail}; set CLOUDFLARED_CREDENTIALS explicitly",
            )
        ]
    return [status("cloudflared-credentials", "; ".join(invalid))]


def cloudflared_config_checks(required: bool) -> list[Check]:
    if not CLOUDFLARED_CONFIG.exists():
        status = fail_check if required else warn_check
        return [status("cloudflared-config", f"missing: {CLOUDFLARED_CONFIG}")]
    text = CLOUDFLARED_CONFIG.read_text()
    checks = [pass_check("cloudflared-config", str(CLOUDFLARED_CONFIG))]
    top_level, ingress = parse_cloudflared_config(text)

    tunnel = top_level.get("tunnel", "").strip()
    if not tunnel:
        checks.append(fail_check("cloudflared-config:tunnel", "missing tunnel name"))
    elif has_placeholder(tunnel):
        checks.append(fail_check("cloudflared-config:tunnel", f"contains placeholder: {tunnel}"))
    elif issue := tunnel_name_issue(tunnel):
        checks.append(fail_check("cloudflared-config:tunnel", f"invalid tunnel name: {issue}"))
    else:
        checks.append(pass_check("cloudflared-config:tunnel", tunnel))

    credentials_value = top_level.get("credentials-file", "").strip()
    if not credentials_value:
        checks.append(fail_check("cloudflared-config:credentials-file", "missing credentials-file"))
    elif has_placeholder(credentials_value):
        checks.append(fail_check("cloudflared-config:credentials-file", f"contains placeholder: {credentials_value}"))
    else:
        credentials_path = Path(credentials_value).expanduser()
        if credentials_path.exists():
            if issue := cloudflare_credentials_file_issue(credentials_path):
                checks.append(fail_check("cloudflared-config:credentials-file", f"{credentials_path}: {issue}"))
            else:
                checks.append(pass_check("cloudflared-config:credentials-file", str(credentials_path)))
        else:
            status = fail_check if required else warn_check
            checks.append(status("cloudflared-config:credentials-file", f"missing: {credentials_path}"))

    hostnames = sorted({entry.get("hostname", "").strip() for entry in ingress if entry.get("hostname", "").strip()})
    concrete_hostnames = [hostname for hostname in hostnames if not has_placeholder(hostname)]
    if any(has_placeholder(hostname) for hostname in hostnames):
        checks.append(
            fail_check(
                "cloudflared-config:ingress",
                f"contains placeholder hostnames: {', '.join(hostnames)}",
            )
        )
    elif invalid_hostnames := [f"{hostname} ({issue})" for hostname in hostnames if (issue := hostname_issue(hostname))]:
        checks.append(
            fail_check(
                "cloudflared-config:ingress",
                f"invalid hostnames: {', '.join(invalid_hostnames)}",
            )
        )
    elif not concrete_hostnames:
        checks.append(fail_check("cloudflared-config:ingress", "no concrete hostname ingress entries"))
    else:
        missing_routes: list[str] = []
        hostname_set = set(concrete_hostnames)
        for required_route in REQUIRED_CLOUDFLARED_INGRESS:
            path = required_route["path"]
            service = required_route["service"]
            if not any(
                entry.get("hostname", "").strip() in hostname_set
                and entry.get("path", "").strip() == path
                and entry.get("service", "").strip() == service
                for entry in ingress
            ):
                route_name = f"{path or '<web>'}->{service}"
                missing_routes.append(route_name)
        if not any(entry.get("service", "").strip() == "http_status:404" for entry in ingress):
            missing_routes.append("<fallback>->http_status:404")
        if missing_routes:
            checks.append(fail_check("cloudflared-config:ingress", f"missing routes: {', '.join(missing_routes)}"))
        else:
            checks.append(pass_check("cloudflared-config:ingress", f"{', '.join(concrete_hostnames)}"))
    return checks


def web_build_check() -> Check:
    build_manifest = ROOT / "web" / ".next" / "build-manifest.json"
    return file_check(build_manifest, "web-build", required=False)


def parse_model_list(value: object) -> list[str]:
    if value is None:
        return []
    candidates = value.split(",") if isinstance(value, str) else value if isinstance(value, list) else [value]
    models: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        model = str(candidate).strip()
        if not model or model in seen:
            continue
        models.append(model)
        seen.add(model)
    return models


def required_worker_api_key_checks(required_models: object, adapter_api_env: dict[str, str]) -> list[Check]:
    checks: list[Check] = []
    for model in parse_model_list(required_models):
        variable = API_KEY_MODEL_REQUIREMENTS.get(model)
        if variable is None:
            continue
        name = f"worker-api-key:{model}"
        if adapter_api_value_is_configured(adapter_api_env.get(variable)):
            checks.append(pass_check(name, f"{variable} is set in worker launchd environment"))
        elif adapter_api_value_is_configured(os.getenv(variable)):
            checks.append(
                fail_check(
                    name,
                    f"{variable} is set in the shell but not in the installed worker launchd environment; "
                    f"rerun make install-worker with {variable} present",
                )
            )
        else:
            checks.append(
                fail_check(
                    name,
                    f"{variable} is not set in the installed worker launchd environment; "
                    f"rerun make install-worker with {variable} present",
                )
            )
    return checks


def worker_config_checks(require_registered: bool) -> list[Check]:
    if not WORKER_CONFIG.exists():
        status = fail_check if require_registered else warn_check
        return [status("worker-config", f"missing: {WORKER_CONFIG}")]
    text = WORKER_CONFIG.read_text()
    checks = [pass_check("worker-config", str(WORKER_CONFIG))]
    if "worker_token" in text:
        checks.append(pass_check("worker-token-persisted", "worker_token key present"))
    else:
        status = fail_check if require_registered else warn_check
        checks.append(status("worker-token-persisted", "worker_token key missing"))
    if "user_token" in text:
        checks.append(fail_check("user-token-not-persisted", "user_token key is present in worker config"))
    else:
        checks.append(pass_check("user-token-not-persisted", "user_token key absent"))
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        checks.append(fail_check("worker-config-parse", f"invalid TOML: {exc}"))
        return checks
    if not isinstance(payload, dict):
        checks.append(fail_check("worker-config-parse", "root is not a table"))
        return checks
    checks.append(pass_check("worker-config-parse", "valid TOML"))

    allowed_models = parse_model_list(payload.get("allowed_models"))
    if allowed_models:
        checks.append(pass_check("worker-allowed-models", ", ".join(allowed_models)))
    else:
        checks.append(
            warn_check(
                "worker-allowed-models",
                "no allowed_models pin; worker may advertise every detected healthy adapter",
            )
        )

    if payload.get("enable_mock") is True:
        checks.append(warn_check("worker-mock-adapter", "enable_mock is true in worker config"))
    else:
        checks.append(pass_check("worker-mock-adapter", "mock adapter disabled"))

    if payload.get("enable_real_adapters", True) is False:
        checks.append(warn_check("worker-real-adapters", "enable_real_adapters is false"))
    else:
        checks.append(pass_check("worker-real-adapters", "real adapters enabled"))
    return checks


def scrub_worker_user_token(path: Path) -> bool:
    lines = path.read_text().splitlines(keepends=True)
    kept: list[str] = []
    removed = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("user_token") and stripped[len("user_token") :].lstrip().startswith("="):
            removed = True
            continue
        kept.append(line)
    if removed:
        path.write_text("".join(kept))
    return removed


def ollama_models() -> list[str]:
    request = urllib.request.Request("http://127.0.0.1:11434/api/tags")
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = json.loads(response.read().decode())
    return [str(item.get("name")) for item in payload.get("models", []) if item.get("name")]


def ollama_capability_id(model_name: str) -> str:
    return f"ollama:{model_name.split(':', 1)[0]}"


def grok_cli_prompt_flag_check(path: str) -> tuple[Check, bool]:
    try:
        result = subprocess.run(
            [path, "--help"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return warn_check("adapter-command:grok-4", f"{path}; help check failed: {exc}"), False

    help_text = f"{result.stdout}\n{result.stderr}"
    if result.returncode == 0 and GROK_PROMPT_FLAG_PATTERN.search(help_text):
        return pass_check("adapter-command:grok-4", f"{path}; supports -p prompt mode"), True
    return (
        warn_check("adapter-command:grok-4", f"{path}; does not advertise noninteractive -p/--prompt mode"),
        False,
    )


def adapter_api_credential_source(variable: str, adapter_api_env: dict[str, str]) -> str | None:
    if adapter_api_value_is_configured(os.getenv(variable)):
        return "shell environment"
    if adapter_api_value_is_configured(adapter_api_env.get(variable)):
        return "worker launchd environment"
    return None


def real_adapter_checks(allow_no_real_adapters: bool, adapter_api_env: dict[str, str] | None = None) -> list[Check]:
    checks: list[Check] = []
    detected: list[str] = []
    adapter_api_env = adapter_api_env or {}
    for command, model in (
        ("claude", "claude-sonnet-4-6"),
        ("codex", "codex-gpt-5.5"),
        ("gemini", "gemini-2.5-flash"),
        ("grok", "grok-4"),
    ):
        path = shutil.which(command)
        if path:
            if command == "grok":
                check, usable = grok_cli_prompt_flag_check(path)
                checks.append(check)
                if usable:
                    detected.append(model)
                    checks.append(
                        warn_check(
                            f"adapter-auth:{model}",
                            f"{command} command found; preflight does not run model prompts, so unattended auth is unverified",
                        )
                    )
                else:
                    checks.append(
                        warn_check(
                            f"adapter-auth:{model}",
                            "CLI prompt mode unavailable; set XAI_API_KEY to use the xAI API fallback",
                        )
                    )
                continue
            else:
                detected.append(model)
                checks.append(pass_check(f"adapter-command:{model}", path))
            checks.append(
                warn_check(
                    f"adapter-auth:{model}",
                    f"{command} command found; preflight does not run model prompts, so unattended auth is unverified",
                )
            )
        else:
            checks.append(warn_check(f"adapter-command:{model}", f"{command} not found on PATH"))

    if source := adapter_api_credential_source("XAI_API_KEY", adapter_api_env):
        detected.append("grok-4")
        checks.append(pass_check("adapter-credential:xai-api", f"XAI_API_KEY is set in {source}"))
        checks.append(warn_check("adapter-auth:xai-api", "API key is present but no model request was made"))
    else:
        checks.append(warn_check("adapter-credential:xai-api", "XAI_API_KEY is not set to a real value"))

    if source := adapter_api_credential_source("GEMINI_API_KEY", adapter_api_env):
        detected.append("gemini-2.5-flash")
        checks.append(pass_check("adapter-credential:gemini-api", f"GEMINI_API_KEY is set in {source}"))
        checks.append(warn_check("adapter-auth:gemini-api", "API key is present but no model request was made"))
    else:
        checks.append(warn_check("adapter-credential:gemini-api", "GEMINI_API_KEY is not set to a real value"))

    try:
        models = ollama_models()
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        checks.append(warn_check("adapter-service:ollama", f"localhost:11434/api/tags unavailable: {exc}"))
    else:
        ollama_detected = [model.strip() for model in models if model.strip()]
        seen_capabilities: set[str] = set()
        for model in ollama_detected:
            capability = ollama_capability_id(model)
            if capability in seen_capabilities:
                continue
            detected.append(capability)
            seen_capabilities.add(capability)
        detail = ", ".join(ollama_detected) if ollama_detected else "no pulled models"
        checks.append(
            pass_check("adapter-service:ollama", detail)
            if ollama_detected
            else warn_check("adapter-service:ollama", detail)
        )

    if detected:
        checks.append(
            pass_check(
                "real-adapter-invocation",
                f"{', '.join(sorted(set(detected)))}; auth smoke is not part of deploy-preflight",
            )
        )
    elif allow_no_real_adapters:
        checks.append(warn_check("real-adapter-invocation", "none detected; allowed by flag"))
    else:
        checks.append(fail_check("real-adapter-invocation", "no real adapters detected; production workers would be idle"))
    return checks


def run(args: argparse.Namespace) -> list[Check]:
    checks = [python_version_check(), python_stdlib_check(), macos_check(), *template_checks()]

    if args.role in {"mac-mini", "both"}:
        checks.extend(
            [
                command_check("launchctl"),
                command_check("pnpm"),
                command_check("cloudflared"),
                web_build_check(),
                *([] if CLOUDFLARED_CONFIG.exists() else cloudflared_credentials_checks(args.require_installed_services)),
                *cloudflared_config_checks(args.require_installed_services),
            ]
        )
        checks.extend(launch_agent_checks(args.require_installed_services, ["coordinator", "web", "cloudflared"]))

    if args.role in {"worker", "both"}:
        adapter_api_env = installed_worker_adapter_api_environment()
        if args.repair_worker_config and WORKER_CONFIG.exists():
            removed = scrub_worker_user_token(WORKER_CONFIG)
            detail = "removed user_token" if removed else "no user_token key found"
            checks.append(pass_check("repair-worker-config", detail))
        checks.extend(
            [
                command_check("launchctl"),
                *launch_agent_checks(args.require_installed_services, ["worker"]),
                *worker_config_checks(args.require_registered_worker),
                *required_worker_api_key_checks(args.require_worker_api_keys_for_models, adapter_api_env),
                *real_adapter_checks(args.allow_no_real_adapters, adapter_api_env),
            ]
        )

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local deployment prerequisites for Dialectical Engine")
    parser.add_argument("--role", choices=["mac-mini", "worker", "both"], default="both")
    parser.add_argument("--require-installed-services", action="store_true")
    parser.add_argument("--require-registered-worker", action="store_true")
    parser.add_argument(
        "--require-worker-api-keys-for-models",
        default="",
        help="comma-separated final model IDs whose API-backed adapters must be present in the worker launchd environment",
    )
    parser.add_argument("--allow-no-real-adapters", action="store_true")
    parser.add_argument("--repair-worker-config", action="store_true")
    args = parser.parse_args()

    checks = run(args)
    for check in checks:
        print(f"{check.status} {check.name}: {check.detail}")
    return 1 if any(check.status == "FAIL" for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
