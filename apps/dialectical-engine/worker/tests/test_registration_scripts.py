from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    for module_name in [key for key in sys.modules if key == "app" or key.startswith("app.")]:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_register_worker_respects_allowed_models(tmp_path: Path, monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "register_worker.py", "dialectical_register_worker")
    captured: dict[str, object] = {}

    async def fake_detect_adapters(config):
        captured["detected_allowed_models"] = config.allowed_models
        return {model: object() for model in config.allowed_models or ["codex-gpt-5.5", "gemini-2.5-flash"]}

    class FakeCoordinatorClient:
        def __init__(self, config) -> None:
            self.config = config

        async def register(self, capabilities: list[str], *, persist: bool = True, save_path: Path | None = None) -> None:
            captured["registered_capabilities"] = capabilities
            captured["register_persist"] = persist
            captured["register_save_path"] = save_path
            self.config.worker_id = "worker-1"
            self.config.worker_token = "worker_secret"

        async def aclose(self) -> None:
            captured["closed"] = True

    def fake_save_config(config, path=None) -> None:
        captured["saved_allowed_models"] = config.allowed_models
        captured["saved_path"] = path

    monkeypatch.setattr(module, "user_token", lambda: "user_secret")
    monkeypatch.setattr(module, "detect_adapters", fake_detect_adapters)
    monkeypatch.setattr(module, "CoordinatorClient", FakeCoordinatorClient)
    monkeypatch.setattr(module, "save_config", fake_save_config)

    config_path = tmp_path / "worker.toml"
    args = SimpleNamespace(
        coordinator_url="https://debate.example.com",
        name="adesso-mbp",
        config=str(config_path),
        enable_mock=False,
        allowed_models=" codex-gpt-5.5, gemini-2.5-flash, codex-gpt-5.5, ",
    )

    asyncio.run(module.run(args))

    assert captured["detected_allowed_models"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["registered_capabilities"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["register_persist"] is False
    assert captured["register_save_path"] is None
    assert captured["saved_allowed_models"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["saved_path"] == config_path
    assert captured["closed"] is True


def test_register_worker_rejects_empty_detected_capabilities(tmp_path: Path, monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "register_worker.py", "dialectical_register_worker_empty")

    def unexpected_user_token() -> str:
        raise AssertionError("user token should not be requested without healthy capabilities")

    async def fake_detect_adapters(config):
        return {}

    class UnexpectedCoordinatorClient:
        def __init__(self, config) -> None:
            raise AssertionError("client should not be created without capabilities")

    monkeypatch.setattr(module, "user_token", unexpected_user_token)
    monkeypatch.setattr(module, "detect_adapters", fake_detect_adapters)
    monkeypatch.setattr(module, "CoordinatorClient", UnexpectedCoordinatorClient)

    args = SimpleNamespace(
        coordinator_url="https://debate.example.com",
        name="adesso-mbp",
        config=str(tmp_path / "worker.toml"),
        enable_mock=False,
        allowed_models="codex-gpt-5.5",
    )

    with pytest.raises(RuntimeError, match="no healthy adapters detected for allowed models: codex-gpt-5.5"):
        asyncio.run(module.run(args))


def test_register_worker_user_token_reports_noninteractive_missing_token(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "register_worker.py", "dialectical_register_worker_noninteractive_token")
    monkeypatch.delenv("DIALECTICAL_USER_TOKEN", raising=False)
    monkeypatch.delenv("USER_TOKEN", raising=False)

    class NonInteractiveStdin:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(module.sys, "stdin", NonInteractiveStdin())

    with pytest.raises(RuntimeError, match="DIALECTICAL_USER_TOKEN or USER_TOKEN is required"):
        module.user_token()


def test_register_worker_named_https_guard_rejects_quick_tunnel_before_token(tmp_path: Path, monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "register_worker.py", "dialectical_register_worker_named_guard")

    def unexpected_user_token() -> str:
        raise AssertionError("user token should not be requested for an invalid named URL")

    async def unexpected_detect_adapters(config):
        raise AssertionError("adapter detection should not run for an invalid named URL")

    monkeypatch.setattr(module, "user_token", unexpected_user_token)
    monkeypatch.setattr(module, "detect_adapters", unexpected_detect_adapters)

    args = SimpleNamespace(
        coordinator_url="https://temporary.trycloudflare.com",
        name="adesso-mbp",
        config=str(tmp_path / "worker.toml"),
        enable_mock=False,
        allowed_models="codex-gpt-5.5",
        require_named_https=True,
    )

    with pytest.raises(RuntimeError, match="trycloudflare.com quick tunnel"):
        asyncio.run(module.run(args))


def test_install_worker_respects_allowed_models(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker")
    captured: dict[str, object] = {}

    async def fake_detect_adapters(config):
        captured["detected_allowed_models"] = config.allowed_models
        return {model: object() for model in config.allowed_models or ["codex-gpt-5.5", "gemini-2.5-flash"]}

    class FakeCoordinatorClient:
        def __init__(self, config) -> None:
            self.config = config

        async def register(self, capabilities: list[str], *, persist: bool = True, save_path: Path | None = None) -> None:
            captured["registered_capabilities"] = capabilities
            captured["register_persist"] = persist
            captured["register_save_path"] = save_path
            self.config.worker_id = "worker-1"
            self.config.worker_token = "worker_secret"

        async def heartbeat(self, capabilities: list[str]) -> None:
            captured["heartbeat_capabilities"] = capabilities

        async def aclose(self) -> None:
            captured["closed"] = True

    def fake_save_config(config, path=None) -> None:
        captured["saved_allowed_models"] = config.allowed_models
        captured["saved_path"] = path

    monkeypatch.setattr(module, "user_token", lambda: "user_secret")
    monkeypatch.setattr(module, "load_file_config", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(module, "detect_adapters", fake_detect_adapters)
    monkeypatch.setattr(module, "CoordinatorClient", FakeCoordinatorClient)
    monkeypatch.setattr(module, "save_config", fake_save_config)

    args = SimpleNamespace(
        coordinator_url="https://debate.example.com",
        name="adesso-mbp",
        python="/python",
        install_service=False,
        enable_mock=False,
        allowed_models=" codex-gpt-5.5, gemini-2.5-flash, codex-gpt-5.5, ",
    )

    asyncio.run(module.run(args))

    assert captured["detected_allowed_models"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["registered_capabilities"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["heartbeat_capabilities"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["register_persist"] is False
    assert captured["register_save_path"] is None
    assert captured["saved_allowed_models"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["saved_path"] is None
    assert captured["closed"] is True


def test_install_worker_user_token_reports_noninteractive_new_registration(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker_noninteractive_token")
    monkeypatch.delenv("DIALECTICAL_USER_TOKEN", raising=False)
    monkeypatch.delenv("USER_TOKEN", raising=False)

    class NonInteractiveStdin:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(module.sys, "stdin", NonInteractiveStdin())

    with pytest.raises(RuntimeError, match="required when registering a new worker"):
        module.user_token()


def test_install_worker_reuses_matching_registration_without_user_token(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker_reuse")
    captured: dict[str, object] = {}

    async def fake_detect_adapters(config):
        captured["detected_allowed_models"] = config.allowed_models
        return {model: object() for model in config.allowed_models or ["codex-gpt-5.5", "gemini-2.5-flash"]}

    class FakeCoordinatorClient:
        def __init__(self, config) -> None:
            self.config = config
            captured["client_worker_id"] = config.worker_id
            captured["client_worker_token"] = config.worker_token

        async def register(self, capabilities: list[str], *, persist: bool = True, save_path: Path | None = None) -> None:
            captured["register_capabilities"] = capabilities
            captured["register_user_token"] = self.config.user_token
            captured["register_worker_id"] = self.config.worker_id
            captured["register_persist"] = persist
            captured["register_save_path"] = save_path

        async def heartbeat(self, capabilities: list[str]) -> None:
            captured["heartbeat_capabilities"] = capabilities

        async def aclose(self) -> None:
            captured["closed"] = True

    def unexpected_user_token() -> str:
        raise AssertionError("user token should not be requested when a matching worker registration exists")

    def fake_save_config(config, path=None) -> None:
        captured["saved_worker_id"] = config.worker_id
        captured["saved_worker_token"] = config.worker_token
        captured["saved_allowed_models"] = config.allowed_models
        captured["saved_path"] = path

    monkeypatch.setattr(module, "user_token", unexpected_user_token)
    monkeypatch.setattr(
        module,
        "load_file_config",
        lambda: module.WorkerConfig(
            coordinator_url="https://debate.example.com/",
            name="adesso-mbp",
            worker_id="worker-existing",
            worker_token="worker-secret",
        ),
    )
    monkeypatch.setattr(module, "detect_adapters", fake_detect_adapters)
    monkeypatch.setattr(module, "CoordinatorClient", FakeCoordinatorClient)
    monkeypatch.setattr(module, "save_config", fake_save_config)

    args = SimpleNamespace(
        coordinator_url="https://debate.example.com",
        name="adesso-mbp",
        python="/python",
        install_service=False,
        enable_mock=False,
        allowed_models="codex-gpt-5.5,gemini-2.5-flash",
    )

    asyncio.run(module.run(args))

    assert captured["detected_allowed_models"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["client_worker_id"] == "worker-existing"
    assert captured["client_worker_token"] == "worker-secret"
    assert captured["register_user_token"] is None
    assert captured["register_worker_id"] == "worker-existing"
    assert captured["register_capabilities"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["heartbeat_capabilities"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["register_persist"] is False
    assert captured["register_save_path"] is None
    assert captured["saved_worker_id"] == "worker-existing"
    assert captured["saved_worker_token"] == "worker-secret"
    assert captured["saved_allowed_models"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["saved_path"] is None
    assert captured["closed"] is True


def test_install_worker_preserves_existing_allowlist_when_allowed_models_omitted(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker_preserve_allowlist")
    captured: dict[str, object] = {}

    async def fake_detect_adapters(config):
        captured["detected_allowed_models"] = config.allowed_models
        return {model: object() for model in config.allowed_models or ["codex-gpt-5.5", "gemini-2.5-flash"]}

    class FakeCoordinatorClient:
        def __init__(self, config) -> None:
            self.config = config

        async def register(self, capabilities: list[str], *, persist: bool = True, save_path: Path | None = None) -> None:
            captured["registered_capabilities"] = capabilities
            captured["register_user_token"] = self.config.user_token

        async def heartbeat(self, capabilities: list[str]) -> None:
            captured["heartbeat_capabilities"] = capabilities

        async def aclose(self) -> None:
            captured["closed"] = True

    def unexpected_user_token() -> str:
        raise AssertionError("user token should not be requested when a matching worker registration exists")

    def fake_save_config(config, path=None) -> None:
        captured["saved_allowed_models"] = config.allowed_models

    monkeypatch.setattr(module, "user_token", unexpected_user_token)
    monkeypatch.setattr(
        module,
        "load_file_config",
        lambda: module.WorkerConfig(
            coordinator_url="https://debate.example.com",
            name="adesso-mbp",
            worker_id="worker-existing",
            worker_token="worker-secret",
            allowed_models=["codex-gpt-5.5"],
        ),
    )
    monkeypatch.setattr(module, "detect_adapters", fake_detect_adapters)
    monkeypatch.setattr(module, "CoordinatorClient", FakeCoordinatorClient)
    monkeypatch.setattr(module, "save_config", fake_save_config)

    args = SimpleNamespace(
        coordinator_url="https://debate.example.com",
        name="adesso-mbp",
        python="/python",
        install_service=False,
        enable_mock=False,
        allowed_models=None,
    )

    asyncio.run(module.run(args))

    assert captured["detected_allowed_models"] == ["codex-gpt-5.5"]
    assert captured["registered_capabilities"] == ["codex-gpt-5.5"]
    assert captured["heartbeat_capabilities"] == ["codex-gpt-5.5"]
    assert captured["register_user_token"] is None
    assert captured["saved_allowed_models"] == ["codex-gpt-5.5"]
    assert captured["closed"] is True


def test_install_worker_clears_existing_allowlist_when_allowed_models_empty(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker_clear_allowlist")
    captured: dict[str, object] = {}

    async def fake_detect_adapters(config):
        captured["detected_allowed_models"] = config.allowed_models
        return {"codex-gpt-5.5": object(), "gemini-2.5-flash": object()}

    class FakeCoordinatorClient:
        def __init__(self, config) -> None:
            self.config = config

        async def register(self, capabilities: list[str], *, persist: bool = True, save_path: Path | None = None) -> None:
            captured["registered_capabilities"] = capabilities

        async def heartbeat(self, capabilities: list[str]) -> None:
            captured["heartbeat_capabilities"] = capabilities

        async def aclose(self) -> None:
            captured["closed"] = True

    def fake_save_config(config, path=None) -> None:
        captured["saved_allowed_models"] = config.allowed_models

    monkeypatch.setattr(module, "user_token", lambda: (_ for _ in ()).throw(AssertionError("unexpected token prompt")))
    monkeypatch.setattr(
        module,
        "load_file_config",
        lambda: module.WorkerConfig(
            coordinator_url="https://debate.example.com",
            name="adesso-mbp",
            worker_id="worker-existing",
            worker_token="worker-secret",
            allowed_models=["codex-gpt-5.5"],
        ),
    )
    monkeypatch.setattr(module, "detect_adapters", fake_detect_adapters)
    monkeypatch.setattr(module, "CoordinatorClient", FakeCoordinatorClient)
    monkeypatch.setattr(module, "save_config", fake_save_config)

    args = SimpleNamespace(
        coordinator_url="https://debate.example.com",
        name="adesso-mbp",
        python="/python",
        install_service=False,
        enable_mock=False,
        allowed_models="",
    )

    asyncio.run(module.run(args))

    assert captured["detected_allowed_models"] is None
    assert captured["registered_capabilities"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["heartbeat_capabilities"] == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert captured["saved_allowed_models"] is None
    assert captured["closed"] is True


def test_install_worker_rejects_empty_detected_capabilities(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker_empty")

    def unexpected_user_token() -> str:
        raise AssertionError("user token should not be requested without healthy capabilities")

    async def fake_detect_adapters(config):
        return {}

    class UnexpectedCoordinatorClient:
        def __init__(self, config) -> None:
            raise AssertionError("client should not be created without capabilities")

    monkeypatch.setattr(module, "user_token", unexpected_user_token)
    monkeypatch.setattr(module, "detect_adapters", fake_detect_adapters)
    monkeypatch.setattr(module, "CoordinatorClient", UnexpectedCoordinatorClient)

    args = SimpleNamespace(
        coordinator_url="https://debate.example.com",
        name="adesso-mbp",
        python="/python",
        install_service=False,
        enable_mock=False,
        allowed_models="codex-gpt-5.5",
    )

    with pytest.raises(RuntimeError, match="no healthy adapters detected for allowed models: codex-gpt-5.5"):
        asyncio.run(module.run(args))


def test_install_worker_named_https_guard_rejects_local_url_before_token(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker_named_guard")

    def unexpected_user_token() -> str:
        raise AssertionError("user token should not be requested for an invalid named URL")

    async def unexpected_detect_adapters(config):
        raise AssertionError("adapter detection should not run for an invalid named URL")

    monkeypatch.setattr(module, "user_token", unexpected_user_token)
    monkeypatch.setattr(module, "detect_adapters", unexpected_detect_adapters)

    args = SimpleNamespace(
        coordinator_url="http://127.0.0.1:8000",
        name="adesso-mbp",
        python="/python",
        install_service=False,
        enable_mock=False,
        allowed_models="codex-gpt-5.5",
        require_named_https=True,
    )

    with pytest.raises(RuntimeError, match="must be an HTTPS URL"):
        asyncio.run(module.run(args))


def test_install_worker_render_launchd_service_includes_present_adapter_api_env(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker_render_env")
    monkeypatch.setattr(module, "default_launchd_path", lambda: "/usr/bin:/bin")
    monkeypatch.setattr(module, "default_python_dyld_library_path", lambda: "")

    rendered = module.render_launchd_service(
        "/python",
        {
            "GEMINI_API_KEY": "gemini-secret",
            "XAI_API_KEY": "xai-secret",
        },
    )

    assert "<key>GEMINI_API_KEY</key>" in rendered
    assert "<string>gemini-secret</string>" in rendered
    assert "<key>GOOGLE_GENAI_USE_GCA</key>" in rendered
    assert "<string>true</string>" in rendered
    assert "<key>XAI_API_KEY</key>" in rendered
    assert "<string>xai-secret</string>" in rendered
    assert "__ADAPTER_API_ENV__" not in rendered


def test_install_worker_render_launchd_service_omits_absent_adapter_api_env(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker_render_no_env")
    monkeypatch.setattr(module, "default_launchd_path", lambda: "/usr/bin:/bin")
    monkeypatch.setattr(module, "default_python_dyld_library_path", lambda: "")

    rendered = module.render_launchd_service("/python", {})

    assert "GEMINI_API_KEY" not in rendered
    assert "<key>GOOGLE_GENAI_USE_GCA</key>" in rendered
    assert "<string>true</string>" in rendered
    assert "XAI_API_KEY" not in rendered
    assert "__ADAPTER_API_ENV__" not in rendered


def test_install_worker_render_launchd_service_filters_placeholder_adapter_api_env(monkeypatch) -> None:
    module = load_module(ROOT / "scripts" / "install_worker.py", "dialectical_install_worker_render_placeholder_env")
    monkeypatch.setattr(module, "default_launchd_path", lambda: "/usr/bin:/bin")
    monkeypatch.setattr(module, "default_python_dyld_library_path", lambda: "")
    monkeypatch.setenv("GEMINI_API_KEY", "<optional-google-ai-studio-api-key>")
    monkeypatch.setenv("XAI_API_KEY", "xai-secret")

    rendered = module.render_launchd_service("/python")

    assert "GEMINI_API_KEY" not in rendered
    assert "<optional-google-ai-studio-api-key>" not in rendered
    assert "<key>XAI_API_KEY</key>" in rendered
    assert "<string>xai-secret</string>" in rendered
    assert "__ADAPTER_API_ENV__" not in rendered
