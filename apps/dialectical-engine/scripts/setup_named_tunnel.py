from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import install_tunnel  # noqa: E402


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def run_command(command: list[str], *, dry_run: bool) -> None:
    print("+ " + shlex.join(command))
    if dry_run:
        return
    subprocess.run(command, cwd=ROOT, check=True)


def auto_credentials_ready(credentials_arg: str) -> bool:
    try:
        install_tunnel.credentials_file(credentials_arg)
    except ValueError as exc:
        if credentials_arg.strip() not in install_tunnel.AUTO_CREDENTIALS_VALUES:
            raise SystemExit(str(exc)) from exc
        recoverable = (
            "no Cloudflare directory found",
            "no tunnel credentials JSON files found",
        )
        if not any(message in str(exc) for message in recoverable):
            raise SystemExit(str(exc)) from exc
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create, install, and verify the named Cloudflare Tunnel for Dialectical Engine"
    )
    parser.add_argument("--tunnel", default=os.getenv("TUNNEL_NAME", "dialectical"))
    parser.add_argument("--hostname", default=os.getenv("TUNNEL_HOSTNAME", "debate.<your-domain>"))
    parser.add_argument("--credentials-file", default=os.getenv("CLOUDFLARED_CREDENTIALS", "auto"))
    parser.add_argument("--skip-login", action="store_true")
    parser.add_argument("--skip-create", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--skip-status", action="store_true")
    parser.add_argument("--skip-handoff", action="store_true")
    parser.add_argument("--allow-unverified-handoff", action="store_true")
    parser.add_argument("--stop-quick-after-verified", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.skip_status and not args.skip_handoff and not args.allow_unverified_handoff:
        raise SystemExit(
            "Refusing to refresh named-URL handoff without endpoint status; "
            "remove --skip-status, add --skip-handoff, or pass --allow-unverified-handoff"
        )
    if args.skip_preflight and not args.skip_handoff and not args.allow_unverified_handoff:
        raise SystemExit(
            "Refusing to refresh named-URL handoff without deploy preflight; "
            "remove --skip-preflight, add --skip-handoff, or pass --allow-unverified-handoff"
        )
    if args.skip_status and args.stop_quick_after_verified:
        raise SystemExit("Refusing to stop the quick tunnel without endpoint status; remove --skip-status")
    if args.skip_preflight and args.stop_quick_after_verified:
        raise SystemExit("Refusing to stop the quick tunnel without deploy preflight; remove --skip-preflight")

    try:
        tunnel = install_tunnel.tunnel_name(args.tunnel)
    except ValueError as exc:
        raise SystemExit(f"Invalid TUNNEL_NAME: {exc}") from exc
    try:
        hostname = install_tunnel.public_hostname(args.hostname)
    except ValueError as exc:
        raise SystemExit(f"Invalid TUNNEL_HOSTNAME: {exc}") from exc

    cloudflared = shutil.which("cloudflared")
    if not cloudflared and not args.dry_run:
        raise SystemExit("cloudflared is not on PATH; install it before running setup-named-tunnel")

    cloudflared_command = cloudflared or "cloudflared"
    credentials_arg = args.credentials_file.strip() or "auto"
    credentials_ready = auto_credentials_ready(credentials_arg)

    if not credentials_ready:
        if args.skip_create:
            raise SystemExit(
                "No tunnel credentials JSON is available; remove --skip-create or run "
                "`cloudflared tunnel create <name>` first"
            )
        cert_path = install_tunnel.CLOUDFLARED_DIR / "cert.pem"
        if not args.skip_login and not cert_path.exists():
            run_command([cloudflared_command, "tunnel", "login"], dry_run=args.dry_run)
        run_command([cloudflared_command, "tunnel", "create", tunnel], dry_run=args.dry_run)

    run_command(
        [
            "make",
            "install-tunnel",
            f"TUNNEL_NAME={tunnel}",
            f"TUNNEL_HOSTNAME={hostname}",
            f"CLOUDFLARED_CREDENTIALS={credentials_arg}",
        ],
        dry_run=args.dry_run,
    )

    if not args.skip_preflight:
        run_command(
            [
                "make",
                "deploy-preflight",
                "DEPLOY_ROLE=mac-mini",
                "PREFLIGHT_FLAGS=--require-installed-services",
            ],
            dry_run=args.dry_run,
        )
    if not args.skip_status:
        run_command(["make", "status", "STATUS_FLAGS=--check-endpoints"], dry_run=args.dry_run)
    if not args.skip_handoff:
        run_command(["make", "handoff-bundles", f"PUBLIC_URL=https://{hostname}"], dry_run=args.dry_run)
    if args.stop_quick_after_verified:
        run_command(["make", "stop-quick-tunnel"], dry_run=args.dry_run)
        if not args.skip_status:
            run_command(["make", "status", "STATUS_FLAGS=--check-endpoints"], dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
