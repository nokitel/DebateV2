from __future__ import annotations

from pathlib import Path

from app.core.config import load_settings


ENGINE_ROOT = Path(__file__).resolve().parents[2]


def test_qbaf_package_exposes_step_1_marker() -> None:
    from app import qbaf

    assert qbaf.FOUNDATION_STEP == "proposal-b-step-1"


def test_agents_file_records_proposal_b_invariants() -> None:
    agents_text = (ENGINE_ROOT / "AGENTS.md").read_text()

    required_phrases = [
        "Provider-agnostic agents",
        "OpenAI/Codex is the first real adapter",
        "Pure propagation",
        "Swappable semantics",
        "Every leaf is gated by the evidence subsystem",
        "Anonymize debate sources",
        "Skeptic certifies no unaddressed attack remains",
        "Confidence-driven, cost-soft",
    ]
    for phrase in required_phrases:
        assert phrase in agents_text


def test_coordinator_config_loads_openai_values_from_dotenv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=env-file-key\n"
        "OPENAI_MODEL=codex-gpt-5.5\n"
    )

    settings = load_settings(path=tmp_path / "missing-coordinator.toml")

    assert settings.openai_api_key == "env-file-key"
    assert settings.openai_model == "codex-gpt-5.5"
