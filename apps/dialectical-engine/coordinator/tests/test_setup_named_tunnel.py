from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
VALID_CREDENTIALS = (
    '{"AccountTag":"account-tag","TunnelID":"11111111-1111-1111-1111-111111111111","TunnelSecret":"secret"}'
)


def load_module():
    name = "dialectical_setup_named_tunnel"
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "setup_named_tunnel.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_setup_named_tunnel_logs_in_creates_installs_and_verifies_when_auto_credentials_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    cloudflared_dir = tmp_path / ".cloudflared"
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):  # noqa: ANN001
        commands.append(command)
        return None

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", cloudflared_dir)
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
        ],
    )

    module.main()

    assert commands == [
        ["/usr/local/bin/cloudflared", "tunnel", "login"],
        ["/usr/local/bin/cloudflared", "tunnel", "create", "dialectical-prod"],
        [
            "make",
            "install-tunnel",
            "TUNNEL_NAME=dialectical-prod",
            "TUNNEL_HOSTNAME=debate.example.com",
            "CLOUDFLARED_CREDENTIALS=auto",
        ],
        [
            "make",
            "deploy-preflight",
            "DEPLOY_ROLE=mac-mini",
            "PREFLIGHT_FLAGS=--require-installed-services",
        ],
        ["make", "status", "STATUS_FLAGS=--check-endpoints"],
        ["make", "handoff-bundles", "PUBLIC_URL=https://debate.example.com"],
    ]


def test_setup_named_tunnel_uses_existing_credentials_without_login_or_create(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    cloudflared_dir = tmp_path / ".cloudflared"
    cloudflared_dir.mkdir()
    (cloudflared_dir / "cert.pem").write_text("certificate")
    (cloudflared_dir / "tunnel-id.json").write_text(VALID_CREDENTIALS)
    commands: list[list[str]] = []

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", cloudflared_dir)
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--stop-quick-after-verified",
        ],
    )

    module.main()

    assert commands[0] == [
        "make",
        "install-tunnel",
        "TUNNEL_NAME=dialectical-prod",
        "TUNNEL_HOSTNAME=debate.example.com",
        "CLOUDFLARED_CREDENTIALS=auto",
    ]
    assert ["/usr/local/bin/cloudflared", "tunnel", "login"] not in commands
    assert ["/usr/local/bin/cloudflared", "tunnel", "create", "dialectical-prod"] not in commands
    assert ["make", "stop-quick-tunnel"] in commands
    assert commands[-1] == ["make", "status", "STATUS_FLAGS=--check-endpoints"]
    assert ["make", "handoff-bundles", "PUBLIC_URL=https://debate.example.com"] in commands


def test_setup_named_tunnel_rejects_explicit_missing_credentials_before_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    commands: list[list[str]] = []
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--credentials-file",
            str(tmp_path / "missing.json"),
        ],
    )

    with pytest.raises(SystemExit, match="credentials file does not exist"):
        module.main()

    assert commands == []


def test_setup_named_tunnel_rejects_invalid_auto_credentials_before_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    cloudflared_dir = tmp_path / ".cloudflared"
    cloudflared_dir.mkdir()
    (cloudflared_dir / "tunnel-id.json").write_text('{"AccountTag":"account-tag"}')
    commands: list[list[str]] = []

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", cloudflared_dir)
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
        ],
    )

    with pytest.raises(SystemExit, match="missing required keys: TunnelID, TunnelSecret"):
        module.main()

    assert commands == []


def test_setup_named_tunnel_dry_run_does_not_require_cloudflared(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", tmp_path / ".cloudflared")
    monkeypatch.setattr(module.shutil, "which", lambda _command: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--dry-run",
        ],
    )

    module.main()


def test_setup_named_tunnel_can_skip_handoff_bundle_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    cloudflared_dir = tmp_path / ".cloudflared"
    cloudflared_dir.mkdir()
    (cloudflared_dir / "tunnel-id.json").write_text(VALID_CREDENTIALS)
    commands: list[list[str]] = []

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", cloudflared_dir)
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--skip-handoff",
        ],
    )

    module.main()

    assert ["make", "handoff-bundles", "PUBLIC_URL=https://debate.example.com"] not in commands


def test_setup_named_tunnel_rejects_handoff_refresh_without_endpoint_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    commands: list[list[str]] = []

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", tmp_path / ".cloudflared")
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--skip-status",
        ],
    )

    with pytest.raises(SystemExit, match="Refusing to refresh named-URL handoff without endpoint status"):
        module.main()

    assert commands == []


def test_setup_named_tunnel_rejects_handoff_refresh_without_deploy_preflight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    commands: list[list[str]] = []

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", tmp_path / ".cloudflared")
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--skip-preflight",
        ],
    )

    with pytest.raises(SystemExit, match="Refusing to refresh named-URL handoff without deploy preflight"):
        module.main()

    assert commands == []


def test_setup_named_tunnel_allows_explicit_unverified_handoff_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    cloudflared_dir = tmp_path / ".cloudflared"
    cloudflared_dir.mkdir()
    (cloudflared_dir / "tunnel-id.json").write_text(VALID_CREDENTIALS)
    commands: list[list[str]] = []

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", cloudflared_dir)
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--skip-status",
            "--allow-unverified-handoff",
        ],
    )

    module.main()

    assert ["make", "status", "STATUS_FLAGS=--check-endpoints"] not in commands
    assert ["make", "handoff-bundles", "PUBLIC_URL=https://debate.example.com"] in commands


def test_setup_named_tunnel_allows_explicit_unverified_handoff_without_deploy_preflight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    cloudflared_dir = tmp_path / ".cloudflared"
    cloudflared_dir.mkdir()
    (cloudflared_dir / "tunnel-id.json").write_text(VALID_CREDENTIALS)
    commands: list[list[str]] = []

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", cloudflared_dir)
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--skip-preflight",
            "--allow-unverified-handoff",
        ],
    )

    module.main()

    assert [
        "make",
        "deploy-preflight",
        "DEPLOY_ROLE=mac-mini",
        "PREFLIGHT_FLAGS=--require-installed-services",
    ] not in commands
    assert ["make", "status", "STATUS_FLAGS=--check-endpoints"] in commands
    assert ["make", "handoff-bundles", "PUBLIC_URL=https://debate.example.com"] in commands


def test_setup_named_tunnel_rejects_quick_tunnel_stop_without_endpoint_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    commands: list[list[str]] = []

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", tmp_path / ".cloudflared")
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--skip-status",
            "--skip-handoff",
            "--stop-quick-after-verified",
        ],
    )

    with pytest.raises(SystemExit, match="Refusing to stop the quick tunnel without endpoint status"):
        module.main()

    assert commands == []


def test_setup_named_tunnel_rejects_quick_tunnel_stop_without_deploy_preflight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    commands: list[list[str]] = []

    monkeypatch.setattr(module.install_tunnel, "CLOUDFLARED_DIR", tmp_path / ".cloudflared")
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/local/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: commands.append(command))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup_named_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--skip-preflight",
            "--skip-handoff",
            "--stop-quick-after-verified",
        ],
    )

    with pytest.raises(SystemExit, match="Refusing to stop the quick tunnel without deploy preflight"):
        module.main()

    assert commands == []
