from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prepare_romarg_nameservers.py"


def load_module():
    spec = importlib.util.spec_from_file_location("prepare_romarg_nameservers", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_nameservers_accepts_two_cloudflare_hosts() -> None:
    module = load_module()

    nameservers, errors = module.validate_nameservers(
        ["First.ns.Cloudflare.com, second.ns.cloudflare.com."]
    )

    assert errors == []
    assert nameservers == ["first.ns.cloudflare.com.", "second.ns.cloudflare.com."]


def test_validate_nameservers_rejects_mixed_or_duplicate_hosts() -> None:
    module = load_module()

    duplicate, duplicate_errors = module.validate_nameservers(
        ["first.ns.cloudflare.com first.ns.cloudflare.com"]
    )
    mixed, mixed_errors = module.validate_nameservers(
        ["first.ns.cloudflare.com ns1.romarg.com"]
    )

    assert duplicate == ["first.ns.cloudflare.com."]
    assert "expected exactly 2 unique Cloudflare nameservers, got 1" in duplicate_errors
    assert mixed == ["first.ns.cloudflare.com.", "ns1.romarg.com."]
    assert "not a Cloudflare nameserver: ns1.romarg.com." in mixed_errors


def test_validated_card_tells_user_to_clear_extra_romarg_fields() -> None:
    module = load_module()

    lines = module.validated_lines(
        ["first.ns.cloudflare.com.", "second.ns.cloudflare.com."],
        "2026-05-28T00:00:00+00:00",
    )
    text = "\n".join(lines)

    assert "Nameserver 1: `first.ns.cloudflare.com.`" in text
    assert "Nameserver 2: `second.ns.cloudflare.com.`" in text
    assert "Leave every other nameserver field blank." in text
    assert "Remove all existing `romarg.com` nameservers" in text
