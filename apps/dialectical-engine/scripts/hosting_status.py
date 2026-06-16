#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DOMAIN = "dezbatere.ro"
DEFAULT_WEB_URL = "http://127.0.0.1:3000"
DEFAULT_CLOUDFLARED_DIR = Path("~/.cloudflared").expanduser()
DEFAULT_REPORT = Path("/private/tmp/dialectical-hosting-status.json")
HEALTH_CHECK_USER_AGENT = "Mozilla/5.0 (compatible; DialecticalHealthCheck/1.0; +https://dezbatere.ro)"
QUICK_TUNNEL_LOGS = [
    Path("/tmp/dialectical-cloudflared-quick.err.log"),
    Path("/tmp/dialectical-cloudflared-quick.out.log"),
]


def run(command: list[str], *, timeout: int = 8) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "command": command,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": command,
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def http_json(url: str, *, timeout: int = 5) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": HEALTH_CHECK_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "status": response.status, "payload": payload}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def http_text(url: str, *, timeout: int = 5) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": HEALTH_CHECK_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(8192)
            return {
                "ok": 200 <= response.status < 400,
                "status": response.status,
                "prefix": body.decode("utf-8", errors="replace"),
            }
    except (OSError, urllib.error.URLError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def http_head(url: str, *, timeout: int = 5) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": HEALTH_CHECK_USER_AGENT}, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"ok": 200 <= response.status < 400, "status": response.status}
    except (OSError, urllib.error.URLError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def web_surface(base_url: str | None) -> dict[str, Any]:
    if not base_url:
        return {"ok": False, "error": "missing base URL"}
    home = http_text(f"{base_url.rstrip('/')}/", timeout=8)
    static_assets: dict[str, Any] = {"ok": False, "assets": []}
    prefix = home.get("prefix")
    if isinstance(prefix, str):
        assets = list(dict.fromkeys(re.findall(r'/_next/static/[^"\'<> ]+', prefix)))
        static_assets["assets"] = assets[:10]
        if assets:
            sample = http_head(f"{base_url.rstrip('/')}{assets[0]}", timeout=8)
            static_assets["sample"] = sample
            static_assets["ok"] = bool(sample.get("ok"))
        else:
            static_assets["error"] = "no _next static assets found in home HTML"
    return {
        "ok": bool(home.get("ok") and static_assets.get("ok")),
        "base_url": base_url.rstrip("/"),
        "home": home,
        "static_assets": static_assets,
    }


def extract_ns_records(result: dict[str, Any]) -> list[str]:
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
            records.append(parts[-1].lower())
    return sorted(set(records))


def registry_dns(domain: str) -> dict[str, Any]:
    result = run(["dig", "@primary.rotld.ro", "+time=3", "+tries=1", domain, "NS"], timeout=8)
    nameservers = extract_ns_records(result)
    return {
        "result": result,
        "nameservers": nameservers,
        "delegated_to_cloudflare": bool(nameservers)
        and all(ns.endswith(".ns.cloudflare.com.") for ns in nameservers),
        "delegated_to_romarg": any(".romarg.com." in ns for ns in nameservers),
    }


def cloudflared(directory: Path) -> dict[str, Any]:
    cert = directory / "cert.pem"
    config = directory / "config.yml"
    credentials = sorted(path.name for path in directory.glob("*.json")) if directory.exists() else []
    service = run(["launchctl", "print", f"gui/{os.getuid()}/com.dialectical.cloudflared"], timeout=5)
    return {
        "directory": str(directory),
        "cert_path": str(cert),
        "cert_exists": cert.exists(),
        "config_path": str(config),
        "config_exists": config.exists(),
        "credential_files": credentials,
        "named_tunnel_ready": cert.exists() and config.exists() and bool(credentials),
        "service_loaded": bool(service.get("ok")),
        "service": service,
    }


def quick_tunnel() -> dict[str, Any]:
    pattern = re.compile(r"https://[A-Za-z0-9-]+\.trycloudflare\.com\b")
    urls: list[str] = []
    for path in QUICK_TUNNEL_LOGS:
        if not path.exists():
            continue
        try:
            urls.extend(pattern.findall(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    current_url = urls[-1] if urls else None
    api = http_json(f"{current_url}/api/backends/status", timeout=8) if current_url else {"ok": False}
    return {"current_url": current_url, "api": api, "web": web_surface(current_url)}


def next_action(
    local_app: dict[str, Any],
    local_web: dict[str, Any],
    dns: dict[str, Any],
    cf: dict[str, Any],
    named_endpoint: dict[str, Any],
    named_web: dict[str, Any],
) -> str:
    if not local_app.get("ok"):
        return "Run `make local-status` and fix the local web app before tunnel setup."
    if not local_web.get("ok"):
        return "Local API works, but the local web UI/static assets failed; run `make rebuild-web-service`, then `make hosting-status`."
    if not dns.get("delegated_to_cloudflare"):
        return (
            "Add dezbatere.ro to Cloudflare, run `make prepare-romarg-nameservers` with the assigned "
            "nameservers, update Romarg, then run `make wait-dezbatere-dns`."
        )
    if not cf.get("cert_exists"):
        return "Run `cloudflared tunnel login`, then rerun `make hosting-status`."
    if not cf.get("named_tunnel_ready"):
        return "Run `make resume-dezbatere-hosting`."
    if not cf.get("service_loaded"):
        return "Verify HTTPS manually, then run `INSTALL_SERVICE=1 STOP_QUICK_TUNNEL=1 make resume-dezbatere-hosting`."
    if not named_endpoint.get("ok"):
        return "Named tunnel service is installed, but `https://dezbatere.ro/api/backends/status` is not serving yet."
    if not named_web.get("ok"):
        return "Named tunnel API works, but `https://dezbatere.ro/` or its static assets are not serving yet."
    return "Named domain is serving the app; run final `make local-status` and stop any remaining quick tunnel if needed."


def main() -> int:
    parser = argparse.ArgumentParser(description="Report dezbatere.ro hosting and Cloudflare Tunnel status.")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--cloudflared-dir", type=Path, default=DEFAULT_CLOUDFLARED_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    local_base_url = args.web_url.rstrip("/")
    local_app = http_json(f"{local_base_url}/api/backends/status", timeout=5)
    local_web = web_surface(local_base_url)
    dns = registry_dns(args.domain)
    cf = cloudflared(args.cloudflared_dir.expanduser())
    quick = quick_tunnel()
    named_base_url = f"https://{args.domain}"
    named_endpoint = http_json(f"{named_base_url}/api/backends/status", timeout=8)
    named_web = web_surface(named_base_url)
    report = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "domain": args.domain,
        "local_app": local_app,
        "local_web": local_web,
        "dns": dns,
        "cloudflared": cf,
        "quick_tunnel": quick,
        "named_endpoint": named_endpoint,
        "named_web": named_web,
    }
    report["next_action"] = next_action(local_app, local_web, dns, cf, named_endpoint, named_web)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print("Hosting status")
    print(f"- local app: {'ok' if local_app.get('ok') else 'failed'}")
    print(f"- local web UI: {'ok' if local_web.get('ok') else 'failed'}")
    nameservers = dns.get("nameservers") or []
    print(f"- registry nameservers: {', '.join(nameservers) if nameservers else '<none>'}")
    if dns.get("delegated_to_cloudflare"):
        print("- delegation: Cloudflare")
    elif dns.get("delegated_to_romarg"):
        print("- delegation: Romarg")
    else:
        print("- delegation: not Cloudflare")
    print(f"- cloudflared login: {'ok' if cf.get('cert_exists') else 'missing'}")
    print(f"- named tunnel config: {'ok' if cf.get('named_tunnel_ready') else 'missing'}")
    print(f"- named tunnel service: {'loaded' if cf.get('service_loaded') else 'not loaded'}")
    print(f"- named endpoint: {'ok' if named_endpoint.get('ok') else 'failed'}")
    print(f"- named web UI: {'ok' if named_web.get('ok') else 'failed'}")
    if quick.get("current_url"):
        quick_ok = bool(quick.get("api", {}).get("ok") and quick.get("web", {}).get("ok"))
        print(f"- quick tunnel: {quick['current_url']} ({'ok' if quick_ok else 'failed'})")
    print(f"- next: {report['next_action']}")
    print(f"Report: {args.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
