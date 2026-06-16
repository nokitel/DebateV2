#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))

from app.config import update_config_file


HOSTNAME_RE = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
    re.IGNORECASE,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Update a registered Dialectical worker config")
    parser.add_argument("--coordinator-url", required=True)
    parser.add_argument("--config", default="~/.dialectical-worker/config.toml")
    parser.add_argument(
        "--require-named-https",
        action="store_true",
        help="reject placeholder, non-HTTPS, local, or trycloudflare.com coordinator URLs",
    )
    parser.add_argument(
        "--allowed-models",
        default=argparse.SUPPRESS,
        help="comma-separated model IDs to advertise; omit to preserve, pass an empty string to clear",
    )
    args = parser.parse_args()

    kwargs: dict[str, object] = {}
    if hasattr(args, "allowed_models"):
        kwargs["allowed_models"] = args.allowed_models

    if args.require_named_https:
        if issue := named_https_url_issue(args.coordinator_url):
            raise SystemExit(f"Invalid named coordinator URL: {issue}")

    config_path = Path(args.config).expanduser()
    config = update_config_file(config_path, coordinator_url=args.coordinator_url, **kwargs)
    models = ",".join(config.allowed_models) if config.allowed_models else "all detected models"

    print(f"Updated worker config: {config_path}")
    print(f"coordinator_url={config.coordinator_url}")
    print(f"allowed_models={models}")
    print("worker_token=preserved" if config.worker_token else "worker_token=missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
