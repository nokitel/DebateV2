#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_OUTPUT = Path("Romarg_Nameservers_To_Set.md")
NAMESERVER_RE = re.compile(r"^[a-z0-9-]+\.ns\.cloudflare\.com\.$")


def split_nameservers(values: list[str]) -> list[str]:
    nameservers: list[str] = []
    for value in values:
        for item in re.split(r"[\s,;]+", value):
            item = item.strip()
            if item:
                nameservers.append(item)
    return nameservers


def normalize_nameserver(value: str) -> str:
    normalized = value.strip().lower().rstrip(".")
    return f"{normalized}."


def validate_nameservers(values: list[str]) -> tuple[list[str], list[str]]:
    normalized = [normalize_nameserver(value) for value in split_nameservers(values)]
    unique = list(dict.fromkeys(normalized))
    errors: list[str] = []
    if len(unique) != 2:
        errors.append(f"expected exactly 2 unique Cloudflare nameservers, got {len(unique)}")
    for nameserver in unique:
        if not NAMESERVER_RE.match(nameserver):
            errors.append(f"not a Cloudflare nameserver: {nameserver}")
    return unique, errors


def pending_lines(generated_at: str) -> list[str]:
    return [
        "# Romarg Nameservers To Set",
        "",
        f"Generated at: `{generated_at}`",
        "Status: waiting for Cloudflare-assigned nameservers.",
        "",
        "After adding `dezbatere.ro` to Cloudflare, run:",
        "",
        "```sh",
        'CLOUDFLARE_NAMESERVERS="first.ns.cloudflare.com second.ns.cloudflare.com" make prepare-romarg-nameservers',
        "```",
        "",
        "Replace the example names with the exact two nameservers Cloudflare shows for this zone.",
    ]


def validated_lines(nameservers: list[str], generated_at: str) -> list[str]:
    return [
        "# Romarg Nameservers To Set",
        "",
        f"Generated at: `{generated_at}`",
        "Status: validated Cloudflare nameservers.",
        "",
        "## Paste In Romarg",
        "",
        f"- Nameserver 1: `{nameservers[0]}`",
        f"- Nameserver 2: `{nameservers[1]}`",
        "- Leave every other nameserver field blank.",
        "- Remove all existing `romarg.com` nameservers before saving.",
        "",
        "## After Saving In Romarg",
        "",
        "```sh",
        "make wait-dezbatere-dns",
        "make hosting-status",
        "cloudflared tunnel login",
        "make resume-dezbatere-hosting",
        "```",
        "",
        "Do not add `A` records for the home IP. This setup uses Cloudflare Tunnel.",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Cloudflare nameservers and write a Romarg-ready handoff card."
    )
    parser.add_argument(
        "--nameservers",
        action="append",
        default=[],
        help="Cloudflare nameservers as a comma-separated or whitespace-separated string.",
    )
    parser.add_argument(
        "--nameserver",
        action="append",
        default=[],
        help="One Cloudflare nameserver. May be passed twice.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    values = [*args.nameservers, *args.nameserver]
    generated_at = datetime.now(timezone.utc).isoformat()
    if not values:
        args.output.write_text("\n".join(pending_lines(generated_at)) + "\n", encoding="utf-8")
        print(f"Wrote pending template: {args.output}")
        return 0

    nameservers, errors = validate_nameservers(values)
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 2

    args.output.write_text("\n".join(validated_lines(nameservers, generated_at)) + "\n", encoding="utf-8")
    print(f"Wrote validated Romarg nameserver card: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
