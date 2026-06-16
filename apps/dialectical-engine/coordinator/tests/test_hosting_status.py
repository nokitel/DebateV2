from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]


def load_hosting_status_module() -> ModuleType:
    path = ROOT / "scripts" / "hosting_status.py"
    spec = importlib.util.spec_from_file_location("hosting_status", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_surface_checks_home_and_static_asset(monkeypatch) -> None:
    module = load_hosting_status_module()

    def fake_text(url: str, *, timeout: int = 5) -> dict[str, object]:
        return {
            "ok": True,
            "status": 200,
            "prefix": '<link href="/_next/static/chunks/app.js" rel="preload">',
        }

    def fake_head(url: str, *, timeout: int = 5) -> dict[str, object]:
        assert url == "https://dezbatere.ro/_next/static/chunks/app.js"
        return {"ok": True, "status": 200}

    monkeypatch.setattr(module, "http_text", fake_text)
    monkeypatch.setattr(module, "http_head", fake_head)

    result = module.web_surface("https://dezbatere.ro")

    assert result["ok"] is True
    assert result["static_assets"]["assets"] == ["/_next/static/chunks/app.js"]
    assert result["static_assets"]["sample"] == {"ok": True, "status": 200}


def test_http_json_uses_browser_like_health_check_user_agent(monkeypatch) -> None:
    module = load_hosting_status_module()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"ok": True}).encode("utf-8")

    def fake_urlopen(request, timeout: int):
        assert isinstance(request, module.urllib.request.Request)
        assert request.get_header("User-agent") == "Mozilla/5.0 (compatible; DialecticalHealthCheck/1.0; +https://dezbatere.ro)"
        assert timeout == 5
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    result = module.http_json("https://dezbatere.ro/api/backends/status")

    assert result["ok"] is True


def test_next_action_reports_named_web_failure_after_api_ready() -> None:
    module = load_hosting_status_module()

    action = module.next_action(
        {"ok": True},
        {"ok": True},
        {"delegated_to_cloudflare": True},
        {"cert_exists": True, "named_tunnel_ready": True, "service_loaded": True},
        {"ok": True},
        {"ok": False},
    )

    assert "Named tunnel API works" in action
    assert "https://dezbatere.ro/" in action


def test_next_action_points_to_romarg_nameserver_helper_before_delegation() -> None:
    module = load_hosting_status_module()

    action = module.next_action(
        {"ok": True},
        {"ok": True},
        {"delegated_to_cloudflare": False},
        {"cert_exists": False, "named_tunnel_ready": False, "service_loaded": False},
        {"ok": False},
        {"ok": False},
    )

    assert "make prepare-romarg-nameservers" in action
    assert "make wait-dezbatere-dns" in action
