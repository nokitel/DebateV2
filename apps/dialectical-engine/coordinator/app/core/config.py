from __future__ import annotations

import os
import secrets
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - runtime target is 3.12+, tests may use older macOS Python.
    import tomli as tomllib

DEFAULT_COORDINATOR_DIR = Path("~/.dialectical").expanduser()
DEFAULT_DB_PATH = DEFAULT_COORDINATOR_DIR / "db.sqlite3"
DEFAULT_CONFIG_PATH = DEFAULT_COORDINATOR_DIR / "coordinator.toml"
DEFAULT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
RUNTIME_SETTINGS_KEY = "runtime_settings"
MAX_PUBLIC_RATE_LIMIT_PER_MINUTE = 100_000
MAX_WORKER_POLL_SECONDS = 300
MAX_WORKER_OFFLINE_SECONDS = 3_600
MAX_JOB_FALLBACK_SECONDS = 3_600
MAX_GROK_MONTHLY_CAP_USD = 1_000_000.0


DEFAULT_ROUTING: dict[str, dict[str, Any]] = {
    "decomposer": {
        "primary": "mock-local",
        "fallback": ["claude-sonnet-4-6", "codex-gpt-5.5"],
    },
    "proposer": {
        "pool": [
            "mock-local",
            "claude-sonnet-4-6",
            "codex-gpt-5.5",
            "gemini-2.5-flash",
            "grok-4",
            "ollama:qwen-3.6",
            "ollama:gemma-4-9b",
        ],
        "strategy": "round_robin",
    },
    "opponent": {
        "pool": [
            "mock-local",
            "claude-sonnet-4-6",
            "codex-gpt-5.5",
            "gemini-2.5-flash",
            "grok-4",
            "ollama:qwen-3.6",
            "ollama:gemma-4-9b",
        ],
        "strategy": "round_robin",
        "constraint": "not_same_as_claim_author",
    },
    "synthesizer": {
        "primary": "mock-local",
        "fallback": ["claude-sonnet-4-6", "codex-gpt-5.5"],
    },
}


@dataclass
class Settings:
    home: Path = DEFAULT_COORDINATOR_DIR
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    user_token: str | None = None
    public_base_url: str = "http://localhost:8000"
    web_origin: str = "http://localhost:3000"
    public_rate_limit_per_minute: int = 100
    worker_poll_seconds: int = 30
    worker_offline_seconds: int = 90
    job_fallback_seconds: int = 60
    routing: dict[str, dict[str, Any]] = field(default_factory=lambda: deepcopy(DEFAULT_ROUTING))
    grok_monthly_cap_usd: float = 25.0
    openai_api_key: str | None = None
    openai_model: str = "codex-gpt-5.5"
    single_shot_provider: str = "codex"
    codex_command: str = "codex"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = {**base}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return default
    return max(minimum, min(maximum, parsed))


def clean_string(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    cleaned = value.strip()
    return cleaned or default


def load_dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    value = os.getenv(name)
    return bounded_int(value, default, minimum, maximum) if value is not None else default


def float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    value = os.getenv(name)
    return bounded_float(value, default, minimum, maximum) if value is not None else default


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.getenv("DIALECTICAL_COORDINATOR_CONFIG", DEFAULT_CONFIG_PATH)).expanduser()
    dotenv_values = {
        **load_dotenv_values(DEFAULT_ENV_PATH),
        **load_dotenv_values(Path(".env")),
    }
    home = Path(os.getenv("DIALECTICAL_HOME", str(DEFAULT_COORDINATOR_DIR))).expanduser()
    db_url = os.getenv("DIALECTICAL_DATABASE_URL", f"sqlite:///{home / 'db.sqlite3'}")
    settings = Settings(home=home, database_url=db_url)

    if path.exists():
        raw = tomllib.loads(path.read_text())
        settings.public_base_url = clean_string(raw.get("public_base_url"), settings.public_base_url)
        settings.web_origin = clean_string(raw.get("web_origin"), settings.web_origin)
        settings.public_rate_limit_per_minute = bounded_int(
            raw.get("public_rate_limit_per_minute"),
            settings.public_rate_limit_per_minute,
            1,
            MAX_PUBLIC_RATE_LIMIT_PER_MINUTE,
        )
        settings.worker_poll_seconds = bounded_int(
            raw.get("worker_poll_seconds"),
            settings.worker_poll_seconds,
            1,
            MAX_WORKER_POLL_SECONDS,
        )
        settings.worker_offline_seconds = bounded_int(
            raw.get("worker_offline_seconds"),
            settings.worker_offline_seconds,
            5,
            MAX_WORKER_OFFLINE_SECONDS,
        )
        settings.job_fallback_seconds = bounded_int(
            raw.get("job_fallback_seconds"),
            settings.job_fallback_seconds,
            1,
            MAX_JOB_FALLBACK_SECONDS,
        )
        settings.grok_monthly_cap_usd = bounded_float(
            raw.get("grok_monthly_cap_usd"),
            settings.grok_monthly_cap_usd,
            0.0,
            MAX_GROK_MONTHLY_CAP_USD,
        )
        if isinstance(raw.get("roles"), dict):
            settings.routing = deep_merge(deepcopy(DEFAULT_ROUTING), raw["roles"])

    settings.user_token = os.getenv("DIALECTICAL_USER_TOKEN")
    settings.openai_api_key = os.getenv("OPENAI_API_KEY", dotenv_values.get("OPENAI_API_KEY"))
    settings.openai_model = clean_string(
        os.getenv("OPENAI_MODEL", dotenv_values.get("OPENAI_MODEL")),
        settings.openai_model,
    )
    settings.public_base_url = clean_string(os.getenv("DIALECTICAL_PUBLIC_BASE_URL"), settings.public_base_url)
    settings.web_origin = clean_string(os.getenv("DIALECTICAL_WEB_ORIGIN"), settings.web_origin)
    settings.public_rate_limit_per_minute = int_env(
        "DIALECTICAL_PUBLIC_RATE_LIMIT_PER_MINUTE",
        settings.public_rate_limit_per_minute,
        1,
        MAX_PUBLIC_RATE_LIMIT_PER_MINUTE,
    )
    settings.worker_poll_seconds = int_env(
        "DIALECTICAL_WORKER_POLL_SECONDS",
        settings.worker_poll_seconds,
        1,
        MAX_WORKER_POLL_SECONDS,
    )
    settings.worker_offline_seconds = int_env(
        "DIALECTICAL_WORKER_OFFLINE_SECONDS",
        settings.worker_offline_seconds,
        5,
        MAX_WORKER_OFFLINE_SECONDS,
    )
    settings.job_fallback_seconds = int_env(
        "DIALECTICAL_JOB_FALLBACK_SECONDS",
        settings.job_fallback_seconds,
        1,
        MAX_JOB_FALLBACK_SECONDS,
    )
    settings.grok_monthly_cap_usd = float_env(
        "DIALECTICAL_GROK_MONTHLY_CAP_USD",
        settings.grok_monthly_cap_usd,
        0.0,
        MAX_GROK_MONTHLY_CAP_USD,
    )
    settings.single_shot_provider = clean_string(
        os.getenv("DIALECTICAL_SINGLE_SHOT_PROVIDER"), settings.single_shot_provider
    ).lower()
    settings.codex_command = clean_string(os.getenv("CODEX_COMMAND"), settings.codex_command)
    return settings


def ensure_home(settings: Settings) -> None:
    settings.home.mkdir(parents=True, exist_ok=True)


def new_secret_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"
