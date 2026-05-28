#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import stat
except ImportError:  # pragma: no cover
    stat = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = Path("/private/tmp/dialectical-local-single-machine-check.json")
DEFAULT_LM_STUDIO_URL = "http://127.0.0.1:1234"
DEFAULT_WEB_URL = "http://127.0.0.1:3000"
DEFAULT_COORDINATOR_URL = "http://127.0.0.1:8000"
DEFAULT_PUBLIC_URL = None
DEFAULT_DOMAIN = "dezbatere.ro"
DEFAULT_DB = Path("~/.dialectical/db.sqlite3").expanduser()
DEFAULT_GEMINI_SETTINGS = Path("~/.gemini/settings.json").expanduser()
GOOGLE_OAUTH_AUTH_TYPE = "oauth-personal"
DEFAULT_LM_STUDIO_CAPABILITY = "lmstudio:google_gemma-4-e4b-it"
DEFAULT_CLOUDFLARED_DIR = Path("~/.cloudflared").expanduser()
DEFAULT_QUICK_TUNNEL_LOGS = [
    Path("/tmp/dialectical-cloudflared-quick.err.log"),
    Path("/tmp/dialectical-cloudflared-quick.out.log"),
]
REQUIRED_LOCAL_PATHS = [
    ROOT / "coordinator" / "app" / "main.py",
    ROOT / "coordinator" / "app" / "core" / "config.py",
    ROOT / "coordinator" / "app" / "core" / "db.py",
    ROOT / "coordinator" / "tests" / "conftest.py",
    ROOT / "worker" / "app" / "main.py",
    ROOT / "worker" / "app" / "client.py",
    ROOT / "worker" / "app" / "capabilities.py",
    ROOT / "web" / "package.json",
    ROOT / "web" / "app" / "page.tsx",
    ROOT / "scripts" / "verify_public_endpoint.py",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_load_error": f"{type(exc).__name__}: {exc}"}
    return payload if isinstance(payload, dict) else {"_load_error": "settings file is not a JSON object"}


def nested_get(payload: dict[str, object], dotted_key: str) -> object:
    current: object = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def run(command: list[str], *, timeout: float = 8.0, env: dict[str, str] | None = None) -> dict[str, object]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
            env={**os.environ, **env} if env else None,
        )
        return {
            "command": command,
            "env_overrides": sorted(env or {}),
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "env_overrides": sorted(env or {}),
            "ok": False,
            "returncode": None,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "").strip() if isinstance(exc.stderr, str) else "",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": f"timed out after {timeout:g}s",
        }
    except OSError as exc:
        return {
            "command": command,
            "env_overrides": sorted(env or {}),
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


def http_json(url: str, *, timeout: float = 5.0) -> dict[str, object]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
            payload = json.loads(body.decode("utf-8"))
            return {"ok": True, "status": response.status, "payload": payload}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def http_text(url: str, *, timeout: float = 5.0) -> dict[str, object]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(2048)
            return {
                "ok": 200 <= response.status < 400,
                "status": response.status,
                "prefix": body.decode("utf-8", errors="replace"),
            }
    except (OSError, urllib.error.URLError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def http_head(url: str, *, timeout: float = 5.0) -> dict[str, object]:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"ok": 200 <= response.status < 400, "status": response.status}
    except (OSError, urllib.error.URLError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def has_dataless_flag(path: Path) -> bool:
    if stat is None:
        return False
    try:
        flags = path.stat().st_flags
    except (AttributeError, OSError):
        return False
    dataless = getattr(stat, "SF_DATALESS", 0)
    return bool(dataless and flags & dataless)


def checkout_hydration() -> dict[str, object]:
    offloaded = [rel(path) for path in REQUIRED_LOCAL_PATHS if has_dataless_flag(path)]
    missing = [rel(path) for path in REQUIRED_LOCAL_PATHS if not path.exists()]
    return {
        "ok": not offloaded and not missing,
        "offloaded": offloaded,
        "missing": missing,
    }


def command_path(name: str) -> str | None:
    result = run(["/usr/bin/which", name], timeout=2)
    if result["ok"] and result["stdout"]:
        return str(result["stdout"]).splitlines()[0]
    return None


def cli_status(probe_models: bool) -> dict[str, object]:
    status: dict[str, object] = {}
    for name, version_command in {
        "claude": ["claude", "--version"],
        "codex": ["codex", "--version"],
        "gemini": ["gemini", "--version"],
        "lms": ["lms", "--version"],
    }.items():
        path = command_path(name)
        entry: dict[str, object] = {"path": path}
        if path:
            entry["version"] = run(version_command, timeout=5)
        status[name] = entry

    if probe_models:
        status["claude"]["probe"] = run(["claude", "-p", "--max-turns", "1", "Reply with exactly: ok"], timeout=20)
        status["codex"]["probe"] = run(
            ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "Reply with exactly: ok"],
            timeout=60,
        )
        status["gemini"]["probe"] = run(
            ["gemini", "-p", "Reply with exactly: ok"],
            timeout=30,
            env={"GOOGLE_GENAI_USE_GCA": "true"},
        )
    return status


def lm_studio_status(base_url: str, model: str, probe: bool) -> dict[str, object]:
    models = http_json(f"{base_url.rstrip('/')}/v1/models", timeout=5)
    payload: dict[str, object] = {"base_url": base_url, "models_endpoint": models}
    model_ids: list[str] = []
    if models.get("ok"):
        raw_models = models.get("payload", {}).get("data", [])  # type: ignore[union-attr]
        if isinstance(raw_models, list):
            model_ids = [item.get("id") for item in raw_models if isinstance(item, dict) and isinstance(item.get("id"), str)]
    payload["model_ids"] = model_ids
    payload["expected_model"] = model
    payload["expected_model_loaded"] = model in model_ids
    if probe and model in model_ids:
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            data=json.dumps(
                {
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                    "temperature": 0,
                    "max_tokens": 5,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            content = response_payload["choices"][0]["message"]["content"]
            payload["probe"] = {"ok": content.strip().lower() == "ok", "content": content}
        except (OSError, urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
            payload["probe"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return payload


def runtime_routing_status(db_path: Path, capability: str) -> dict[str, object]:
    try:
        import sqlite3

        with sqlite3.connect(db_path) as db:
            row = db.execute("select value from settings where key = 'runtime_settings'").fetchone()
    except (OSError, sqlite3.Error) as exc:
        return {"ok": False, "database": str(db_path), "error": f"{type(exc).__name__}: {exc}"}
    if row is None:
        return {"ok": False, "database": str(db_path), "error": "runtime_settings missing"}
    try:
        value = json.loads(row[0])
    except (TypeError, json.JSONDecodeError) as exc:
        return {"ok": False, "database": str(db_path), "error": f"{type(exc).__name__}: {exc}"}
    enabled = value.get("enabled_models", [])
    routing = value.get("routing", {})
    configured_models: set[str] = set()
    if isinstance(routing, dict):
        for role_config in routing.values():
            if not isinstance(role_config, dict):
                continue
            primary = role_config.get("primary")
            if primary:
                configured_models.add(str(primary))
            configured_models.update(str(model) for model in role_config.get("fallback", []) if model)
            configured_models.update(str(model) for model in role_config.get("pool", []) if model)
    return {
        "ok": capability in enabled and capability in configured_models,
        "database": str(db_path),
        "expected_capability": capability,
        "enabled_models": enabled,
        "configured_models": sorted(configured_models),
    }


def launch_agent(label: str) -> dict[str, object]:
    path = Path("~/Library/LaunchAgents").expanduser() / f"{label}.plist"
    entry: dict[str, object] = {"path": str(path), "exists": path.exists()}
    if path.exists():
        try:
            with path.open("rb") as handle:
                entry["plist"] = plistlib.load(handle)
        except (OSError, plistlib.InvalidFileException) as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
    entry["process"] = run(["/bin/launchctl", "print", f"gui/{os.getuid()}/{label}"], timeout=5)
    return entry


def gemini_auth_status(settings_path: Path, worker_launchd: dict[str, object]) -> dict[str, object]:
    settings = load_json(settings_path)
    selected_top = settings.get("selectedAuthType")
    selected_nested = nested_get(settings, "security.auth.selectedType")
    settings_oauth_configured = (
        selected_top == GOOGLE_OAUTH_AUTH_TYPE
        or selected_nested == GOOGLE_OAUTH_AUTH_TYPE
    )
    plist = worker_launchd.get("plist")
    environment = plist.get("EnvironmentVariables", {}) if isinstance(plist, dict) else {}
    if not isinstance(environment, dict):
        environment = {}
    worker_google_account_env = environment.get("GOOGLE_GENAI_USE_GCA") == "true"
    worker_gemini_api_key_present = bool(environment.get("GEMINI_API_KEY"))
    return {
        "ok": settings_oauth_configured and worker_google_account_env and not worker_gemini_api_key_present,
        "settings_path": str(settings_path),
        "settings_exists": settings_path.exists(),
        "settings_load_error": settings.get("_load_error"),
        "selected_auth_type": selected_top,
        "security_auth_selected_type": selected_nested,
        "settings_oauth_configured": settings_oauth_configured,
        "worker_launchd_path": worker_launchd.get("path"),
        "worker_launchd_exists": worker_launchd.get("exists"),
        "worker_google_account_env": worker_google_account_env,
        "worker_gemini_api_key_present": worker_gemini_api_key_present,
        "shell_gemini_api_key_present": bool(os.getenv("GEMINI_API_KEY")),
    }


def output_lines(result: dict[str, object]) -> list[str]:
    stdout = result.get("stdout", "")
    if not isinstance(stdout, str):
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def dig_response_status(result: dict[str, object]) -> str | None:
    stdout = result.get("stdout", "")
    if not isinstance(stdout, str):
        return None
    marker = "status:"
    for line in stdout.splitlines():
        if marker not in line:
            continue
        after = line.split(marker, 1)[1].strip()
        return after.split(",", 1)[0].strip()
    return None


def extract_ns_records(result: dict[str, object]) -> list[str]:
    stdout = result.get("stdout", "")
    if not isinstance(stdout, str):
        return []
    records: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        parts = stripped.split()
        if len(parts) >= 5 and parts[-2].upper() == "NS":
            records.append(parts[-1])
    return records


def dns_status(domain: str) -> dict[str, object]:
    recursive_ns = run(["dig", "+short", domain, "NS"], timeout=5)
    registry_ns = run(["dig", "@primary.rotld.ro", domain, "NS"], timeout=5)
    romarg_soa = run(["dig", "@ns1.romarg.com", domain, "SOA"], timeout=5)
    recursive_nameservers = output_lines(recursive_ns)
    registry_nameservers = extract_ns_records(registry_ns)
    return {
        "domain": domain,
        "ns": recursive_ns,
        "a": run(["dig", "+short", domain, "A"], timeout=5),
        "www_cname": run(["dig", "+short", f"www.{domain}", "CNAME"], timeout=5),
        "registry_ns": registry_ns,
        "registry_nameservers": registry_nameservers,
        "recursive_nameservers": recursive_nameservers,
        "delegated_to_cloudflare": all(
            nameserver.endswith(".ns.cloudflare.com.") for nameserver in registry_nameservers
        )
        if registry_nameservers
        else False,
        "delegated_to_romarg": any(".romarg.com." in nameserver for nameserver in registry_nameservers),
        "romarg_authoritative_soa": romarg_soa,
        "romarg_authoritative_status": dig_response_status(romarg_soa),
    }


def cloudflared_status(directory: Path) -> dict[str, object]:
    cert = directory / "cert.pem"
    config = directory / "config.yml"
    credentials = sorted(path.name for path in directory.glob("*.json")) if directory.exists() else []
    return {
        "directory": str(directory),
        "cert_path": str(cert),
        "cert_exists": cert.exists(),
        "config_path": str(config),
        "config_exists": config.exists(),
        "credential_files": credentials,
        "named_tunnel_ready": cert.exists() and config.exists() and bool(credentials),
    }


def quick_tunnel_status(log_paths: list[Path]) -> dict[str, object]:
    urls: list[str] = []
    readable_logs: list[str] = []
    errors: list[str] = []
    pattern = re.compile(r"https://[A-Za-z0-9-]+\.trycloudflare\.com\b")
    for path in log_paths:
        if not path.exists():
            continue
        readable_logs.append(str(path))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
            continue
        urls.extend(pattern.findall(text))
    unique_urls = list(dict.fromkeys(urls))
    return {
        "log_paths": [str(path) for path in log_paths],
        "readable_logs": readable_logs,
        "urls": unique_urls,
        "current_url": urls[-1] if urls else None,
        "errors": errors,
    }


def probe_summary(entry: object) -> str:
    if not isinstance(entry, dict):
        return "not checked"
    probe = entry.get("probe")
    if not isinstance(probe, dict):
        return "not checked"
    if probe.get("ok"):
        return "ok"
    stderr = str(probe.get("stderr") or "")
    stdout = str(probe.get("stdout") or "")
    error = str(probe.get("error") or "")
    env_overrides = probe.get("env_overrides")
    env_names = set(env_overrides if isinstance(env_overrides, list) else [])
    combined = "\n".join(value for value in (stderr, stdout, error) if value)
    if "Invalid authentication credentials" in combined or "401" in combined:
        return "auth failed"
    if "timed out" in combined and "GOOGLE_GENAI_USE_GCA" in env_names:
        return "OAuth pending (Google-account auth)"
    if "Please set an Auth method" in combined or "GEMINI_API_KEY" in combined:
        return "auth missing"
    if "Not logged in" in combined:
        return "not logged in"
    return "failed"


def local_endpoints(web_url: str, coordinator_url: str, public_url: str | None) -> dict[str, object]:
    web_home = http_text(f"{web_url.rstrip('/')}/", timeout=5)
    static_assets: dict[str, object] = {"ok": False, "assets": []}
    prefix = web_home.get("prefix")
    if isinstance(prefix, str):
        assets = list(dict.fromkeys(re.findall(r'/_next/static/[^"\'<> ]+', prefix)))
        static_assets["assets"] = assets[:10]
        if assets:
            static_assets["sample"] = http_head(f"{web_url.rstrip('/')}{assets[0]}", timeout=5)
            static_assets["ok"] = bool(static_assets["sample"].get("ok"))  # type: ignore[union-attr]
        else:
            static_assets["error"] = "no _next static assets found in home HTML"
    payload: dict[str, object] = {
        "coordinator_health": http_json(f"{coordinator_url.rstrip('/')}/healthz", timeout=5),
        "coordinator_backends": http_json(f"{coordinator_url.rstrip('/')}/api/backends/status", timeout=5),
        "web_home": web_home,
        "web_static_assets": static_assets,
        "web_backends": http_json(f"{web_url.rstrip('/')}/api/backends/status", timeout=5),
    }
    if public_url:
        payload["public_backends"] = http_json(f"{public_url.rstrip('/')}/api/backends/status", timeout=8)
    return payload


def select_public_url(
    explicit_public_url: str | None,
    domain: str,
    dns: dict[str, object],
    cloudflared: dict[str, object],
    quick_tunnel: dict[str, object],
) -> dict[str, object]:
    if explicit_public_url:
        return {"url": explicit_public_url, "source": "argument"}
    if cloudflared.get("named_tunnel_ready") and dns.get("delegated_to_cloudflare"):
        return {"url": f"https://{domain}", "source": "named_tunnel"}
    if quick_tunnel.get("current_url"):
        return {"url": quick_tunnel["current_url"], "source": "quick_tunnel"}
    return {"url": None, "source": "none"}


def summarize(report: dict[str, object]) -> int:
    checks = report["checks"]  # type: ignore[index]
    hydration = checks["checkout_hydration"]  # type: ignore[index]
    endpoints = checks["local_endpoints"]  # type: ignore[index]
    cli = checks["cli_status"]  # type: ignore[index]
    gemini_auth = checks["gemini_auth"]  # type: ignore[index]
    lm_studio = checks["lm_studio"]  # type: ignore[index]
    routing = checks["runtime_routing"]  # type: ignore[index]
    dns = checks["dns"]  # type: ignore[index]
    cloudflared = checks["cloudflared"]  # type: ignore[index]
    quick_tunnel = checks["quick_tunnel"]  # type: ignore[index]
    print("Local single-machine readiness")
    print(f"- checkout hydration: {'ok' if hydration['ok'] else 'blocked'}")
    if hydration["offloaded"]:
        print(f"  offloaded: {', '.join(hydration['offloaded'][:8])}")
    print(f"- coordinator health: {'ok' if endpoints['coordinator_health']['ok'] else 'failed'}")
    print(f"- web home: {'ok' if endpoints['web_home']['ok'] else 'failed'}")
    print(f"- web static assets: {'ok' if endpoints['web_static_assets']['ok'] else 'failed'}")
    backends = endpoints["coordinator_backends"]
    if backends["ok"]:
        workers = backends["payload"].get("workers", [])
        online_workers = [worker for worker in workers if worker.get("status") == "online"]
        print(f"- local workers online: {len(online_workers)}")
        for worker in workers:
            print(f"  {worker.get('name')}: {worker.get('status')} {worker.get('capabilities')}")
    else:
        print("- local workers: unavailable")
    print(f"- LM Studio server: {'ok' if lm_studio['models_endpoint']['ok'] else 'failed'}")
    print(f"- LM Studio expected model: {lm_studio['expected_model_loaded']}")
    print(f"- local routing includes LM Studio: {'ok' if routing['ok'] else 'failed'}")
    if any(isinstance(entry, dict) and "probe" in entry for entry in cli.values()):
        print(f"- Codex CLI probe: {probe_summary(cli.get('codex'))}")
        print(f"- Claude CLI probe: {probe_summary(cli.get('claude'))}")
        print(f"- Gemini CLI probe: {probe_summary(cli.get('gemini'))}")
    print(f"- Gemini Google-account auth config: {'ok' if gemini_auth['ok'] else 'incomplete'}")
    delegation = dns.get("registry_nameservers") or dns.get("recursive_nameservers") or []
    if dns.get("delegated_to_cloudflare"):
        delegation_status = "Cloudflare"
    elif dns.get("delegated_to_romarg"):
        delegation_status = "Romarg"
    elif delegation:
        delegation_status = ", ".join(delegation)
    else:
        delegation_status = "unresolved"
    print(f"- dezbatere.ro delegation: {delegation_status}")
    if dns.get("romarg_authoritative_status"):
        print(f"- Romarg authoritative DNS status: {dns['romarg_authoritative_status']}")
    print(f"- cloudflared named tunnel config: {'ok' if cloudflared['named_tunnel_ready'] else 'missing'}")
    public_url = checks.get("public_url", {})  # type: ignore[assignment]
    if isinstance(public_url, dict) and public_url.get("url"):
        print(f"- public URL checked: {public_url['url']} ({public_url.get('source')})")
    if quick_tunnel.get("current_url"):
        print(f"- quick tunnel URL: {quick_tunnel['current_url']}")
    public_backends = endpoints.get("public_backends")
    if public_backends:
        print(f"- public tunnel API: {'ok' if public_backends['ok'] else 'failed'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the simplified one-computer dialectical deployment.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--coordinator-url", default=DEFAULT_COORDINATOR_URL)
    parser.add_argument("--public-url", default=DEFAULT_PUBLIC_URL)
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--cloudflared-dir", type=Path, default=DEFAULT_CLOUDFLARED_DIR)
    parser.add_argument("--lm-studio-url", default=DEFAULT_LM_STUDIO_URL)
    parser.add_argument("--lm-studio-model", default="google_gemma-4-e4b-it")
    parser.add_argument("--lm-studio-capability", default=DEFAULT_LM_STUDIO_CAPABILITY)
    parser.add_argument("--gemini-settings", type=Path, default=DEFAULT_GEMINI_SETTINGS)
    parser.add_argument("--probe-models", action="store_true")
    args = parser.parse_args()
    quick_tunnel = quick_tunnel_status(DEFAULT_QUICK_TUNNEL_LOGS)
    cloudflared = cloudflared_status(args.cloudflared_dir)
    dns = dns_status(args.domain)
    public_url = select_public_url(args.public_url, args.domain, dns, cloudflared, quick_tunnel)

    launchd = {
        label: launch_agent(label)
        for label in (
            "com.dialectical.coordinator",
            "com.dialectical.web",
            "com.dialectical.worker",
            "com.dialectical.lmstudio-worker",
            "com.dialectical.cloudflared",
            "com.dialectical.cloudflared-quick",
        )
    }

    report = {
        "status": "checked",
        "completed_at": now_iso(),
        "scope": "single-computer",
        "checks": {
            "checkout_hydration": checkout_hydration(),
            "cli_status": cli_status(args.probe_models),
            "gemini_auth": gemini_auth_status(args.gemini_settings.expanduser(), launchd["com.dialectical.worker"]),
            "lm_studio": lm_studio_status(args.lm_studio_url, args.lm_studio_model, probe=True),
            "runtime_routing": runtime_routing_status(args.database, args.lm_studio_capability),
            "local_endpoints": local_endpoints(args.web_url, args.coordinator_url, public_url.get("url")),
            "cloudflared": cloudflared,
            "quick_tunnel": quick_tunnel,
            "public_url": public_url,
            "launchd": launchd,
            "dns": dns,
        },
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Report: {args.report_path}")
    return summarize(report)


if __name__ == "__main__":
    raise SystemExit(main())
