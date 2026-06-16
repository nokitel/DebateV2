from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
QUICK_TUNNEL_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.dialectical.cloudflared-quick.plist"
CLOUDFLARED_DIR = Path.home() / ".cloudflared"
AUTO_CREDENTIALS_VALUES = {"", "auto", "detect", "auto-detect"}
REQUIRED_CREDENTIAL_KEYS = ("AccountTag", "TunnelID", "TunnelSecret")
HOSTNAME_RE = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
    re.IGNORECASE,
)
TUNNEL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def default_launchd_path() -> str:
    return f"{Path.home()}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def has_placeholder(value: str) -> bool:
    return "<" in value or ">" in value


def public_hostname(value: str) -> str:
    hostname = value.strip().rstrip(".").lower()
    if not hostname:
        raise ValueError("hostname cannot be empty")
    if has_placeholder(value):
        raise ValueError("hostname contains a placeholder")
    if "://" in hostname or any(character in hostname for character in "/?#:"):
        raise ValueError("hostname must be a DNS name such as debate.example.com, not a URL")
    if hostname == "trycloudflare.com" or hostname.endswith(".trycloudflare.com"):
        raise ValueError("hostname must be a stable named Cloudflare hostname, not a trycloudflare.com quick tunnel")
    if not HOSTNAME_RE.fullmatch(hostname):
        raise ValueError("hostname must be a valid DNS name such as debate.example.com")
    return hostname


def tunnel_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("tunnel name cannot be empty")
    if has_placeholder(value):
        raise ValueError("tunnel name contains a placeholder")
    if "://" in cleaned or any(character in cleaned for character in "/?#:"):
        raise ValueError("tunnel name must be a Cloudflare tunnel name or UUID, not a URL")
    if not TUNNEL_NAME_RE.fullmatch(cleaned):
        raise ValueError("tunnel name may contain only letters, numbers, dots, underscores, and hyphens")
    return cleaned


def auto_credentials_file(cloudflared_dir: Path | None = None) -> Path:
    cloudflared_dir = cloudflared_dir or CLOUDFLARED_DIR
    if not cloudflared_dir.exists():
        raise ValueError(
            f"no Cloudflare directory found at {cloudflared_dir}; "
            "run `cloudflared tunnel login` and `cloudflared tunnel create <name>` first"
        )
    candidates = sorted(path for path in cloudflared_dir.glob("*.json") if path.is_file())
    if not candidates:
        raise ValueError(
            f"no tunnel credentials JSON files found in {cloudflared_dir}; "
            "run `cloudflared tunnel create <name>` first"
        )
    if len(candidates) > 1:
        formatted = ", ".join(str(path) for path in candidates)
        raise ValueError(
            "multiple tunnel credentials JSON files found; set "
            f"CLOUDFLARED_CREDENTIALS to the intended file ({formatted})"
        )
    validate_credentials_file(candidates[0])
    return candidates[0]


def validate_credentials_file(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cloudflare credentials file unreadable: {path} ({type(exc).__name__}: {exc})") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cloudflare credentials file is not valid JSON: {path} ({exc.msg})") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Cloudflare credentials file must be a JSON object: {path}")

    missing = [
        key
        for key in REQUIRED_CREDENTIAL_KEYS
        if not isinstance(payload.get(key), str) or not payload.get(key, "").strip()
    ]
    if missing:
        raise ValueError(f"Cloudflare credentials file missing required keys: {', '.join(missing)}")

    placeholders = [key for key in REQUIRED_CREDENTIAL_KEYS if has_placeholder(str(payload.get(key, "")))]
    if placeholders:
        raise ValueError(f"Cloudflare credentials file contains placeholder values: {', '.join(placeholders)}")
    try:
        UUID(str(payload["TunnelID"]).strip())
    except ValueError as exc:
        raise ValueError("Cloudflare credentials file TunnelID is not a UUID") from exc


def credentials_file(value: str | None) -> Path:
    raw = (value or "").strip()
    if raw in AUTO_CREDENTIALS_VALUES:
        return auto_credentials_file()
    if has_placeholder(raw):
        raise ValueError(
            "set TUNNEL_HOSTNAME and CLOUDFLARED_CREDENTIALS before running install-tunnel. "
            "Example: make install-tunnel TUNNEL_HOSTNAME=debate.example.com "
            "CLOUDFLARED_CREDENTIALS=$HOME/.cloudflared/<id>.json"
        )
    path = Path(raw).expanduser()
    if not path.exists():
        raise ValueError(f"Cloudflare credentials file does not exist: {path}")
    validate_credentials_file(path)
    return path


