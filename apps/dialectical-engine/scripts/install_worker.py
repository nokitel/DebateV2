from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))
ADAPTER_API_ENV_VARS = ("GEMINI_API_KEY", "XAI_API_KEY")
ADAPTER_CLI_ENV = {"GOOGLE_GENAI_USE_GCA": "true"}

from app.adapters.credentials import configured_api_key
from app.capabilities import detect_adapters
from app.client import CoordinatorClient
from app.config import WorkerConfig, load_file_config, parse_model_list, save_config

HOSTNAME_RE = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
    re.IGNORECASE,
)


def default_launchd_path() -> str:
    return f"{Path.home()}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def default_python_dyld_library_path() -> str:
    expat = Path("/opt/homebrew/opt/expat/lib")
    return str(expat) if expat.exists() else ""


def user_token() -> str:
    token = os.getenv("DIALECTICAL_USER_TOKEN") or os.getenv("USER_TOKEN")
    if token:
        return token
    if not sys.stdin.isatty():
        raise RuntimeError(
            "DIALECTICAL_USER_TOKEN or USER_TOKEN is required when registering a new worker; "
            "reruns with a matching saved worker_id and worker_token reuse that registration without a user token."
        )
    return getpass.getpass("User token: ")


def require_capabilities(capabilities: list[str], allowed_models: list[str] | None) -> None:
    if capabilities:
        return
    if allowed_models:
        allowed = ", ".join(allowed_models)
        raise RuntimeError(
            f"no healthy adapters detected for allowed models: {allowed}. "
            "Install or authenticate one of those adapters before registering this worker, "
            "or clear ALLOWED_MODELS intentionally."
        )
    raise RuntimeError(
        "no healthy adapters detected. Install or authenticate at least one real adapter, "
        "or pass --enable-mock only for local testing."
    )


def named_https_url_issue(value: str) -> str | None:
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        return "empty URL"
    if "<" in cleaned or ">" in cleaned or "debate.<your-domain>" in cleaned:
        return "placeholder URL"
    parsed = urlsplit(cleaned)
    if parsed.scheme != "https" or not parsed.netloc:
        return "must be an HTTPS URL"
    if parsed.username or parsed.password:
        return "must not include credentials"
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return "must be the coordinator origin without a path, query, or fragment"
    hostname = (parsed.hostname or "").strip().rstrip(".").lower()
    if hostname == "trycloudflare.com" or hostname.endswith(".trycloudflare.com"):
        return "must be a stable named Cloudflare hostname, not a trycloudflare.com quick tunnel"
    if not HOSTNAME_RE.fullmatch(hostname):
        return "must use a DNS hostname such as debate.example.com"
    return None


def require_named_coordinator_url(args: argparse.Namespace) -> None:
    if getattr(args, "require_named_https", False):
        if issue := named_https_url_issue(args.coordinator_url):
            raise RuntimeError(f"Invalid named coordinator URL: {issue}")


def adapter_api_environment() -> dict[str, str]:
    return {name: value for name in ADAPTER_API_ENV_VARS if (value := configured_api_key(name))}


def launchd_environment_xml(values: dict[str, str]) -> str:
    lines: list[str] = []
    for name in sorted(values):
        value = values[name]
        lines.append(f"    <key>{escape(name)}</key>")
        lines.append(f"    <string>{escape(value)}</string>")
    return "\n".join(lines)


def render_launchd_service(python_path: str, adapter_api_env: dict[str, str] | None = None) -> str:
    template = ROOT / "deploy" / "launchd" / "worker.plist"
    adapter_env = {
        **ADAPTER_CLI_ENV,
        **(adapter_api_environment() if adapter_api_env is None else adapter_api_env),
    }
    adapter_env_xml = launchd_environment_xml(adapter_env)
    return (
        template.read_text()
        .replace("__ROOT__", str(ROOT))
        .replace("__PYTHON__", python_path)
        .replace("__PATH__", default_launchd_path())
        .replace("__PYTHON_DYLD_LIBRARY_PATH__", default_python_dyld_library_path())
        .replace("__ADAPTER_API_ENV__", adapter_env_xml)
    )


def install_launchd_service(python_path: str) -> None:
    destination = Path.home() / "Library" / "LaunchAgents" / "com.dialectical.worker.plist"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_launchd_service(python_path))
    subprocess.run(["launchctl", "unload", str(destination)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "load", str(destination)], check=True)
    print(f"Installed and started launchd service: {destination}")


def same_origin(left: str, right: str) -> bool:
    return left.strip().rstrip("/") == right.strip().rstrip("/")


def existing_registration_for(coordinator_url: str, name: str) -> WorkerConfig | None:
    try:
        config = load_file_config()
    except Exception:
        return None
    if not config.worker_id or not config.worker_token:
        return None
    if config.name != name:
        return None
    if not same_origin(config.coordinator_url, coordinator_url):
        return None
    return config


async def run(args: argparse.Namespace) -> None:
    require_named_coordinator_url(args)
    existing = existing_registration_for(args.coordinator_url, args.name)
    allowed_models = parse_model_list(args.allowed_models)
    if args.allowed_models is None and existing is not None:
        allowed_models = existing.allowed_models
    config = WorkerConfig(
        coordinator_url=args.coordinator_url,
        name=args.name,
        enable_mock=args.enable_mock,
        allowed_models=allowed_models,
    )
    adapters = await detect_adapters(config)
    capabilities = sorted(adapters)
    require_capabilities(capabilities, config.allowed_models)
    if existing is not None:
        config.worker_id = existing.worker_id
        config.worker_token = existing.worker_token
        print(f"Reusing existing worker registration for {config.name}.")
    else:
        config.user_token = user_token()
    client = CoordinatorClient(config)
    try:
        await client.register(capabilities, persist=False)
        await client.heartbeat(capabilities)
        save_config(config)
        print(f"Worker config saved for {config.name}.")
    finally:
        await client.aclose()
    if args.install_service:
        install_launchd_service(args.python)
    else:
        print(f"Start manually from {ROOT / 'worker'} with: {args.python} -m app.main")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coordinator-url", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--install-service", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--enable-mock", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--allowed-models",
        default=os.getenv("DIALECTICAL_ALLOWED_MODELS"),
        help="comma-separated model IDs this worker may advertise, for example codex-gpt-5",
    )
    parser.add_argument(
        "--require-named-https",
        action="store_true",
        help="reject placeholder, non-HTTPS, local, or trycloudflare.com coordinator URLs",
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
