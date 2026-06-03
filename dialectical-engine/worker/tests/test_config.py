from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.client import CoordinatorClient
from app.config import WorkerConfig, load_config, load_file_config, save_config, update_config_file


ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_worker_config_defaults_do_not_enable_mock(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "worker.toml"
    monkeypatch.setenv("DIALECTICAL_WORKER_CONFIG", str(config_path))
    monkeypatch.delenv("DIALECTICAL_ENABLE_MOCK", raising=False)

    config = load_config()

    assert config.enable_mock is False
    assert config.enable_real_adapters is True


def test_worker_config_env_can_enable_mock(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "worker.toml"
    monkeypatch.setenv("DIALECTICAL_WORKER_CONFIG", str(config_path))
    monkeypatch.setenv("DIALECTICAL_ENABLE_MOCK", "1")

    config = load_config()

    assert config.enable_mock is True


def test_worker_config_allowed_models_can_come_from_env(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "worker.toml"
    monkeypatch.setenv("DIALECTICAL_WORKER_CONFIG", str(config_path))
    monkeypatch.setenv("DIALECTICAL_ALLOWED_MODELS", " codex-gpt-5.5, gemini-2.5-flash, codex-gpt-5.5, ")

    config = load_config()

    assert config.allowed_models == ["codex-gpt-5.5", "gemini-2.5-flash"]


def test_worker_config_mock_models_can_come_from_env(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "worker.toml"
    monkeypatch.setenv("DIALECTICAL_WORKER_CONFIG", str(config_path))
    monkeypatch.setenv("DIALECTICAL_MOCK_MODELS", " mock-alpha, mock-beta, mock-alpha, ")

    config = load_config()

    assert config.mock_models == ["mock-alpha", "mock-beta"]


def test_worker_file_model_lists_are_deduped_and_trimmed(tmp_path: Path) -> None:
    config_path = tmp_path / "worker.toml"
    config_path.write_text(
        "\n".join(
            [
                'allowed_models = [" codex-gpt-5.5 ", "gemini-2.5-flash", "codex-gpt-5.5", ""]',
                'mock_models = [" mock-alpha ", "mock-beta", "mock-alpha", ""]',
                "",
            ]
        )
    )

    config = load_file_config(config_path)

    assert config.allowed_models == ["codex-gpt-5.5", "gemini-2.5-flash"]
    assert config.mock_models == ["mock-alpha", "mock-beta"]


def test_save_config_does_not_persist_user_token(tmp_path: Path) -> None:
    config_path = tmp_path / "worker.toml"
    config = WorkerConfig(
        coordinator_url="https://dialectical.example.com",
        worker_id="worker-1",
        worker_token="worker_secret",
        user_token="user_secret",
        name="worker-a",
        mock_models=["mock-alpha", "mock-beta"],
        allowed_models=["codex-gpt-5.5"],
    )

    save_config(config, config_path)

    saved = config_path.read_text()
    assert "worker_token" in saved
    assert "worker_secret" in saved
    assert "user_token" not in saved
    assert "user_secret" not in saved
    assert "codex-gpt-5.5" in saved

    loaded = load_config(config_path)
    assert loaded.worker_token == "worker_secret"
    assert loaded.user_token is None
    assert loaded.mock_models == ["mock-alpha", "mock-beta"]
    assert loaded.allowed_models == ["codex-gpt-5.5"]


def test_update_config_file_preserves_worker_registration_and_removes_user_token(tmp_path: Path) -> None:
    config_path = tmp_path / "worker.toml"
    config_path.write_text(
        "\n".join(
            [
                'coordinator_url = "https://quick.trycloudflare.com"',
                'worker_id = "worker-1"',
                'worker_token = "worker_secret"',
                'user_token = "user_secret"',
                'name = "adesso-mbp"',
                'allowed_models = ["codex-gpt-5.5"]',
                "",
            ]
        )
    )

    updated = update_config_file(config_path, coordinator_url="https://debate.example.com/")

    assert updated.coordinator_url == "https://debate.example.com"
    assert updated.worker_id == "worker-1"
    assert updated.worker_token == "worker_secret"
    assert updated.name == "adesso-mbp"
    assert updated.allowed_models == ["codex-gpt-5.5"]
    saved = config_path.read_text()
    assert "user_token" not in saved
    assert "user_secret" not in saved


def test_update_config_file_can_change_allowed_models(tmp_path: Path) -> None:
    config_path = tmp_path / "worker.toml"
    save_config(
        WorkerConfig(
            coordinator_url="https://quick.trycloudflare.com",
            worker_id="worker-1",
            worker_token="worker_secret",
            allowed_models=["codex-gpt-5.5"],
        ),
        config_path,
    )

    updated = update_config_file(
        config_path,
        coordinator_url="https://debate.example.com",
        allowed_models=" codex-gpt-5.5, gemini-2.5-flash, codex-gpt-5.5, ",
    )

    assert updated.allowed_models == ["codex-gpt-5.5", "gemini-2.5-flash"]


def test_update_config_file_can_clear_allowed_models(tmp_path: Path) -> None:
    config_path = tmp_path / "worker.toml"
    save_config(
        WorkerConfig(
            coordinator_url="https://quick.trycloudflare.com",
            worker_id="worker-1",
            worker_token="worker_secret",
            allowed_models=["codex-gpt-5.5"],
        ),
        config_path,
    )

    updated = update_config_file(
        config_path,
        coordinator_url="https://debate.example.com",
        allowed_models="",
    )

    assert updated.allowed_models is None
    saved = config_path.read_text()
    assert "allowed_models" not in saved


def test_update_worker_config_named_https_guard_rejects_quick_tunnel() -> None:
    module = load_module(ROOT / "scripts" / "update_worker_config.py", "dialectical_update_worker_config_guard")

    assert (
        module.named_https_url_issue("https://temporary.trycloudflare.com")
        == "must be a stable named Cloudflare hostname, not a trycloudflare.com quick tunnel"
    )
    assert module.named_https_url_issue("https://debate.example.com/") is None


class RegisterResponse:
    def raise_for_status(self) -> None:
        return

    def json(self) -> dict[str, object]:
        return {
            "worker_id": "worker-1",
            "worker_token": "worker_secret",
            "name": "adesso-mbp",
            "capabilities": ["codex-gpt-5.5"],
        }


class RegisterHttpClient:
    def __init__(self) -> None:
        self.posts: list[dict[str, object]] = []

    async def post(self, path: str, headers: dict[str, str], json: dict[str, object]) -> RegisterResponse:
        self.posts.append({"path": path, "headers": headers, "json": json})
        return RegisterResponse()

    async def aclose(self) -> None:
        return


@pytest.mark.asyncio
async def test_register_can_defer_config_persistence_to_custom_path(tmp_path: Path, monkeypatch) -> None:
    default_path = tmp_path / "default-worker.toml"
    custom_path = tmp_path / "custom-worker.toml"
    monkeypatch.setenv("DIALECTICAL_WORKER_CONFIG", str(default_path))
    config = WorkerConfig(
        coordinator_url="https://dialectical.example.com",
        user_token="user_secret",
        name=" adesso-mbp ",
    )
    client = CoordinatorClient(config)
    fake_http = RegisterHttpClient()
    client.client = fake_http

    try:
        await client.register(["codex-gpt-5.5"], persist=False)
    finally:
        await client.aclose()

    assert fake_http.posts == [
        {
            "path": "/api/workers/register",
            "headers": {"Authorization": "Bearer user_secret"},
            "json": {"name": " adesso-mbp ", "capabilities": ["codex-gpt-5.5"]},
        }
    ]
    assert not default_path.exists()
    assert config.worker_id == "worker-1"
    assert config.worker_token == "worker_secret"
    assert config.name == "adesso-mbp"

    save_config(config, custom_path)

    assert not default_path.exists()
    loaded = load_config(custom_path)
    assert loaded.worker_id == "worker-1"
    assert loaded.worker_token == "worker_secret"
    assert loaded.user_token is None
    assert loaded.name == "adesso-mbp"


@pytest.mark.asyncio
async def test_register_save_path_overrides_default_config_path(tmp_path: Path, monkeypatch) -> None:
    default_path = tmp_path / "default-worker.toml"
    custom_path = tmp_path / "custom-worker.toml"
    monkeypatch.setenv("DIALECTICAL_WORKER_CONFIG", str(default_path))
    config = WorkerConfig(coordinator_url="https://dialectical.example.com", user_token="user_secret")
    client = CoordinatorClient(config)
    client.client = RegisterHttpClient()

    try:
        await client.register(["codex-gpt-5.5"], save_path=custom_path)
    finally:
        await client.aclose()

    assert not default_path.exists()
    assert custom_path.exists()
    loaded = load_config(custom_path)
    assert loaded.worker_id == "worker-1"
    assert loaded.worker_token == "worker_secret"
    assert loaded.user_token is None
