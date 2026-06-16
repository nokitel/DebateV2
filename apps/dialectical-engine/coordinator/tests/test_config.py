from __future__ import annotations

from pathlib import Path

from app.core.config import DEFAULT_ROUTING, load_settings


def clear_config_env(monkeypatch) -> None:
    for name in (
        "DIALECTICAL_COORDINATOR_CONFIG",
        "DIALECTICAL_HOME",
        "DIALECTICAL_DATABASE_URL",
        "DIALECTICAL_USER_TOKEN",
        "DIALECTICAL_PUBLIC_BASE_URL",
        "DIALECTICAL_WEB_ORIGIN",
        "DIALECTICAL_PUBLIC_RATE_LIMIT_PER_MINUTE",
        "DIALECTICAL_WORKER_POLL_SECONDS",
        "DIALECTICAL_WORKER_OFFLINE_SECONDS",
        "DIALECTICAL_JOB_FALLBACK_SECONDS",
        "DIALECTICAL_GROK_MONTHLY_CAP_USD",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "DIALECTICAL_SINGLE_SHOT_PROVIDER",
        "CODEX_COMMAND",
    ):
        monkeypatch.delenv(name, raising=False)


def test_load_settings_tolerates_malformed_file_values(tmp_path: Path, monkeypatch) -> None:
    clear_config_env(monkeypatch)
    config_path = tmp_path / "coordinator.toml"
    config_path.write_text(
        "\n".join(
            [
                "public_base_url = 123",
                'web_origin = ""',
                'public_rate_limit_per_minute = "not-an-int"',
                "worker_poll_seconds = -5",
                "worker_offline_seconds = 1",
                "job_fallback_seconds = 999999",
                "grok_monthly_cap_usd = -10",
                'roles = "not-a-table"',
                "",
            ]
        )
    )

    settings = load_settings(config_path)

    assert settings.public_base_url == "http://localhost:8000"
    assert settings.web_origin == "http://localhost:3000"
    assert settings.public_rate_limit_per_minute == 100
    assert settings.worker_poll_seconds == 1
    assert settings.worker_offline_seconds == 5
    assert settings.job_fallback_seconds == 3600
    assert settings.grok_monthly_cap_usd == 0.0
    assert settings.routing == DEFAULT_ROUTING


def test_load_settings_tolerates_malformed_env_values(tmp_path: Path, monkeypatch) -> None:
    clear_config_env(monkeypatch)
    monkeypatch.setenv("DIALECTICAL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DIALECTICAL_PUBLIC_BASE_URL", "   ")
    monkeypatch.setenv("DIALECTICAL_WEB_ORIGIN", "https://debate.example.com ")
    monkeypatch.setenv("DIALECTICAL_PUBLIC_RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("DIALECTICAL_WORKER_POLL_SECONDS", "not-an-int")
    monkeypatch.setenv("DIALECTICAL_WORKER_OFFLINE_SECONDS", "999999")
    monkeypatch.setenv("DIALECTICAL_JOB_FALLBACK_SECONDS", "-10")
    monkeypatch.setenv("DIALECTICAL_GROK_MONTHLY_CAP_USD", "nan")

    settings = load_settings(tmp_path / "missing.toml")

    assert settings.home == tmp_path / "home"
    assert settings.public_base_url == "http://localhost:8000"
    assert settings.web_origin == "https://debate.example.com"
    assert settings.public_rate_limit_per_minute == 1
    assert settings.worker_poll_seconds == 30
    assert settings.worker_offline_seconds == 3600
    assert settings.job_fallback_seconds == 1
    assert settings.grok_monthly_cap_usd == 25.0


def test_default_routing_is_not_shared_between_settings_loads(tmp_path: Path, monkeypatch) -> None:
    clear_config_env(monkeypatch)

    first = load_settings(tmp_path / "missing.toml")
    first.routing["proposer"]["pool"].append("mutated-model")

    second = load_settings(tmp_path / "missing.toml")

    assert "mutated-model" not in second.routing["proposer"]["pool"]
    assert "mutated-model" not in DEFAULT_ROUTING["proposer"]["pool"]


def test_load_settings_reads_openai_values_from_env_file(tmp_path: Path, monkeypatch) -> None:
    clear_config_env(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text('OPENAI_API_KEY="sk-test"\nOPENAI_MODEL=gpt-5.5\n', encoding="utf-8")
    monkeypatch.setattr("app.core.config.DEFAULT_ENV_PATH", env_path)

    settings = load_settings(tmp_path / "missing.toml")

    assert settings.openai_api_key == "sk-test"
    assert settings.openai_model == "gpt-5.5"


def test_load_settings_defaults_single_shot_to_codex_cli(tmp_path: Path, monkeypatch) -> None:
    clear_config_env(monkeypatch)
    monkeypatch.setattr("app.core.config.DEFAULT_ENV_PATH", tmp_path / "missing.env")

    settings = load_settings(tmp_path / "missing.toml")

    assert settings.single_shot_provider == "codex"
    assert settings.codex_command == "codex"
