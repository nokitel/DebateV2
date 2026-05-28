#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit


HOSTNAME_RE = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
    re.IGNORECASE,
)


class EndpointError(RuntimeError):
    pass


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


def fetch_status(base_url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/backends/status",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise EndpointError("/api/backends/status did not return a JSON object")
    return payload


def status_detail(payload: dict[str, Any]) -> str:
    workers = payload.get("workers")
    if not isinstance(workers, list):
        raise EndpointError("/api/backends/status did not return a workers list")
    names: list[str] = []
    for index, worker in enumerate(workers, start=1):
        if not isinstance(worker, dict):
            raise EndpointError(f"workers[{index}] is not an object")
        raw_name = worker.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            names.append(raw_name.strip())
    return ", ".join(sorted(names)) if names else "no workers"


def verify_public_endpoint(base_url: str, timeout: float, require_named_https: bool) -> str:
    if require_named_https:
        issue = named_https_url_issue(base_url)
        if issue:
            raise EndpointError(f"invalid named coordinator URL: {issue}")
    try:
        payload = fetch_status(base_url, timeout)
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise EndpointError(f"{base_url.rstrip('/')} /api/backends/status unavailable: {exc}") from exc
    return status_detail(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a public Dialectical coordinator endpoint is reachable")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--require-named-https", action="store_true")
    args = parser.parse_args()

    try:
        detail = verify_public_endpoint(args.base_url, max(args.timeout, 0.1), args.require_named_https)
    except EndpointError as exc:
        print(f"public coordinator endpoint check failed: {exc}", file=sys.stderr)
        return 2
    print(f"public coordinator endpoint ok: {args.base_url.rstrip('/')} ({detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
