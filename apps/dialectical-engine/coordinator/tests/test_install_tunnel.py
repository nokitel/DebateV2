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
    name = "dialectical_install_tunnel"
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "install_tunnel.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_render_config_writes_named_tunnel_ingress_routes(tmp_path: Path) -> None:
    module = load_module()
    credentials = tmp_path / "dialectical.json"

    rendered = module.render_config("dialectical-prod", "debate.example.com", credentials)

    assert "tunnel: dialectical-prod" in rendered
    assert f"credentials-file: {credentials}" in rendered
    assert "hostname: debate.example.com" in rendered
    assert "path: /api/*" in rendered
    assert "path: /healthz" in rendered
    assert "service: http://localhost:8000" in rendered
    assert "service: http://localhost:3000" in rendered
    assert "service: http_status:404" in rendered
    assert "<your-domain>" not in rendered
    assert "<tunnel-id>" not in rendered


def test_install_tunnel_rejects_missing_credentials_before_writing_config(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    destination = tmp_path / "config.yml"
    missing_credentials = tmp_path / "missing.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--credentials-file",
            str(missing_credentials),
            "--config",
            str(destination),
        ],
    )

    with pytest.raises(SystemExit, match="credentials file does not exist"):
        module.main()

    assert not destination.exists()


def test_install_tunnel_autodetects_single_credentials_file(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    cloudflared_dir = tmp_path / ".cloudflared"
    cloudflared_dir.mkdir()
    credentials = cloudflared_dir / "tunnel-id.json"
    credentials.write_text(VALID_CREDENTIALS)
    destination = tmp_path / "config.yml"
    monkeypatch.setattr(module, "CLOUDFLARED_DIR", cloudflared_dir)
    monkeypatch.setattr(module.shutil, "which", lambda _command: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--config",
            str(destination),
        ],
    )

    module.main()

    assert destination.exists()
    assert f"credentials-file: {credentials}" in destination.read_text()


def test_install_tunnel_rejects_malformed_credentials_before_writing_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    destination = tmp_path / "config.yml"
    credentials = tmp_path / "dialectical.json"
    credentials.write_text('{"AccountTag":"account-tag"}')
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--credentials-file",
            str(credentials),
            "--config",
            str(destination),
        ],
    )

    with pytest.raises(SystemExit, match="missing required keys: TunnelID, TunnelSecret"):
        module.main()

    assert not destination.exists()


def test_install_tunnel_rejects_non_uuid_tunnel_id_before_writing_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    destination = tmp_path / "config.yml"
    credentials = tmp_path / "dialectical.json"
    credentials.write_text('{"AccountTag":"account-tag","TunnelID":"not-a-uuid","TunnelSecret":"secret"}')
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--credentials-file",
            str(credentials),
            "--config",
            str(destination),
        ],
    )

    with pytest.raises(SystemExit, match="TunnelID is not a UUID"):
        module.main()

    assert not destination.exists()


def test_install_tunnel_rejects_missing_autodetect_credentials_before_writing_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    destination = tmp_path / "config.yml"
    monkeypatch.setattr(module, "CLOUDFLARED_DIR", tmp_path / "missing-cloudflared")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--config",
            str(destination),
        ],
    )

    with pytest.raises(SystemExit, match="no Cloudflare directory found"):
        module.main()

    assert not destination.exists()


def test_install_tunnel_rejects_ambiguous_autodetect_credentials_before_writing_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    cloudflared_dir = tmp_path / ".cloudflared"
    cloudflared_dir.mkdir()
    (cloudflared_dir / "first.json").write_text("{}")
    (cloudflared_dir / "second.json").write_text("{}")
    destination = tmp_path / "config.yml"
    monkeypatch.setattr(module, "CLOUDFLARED_DIR", cloudflared_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--config",
            str(destination),
        ],
    )

    with pytest.raises(SystemExit, match="multiple tunnel credentials JSON files found"):
        module.main()

    assert not destination.exists()


