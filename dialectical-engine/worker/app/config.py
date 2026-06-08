from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - runtime target is 3.12+, tests may use older macOS Python.
    import tomli as tomllib

try:
    import tomli_w
except ImportError:  # pragma: no cover
    tomli_w = None

DEFAULT_WORKER_DIR = Path("~/.dialectical-worker").expanduser()
DEFAULT_CONFIG_PATH = DEFAULT_WORKER_DIR / "config.toml"
_UNSET = object()


def as_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() not in {"0", "false", "no"}


def parse_model_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = [value]
    models: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        model = str(candidate).strip()
        if not model or model in seen:
            continue
        models.append(model)
        seen.add(model)
    return models or None


def resolved_config_path(path: Path | None = None) -> Path:
    return (path or Path(os.getenv("DIALECTICAL_WORKER_CONFIG", DEFAULT_CONFIG_PATH))).expanduser()


def default_worker_name() -> str:
    return socket.gethostname()


@dataclass
class WorkerConfig:
    coordinator_url: str = "http://localhost:8000"
    worker_id: str | None = None
    worker_token: str | None = None
    user_token: str | None = None
    name: str = default_worker_name()
    enable_mock: bool = False
    enable_real_adapters: bool = True
    mock_models: list[str] | None = None
    allowed_models: list[str] | None = None
    heartbeat_seconds: int = 30
    request_timeout_seconds: int = 60


def load_config(path: Path | None = None) -> WorkerConfig:
    path = resolved_config_path(path)
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    return WorkerConfig(
        coordinator_url=os.getenv("DIALECTICAL_COORDINATOR_URL", data.get("coordinator_url", "http://localhost:8000")),
        worker_id=os.getenv("DIALECTICAL_WORKER_ID", data.get("worker_id")),
        worker_token=os.getenv("DIALECTICAL_WORKER_TOKEN", data.get("worker_token")),
        user_token=os.getenv("DIALECTICAL_USER_TOKEN", data.get("user_token")),
        name=os.getenv("DIALECTICAL_WORKER_NAME", data.get("name", default_worker_name())),
        enable_mock=as_bool(os.getenv("DIALECTICAL_ENABLE_MOCK"), as_bool(data.get("enable_mock", False))),
        enable_real_adapters=as_bool(
            os.getenv("DIALECTICAL_ENABLE_REAL_ADAPTERS"),
            as_bool(data.get("enable_real_adapters", True)),
        ),
        mock_models=parse_model_list(os.getenv("DIALECTICAL_MOCK_MODELS", data.get("mock_models"))),
        allowed_models=parse_model_list(os.getenv("DIALECTICAL_ALLOWED_MODELS", data.get("allowed_models"))),
        heartbeat_seconds=int(data.get("heartbeat_seconds", 30)),
        request_timeout_seconds=int(data.get("request_timeout_seconds", 60)),
    )


def save_config(config: WorkerConfig, path: Path | None = None) -> None:
    path = resolved_config_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "coordinator_url": config.coordinator_url,
        "worker_id": config.worker_id,
        "worker_token": config.worker_token,
        "name": config.name,
        "enable_mock": config.enable_mock,
        "enable_real_adapters": config.enable_real_adapters,
        "mock_models": config.mock_models,
        "allowed_models": config.allowed_models,
        "heartbeat_seconds": config.heartbeat_seconds,
        "request_timeout_seconds": config.request_timeout_seconds,
    }
    data = {key: value for key, value in data.items() if value is not None}
    if tomli_w is not None:
        path.write_text(tomli_w.dumps(data))
        return
    lines = []
    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, int):
            lines.append(f"{key} = {value}")
        elif isinstance(value, list):
            lines.append(f"{key} = [{', '.join(json.dumps(str(item)) for item in value)}]")
        elif value is not None:
            lines.append(f'{key} = "{value}"')
    path.write_text("\n".join(lines) + "\n")


def load_file_config(path: Path | None = None) -> WorkerConfig:
    path = resolved_config_path(path)
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    return WorkerConfig(
        coordinator_url=data.get("coordinator_url", "http://localhost:8000"),
        worker_id=data.get("worker_id"),
        worker_token=data.get("worker_token"),
        user_token=data.get("user_token"),
        name=data.get("name", default_worker_name()),
        enable_mock=as_bool(data.get("enable_mock", False)),
        enable_real_adapters=as_bool(data.get("enable_real_adapters", True)),
        mock_models=parse_model_list(data.get("mock_models")),
        allowed_models=parse_model_list(data.get("allowed_models")),
        heartbeat_seconds=int(data.get("heartbeat_seconds", 30)),
        request_timeout_seconds=int(data.get("request_timeout_seconds", 60)),
    )


def update_config_file(
    path: Path | None = None,
    *,
    coordinator_url: str | None = None,
    allowed_models: object = _UNSET,
) -> WorkerConfig:
    if coordinator_url is None and allowed_models is _UNSET:
        raise ValueError("set at least one worker config field")

    config_path = resolved_config_path(path)
    config = load_file_config(config_path)
    if coordinator_url is not None:
        cleaned_url = coordinator_url.strip().rstrip("/")
        if not cleaned_url:
            raise ValueError("coordinator_url cannot be empty")
        config.coordinator_url = cleaned_url
    if allowed_models is not _UNSET:
        config.allowed_models = parse_model_list(allowed_models)

    save_config(config, config_path)
    return load_file_config(config_path)
