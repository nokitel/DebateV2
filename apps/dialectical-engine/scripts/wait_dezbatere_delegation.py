#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import time
from datetime import datetime


DEFAULT_DOMAIN = "dezbatere.ro"
DEFAULT_SERVER = "primary.rotld.ro"


def dig_nameservers(domain: str, server: str) -> tuple[list[str], str, str, int]:
    command = [
        "dig",
        f"@{server}",
        "+time=3",
        "+tries=1",
        domain,
        "NS",
    ]
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    nameservers: list[str] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[-2].upper() == "NS":
            nameservers.append(parts[-1].lower())
    return sorted(set(nameservers)), proc.stdout.strip(), proc.stderr.strip(), proc.returncode


def is_cloudflare_delegation(nameservers: list[str]) -> bool:
    return bool(nameservers) and all(ns.endswith(".ns.cloudflare.com.") for ns in nameservers)


def format_nameservers(nameservers: list[str]) -> str:
    return ", ".join(nameservers) if nameservers else "<none>"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wait until dezbatere.ro is delegated from ROTLD to Cloudflare nameservers."
    )
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true", help="Check once and exit without waiting.")
    args = parser.parse_args()

    deadline = time.monotonic() + max(args.timeout_seconds, 0)
    attempt = 0
    while True:
        attempt += 1
        nameservers, stdout, stderr, returncode = dig_nameservers(args.domain, args.server)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {args.domain} registry nameservers: {format_nameservers(nameservers)}")
        if is_cloudflare_delegation(nameservers):
            print("Delegation is on Cloudflare. Next:")
            print("  cloudflared tunnel login")
            print("  make resume-dezbatere-hosting")
            return 0
        if returncode != 0:
            print(f"dig exited with {returncode}")
            if stderr:
                print(stderr)
            if stdout and not nameservers:
                print(stdout)
        if any(".romarg.com." in ns for ns in nameservers):
            print(
                "Still delegated to Romarg. After Cloudflare assigns nameservers, run "
                "`make prepare-romarg-nameservers`, then finish Romarg_TODO.md."
            )
        elif nameservers:
            print("Delegated to non-Cloudflare nameservers. Check the names entered at Romarg.")
        else:
            print("No registry nameservers found yet.")

        if args.once:
            return 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print("Timed out waiting for Cloudflare delegation.")
            return 1
        sleep_for = min(max(args.interval_seconds, 1), remaining)
        time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main())