@pytest.mark.parametrize(
    ("hostname", "match"),
    [
        ("https://debate.example.com", "not a URL"),
        ("evaluations-postage-proceed-happiness.trycloudflare.com", "not a trycloudflare.com quick tunnel"),
        ("localhost", "valid DNS name"),
        ("bad_host.example.com", "valid DNS name"),
    ],
)
def test_install_tunnel_rejects_invalid_named_hostnames(
    hostname: str,
    match: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    destination = tmp_path / "config.yml"
    credentials = tmp_path / "dialectical.json"
    credentials.write_text(VALID_CREDENTIALS)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            hostname,
            "--credentials-file",
            str(credentials),
            "--config",
            str(destination),
        ],
    )

    with pytest.raises(SystemExit, match=match):
        module.main()

    assert not destination.exists()


@pytest.mark.parametrize(
    ("tunnel", "match"),
    [
        ("<tunnel-name>", "contains a placeholder"),
        ("https://example.com/tunnel", "not a URL"),
        ("bad tunnel", "may contain only"),
    ],
)
def test_install_tunnel_rejects_invalid_tunnel_names_before_writing_config(
    tunnel: str,
    match: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module()
    destination = tmp_path / "config.yml"
    credentials = tmp_path / "dialectical.json"
    credentials.write_text(VALID_CREDENTIALS)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            tunnel,
            "--hostname",
            "debate.example.com",
            "--credentials-file",
            str(credentials),
            "--config",
            str(destination),
        ],
    )

    with pytest.raises(SystemExit, match=match):
        module.main()

    assert not destination.exists()


def test_install_tunnel_writes_config_without_cloudflared(tmp_path: Path, monkeypatch, capsys) -> None:
    module = load_module()
    destination = tmp_path / "config.yml"
    credentials = tmp_path / "dialectical.json"
    credentials.write_text(VALID_CREDENTIALS)
    monkeypatch.setattr(module.shutil, "which", lambda _command: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--credentials-file",
            str(credentials),
            "--config",
            str(destination),
        ],
    )

    module.main()

    assert destination.exists()
    assert "tunnel: dialectical-prod" in destination.read_text()
    assert "cloudflared is not on PATH" in capsys.readouterr().out


def test_install_tunnel_requires_cloudflared_for_route_dns_or_service(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    destination = tmp_path / "config.yml"
    credentials = tmp_path / "dialectical.json"
    credentials.write_text(VALID_CREDENTIALS)
    monkeypatch.setattr(module.shutil, "which", lambda _command: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "install_tunnel.py",
            "--tunnel",
            "dialectical-prod",
            "--hostname",
            "debate.example.com",
            "--credentials-file",
            str(credentials),
            "--config",
            str(destination),
            "--route-dns",
            "--install-service",
        ],
    )

    with pytest.raises(SystemExit, match="cloudflared is not on PATH"):
        module.main()

    assert not destination.exists()


def test_stop_quick_tunnel_service_unloads_existing_launch_agent(tmp_path: Path, monkeypatch, capsys) -> None:
    module = load_module()
    plist = tmp_path / "com.dialectical.cloudflared-quick.plist"
    plist.write_text("<plist />")
    calls = []

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):  # noqa: ANN001
        calls.append((command, kwargs))
        return Result()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.stop_quick_tunnel_service(plist)

    assert calls[0][0] == ["launchctl", "unload", str(plist)]
    assert calls[0][1]["check"] is False
    assert "Stopped quick tunnel launchd service" in capsys.readouterr().out


def test_stop_quick_tunnel_service_is_idempotent_when_launch_agent_is_missing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = load_module()
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    module.stop_quick_tunnel_service(tmp_path / "missing.plist")

    assert calls == []
    assert "Quick tunnel launchd service not found" in capsys.readouterr().out


def test_stop_quick_service_only_does_not_require_named_tunnel_arguments(monkeypatch) -> None:
    module = load_module()
    stopped = []
    monkeypatch.setattr(module, "stop_quick_tunnel_service", lambda: stopped.append(True))
    monkeypatch.setattr(sys, "argv", ["install_tunnel.py", "--stop-quick-service-only"])

    module.main()

    assert stopped == [True]
