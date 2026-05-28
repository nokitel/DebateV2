from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "dialectical_verify_public_endpoint",
        ROOT / "scripts" / "verify_public_endpoint.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_named_https_url_issue_accepts_named_origin() -> None:
    module = load_module()

    assert module.named_https_url_issue("https://debate.example.com") is None


@pytest.mark.parametrize(
    ("url", "issue"),
    [
        ("https://debate.<your-domain>", "placeholder URL"),
        ("http://debate.example.com", "must be an HTTPS URL"),
        ("https://localhost:8000", "must use a DNS hostname such as debate.example.com"),
        (
            "https://temporary.trycloudflare.com",
            "must be a stable named Cloudflare hostname, not a trycloudflare.com quick tunnel",
        ),
        ("https://debate.example.com/path", "must be the coordinator origin without a path, query, or fragment"),
    ],
)
def test_named_https_url_issue_rejects_non_production_origins(url: str, issue: str) -> None:
    module = load_module()

    assert module.named_https_url_issue(url) == issue


def test_status_detail_reports_worker_names() -> None:
    module = load_module()

    assert module.status_detail({"workers": [{"name": "mac-mini"}, {"name": "adesso-mbp"}]}) == (
        "adesso-mbp, mac-mini"
    )


def test_status_detail_requires_worker_list() -> None:
    module = load_module()

    with pytest.raises(module.EndpointError, match="workers list"):
        module.status_detail({"workers": {}})