def install_launchd_service(cloudflared: str, config_path: Path, tunnel: str) -> None:
    template = ROOT / "deploy" / "launchd" / "cloudflared.plist"
    destination = Path.home() / "Library" / "LaunchAgents" / "com.dialectical.cloudflared.plist"
    rendered = (
        template.read_text()
        .replace("__CLOUDFLARED__", cloudflared)
        .replace("__CONFIG__", str(config_path))
        .replace("__TUNNEL__", tunnel)
        .replace("__PATH__", default_launchd_path())
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered)
    subprocess.run(["launchctl", "unload", str(destination)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "load", str(destination)], check=True)
    print(f"Installed and started launchd service: {destination}")


def stop_quick_tunnel_service(plist_path: Path = QUICK_TUNNEL_PLIST) -> None:
    if not plist_path.exists():
        print(f"Quick tunnel launchd service not found: {plist_path}")
        return
    result = subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        print(f"Stopped quick tunnel launchd service: {plist_path}")
    else:
        print(
            "Requested quick tunnel launchd unload; launchctl returned "
            f"{result.returncode}. Verify with: make status"
        )


def render_config(tunnel: str, hostname: str, credentials_file: Path) -> str:
    template = ROOT / "deploy" / "cloudflared.config.yml"
    return (
        template.read_text()
        .replace("dialectical", tunnel, 1)
        .replace("debate.<your-domain>", hostname)
        .replace("/Users/<you>/.cloudflared/<tunnel-id>.json", str(credentials_file))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Cloudflare Tunnel config for Dialectical Engine")
    parser.add_argument("--tunnel")
    parser.add_argument("--hostname")
    parser.add_argument("--credentials-file", default="auto")
    parser.add_argument("--config", default="~/.cloudflared/config.yml")
    parser.add_argument("--route-dns", action="store_true")
    parser.add_argument("--install-service", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--stop-quick-service",
        action="store_true",
        help="unload the temporary quick-tunnel launchd service after named-tunnel install work",
    )
    parser.add_argument(
        "--stop-quick-service-only",
        action="store_true",
        help="only unload the temporary quick-tunnel launchd service",
    )
    args = parser.parse_args()

    if args.stop_quick_service_only:
        stop_quick_tunnel_service()
        return

    missing = [
        label
        for label, value in (
            ("--tunnel", args.tunnel),
            ("--hostname", args.hostname),
        )
        if not value
    ]
    if missing:
        raise SystemExit("Missing required arguments: " + ", ".join(missing))

    try:
        hostname = public_hostname(args.hostname)
    except ValueError as exc:
        raise SystemExit(f"Invalid TUNNEL_HOSTNAME: {exc}") from exc
    try:
        tunnel = tunnel_name(args.tunnel)
    except ValueError as exc:
        raise SystemExit(f"Invalid TUNNEL_NAME: {exc}") from exc
    try:
        credentials_path = credentials_file(args.credentials_file)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    cloudflared = shutil.which("cloudflared")
    if not cloudflared and (args.route_dns or args.install_service):
        raise SystemExit("cloudflared is not on PATH; install it before using --route-dns or --install-service")

    destination = Path(args.config).expanduser()
    rendered = render_config(tunnel, hostname, credentials_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered)
    print(f"Wrote Cloudflare Tunnel config to {destination}")

    if not cloudflared:
        print("cloudflared is not on PATH. Install it, then run: cloudflared tunnel run " + args.tunnel)
        return

    if args.route_dns:
        subprocess.run([cloudflared, "tunnel", "route", "dns", tunnel, hostname], check=True)
    if args.install_service:
        install_launchd_service(cloudflared, destination, tunnel)
    else:
        print(f"Start the tunnel with: {cloudflared} tunnel --config {destination} run {tunnel}")
    if args.stop_quick_service:
        stop_quick_tunnel_service()


if __name__ == "__main__":
    main()
