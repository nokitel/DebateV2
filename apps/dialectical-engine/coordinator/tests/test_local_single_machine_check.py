from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]


def load_local_single_machine_check_module() -> ModuleType:
    path = ROOT / "scripts" / "local_single_machine_check.py"
    spec = importlib.util.spec_from_file_location("local_single_machine_check", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_http_json_uses_browser_like_health_check_user_agent(monkeypatch) -> None:
    module = load_local_single_machine_check_module()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"ok": True}).encode("utf-8")

    def fake_urlopen(request, timeout: float):
        assert isinstance(request, module.urllib.request.Request)
        assert request.get_header("User-agent") == "Mozilla/5.0 (compatible; DialecticalHealthCheck/1.0; +https://dezbatere.ro)"
        assert timeout == 5.0
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    result = module.http_json("https://dezbatere.ro/api/backends/status")

    assert result["ok"] is True
