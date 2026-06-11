from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_USER_TOKEN = "user_dev_token"


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    args: list[str]
    cwd: Path
    env: dict[str, str]


def int_env(environ: dict[str, str], name: str, default: int) -> int:
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None


def enabled_env(environ: dict[str, str], name: str, default: bool) -> bool:
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in {"0", "false", "no"}


def build_process_specs(
    *,
    root: Path = ROOT,
    python: str = sys.executable,
    environ: dict[str, str] | None = None,
) -> list[ProcessSpec]:
    environ = os.environ if environ is None else environ
    dev_home = Path(environ.get("DIALECTICAL_DEV_HOME") or root / ".dialectical-dev").expanduser()
    coordinator_port = int_env(environ, "DIALECTICAL_DEV_COORDINATOR_PORT", 8000)
    public_web_port = int_env(environ, "DIALECTICAL_DEV_WEB_PORT", 3000)
    next_port = int_env(environ, "DIALECTICAL_DEV_NEXT_PORT", 3001)
    next_mode = environ.get("DIALECTICAL_DEV_NEXT_MODE", "dev").strip() or "dev"
    if next_mode not in {"dev", "start"}:
        raise ValueError("DIALECTICAL_DEV_NEXT_MODE must be 'dev' or 'start'")
    coordinator_url = f"http://localhost:{coordinator_port}"
    coordinator_args = [python, "-m", "uvicorn", "app.main:app", "--port", str(coordinator_port)]
    if enabled_env(environ, "DIALECTICAL_DEV_RELOAD", os.name != "nt"):
        coordinator_args.insert(4, "--reload")
    enable_mock = environ.get("DIALECTICAL_ENABLE_MOCK", "0")
    enable_real_adapters = environ.get("DIALECTICAL_ENABLE_REAL_ADAPTERS", "1")
    worker_env = {
        "DIALECTICAL_WORKER_CONFIG": str(dev_home / "worker.toml"),
        "DIALECTICAL_COORDINATOR_URL": coordinator_url,
        "DIALECTICAL_USER_TOKEN": environ.get("DIALECTICAL_USER_TOKEN", DEFAULT_USER_TOKEN),
        "DIALECTICAL_WORKER_NAME": environ.get("DIALECTICAL_WORKER_NAME", "mac-mini"),
        "DIALECTICAL_ENABLE_MOCK": enable_mock,
        "DIALECTICAL_ENABLE_REAL_ADAPTERS": enable_real_adapters,
        **{
            key: environ[key]
            for key in ("DIALECTICAL_ALLOWED_MODELS", "DIALECTICAL_MOCK_MODELS", "CODEX_COMMAND")
            if environ.get(key)
        },
    }
    if enabled_env(worker_env, "DIALECTICAL_ENABLE_REAL_ADAPTERS", False) and not enabled_env(
        worker_env, "DIALECTICAL_ENABLE_MOCK", True
    ):
        worker_env.setdefault("DIALECTICAL_ALLOWED_MODELS", "codex-gpt-5.5")
        local_codex = (root / "scripts" / "codex-cli.cmd").resolve()
        if local_codex.exists():
            worker_env.setdefault("CODEX_COMMAND", str(local_codex))
    return [
        ProcessSpec(
            "coordinator",
            coordinator_args,
            root / "coordinator",
            {
                "DIALECTICAL_HOME": str(dev_home / "home"),
                "DIALECTICAL_DATABASE_URL": f"sqlite:///{dev_home / 'db.sqlite3'}",
            },
        ),
        ProcessSpec(
            "worker-a",
            [python, "-m", "app.main"],
            root / "worker",
            worker_env,
        ),
        ProcessSpec(
            "web",
            [
                python,
                str(root / "scripts" / "web_proxy.py"),
                "--root",
                str(root),
                "--next-mode",
                next_mode,
                "--public-host",
                "127.0.0.1",
                "--public-port",
                str(public_web_port),
                "--next-port",
                str(next_port),
                "--coordinator-port",
                str(coordinator_port),
            ],
            root,
            {},
        ),
    ]


def start(spec: ProcessSpec) -> subprocess.Popen:
    child_env = os.environ.copy()
    child_env.update(spec.env)
    child_env.setdefault("DIALECTICAL_USER_TOKEN", DEFAULT_USER_TOKEN)
    if spec.name == "worker-a":
        visible_env = {
            key: child_env.get(key)
            for key in (
                "DIALECTICAL_ENABLE_MOCK",
                "DIALECTICAL_ENABLE_REAL_ADAPTERS",
                "DIALECTICAL_ALLOWED_MODELS",
                "CODEX_COMMAND",
            )
            if child_env.get(key)
        }
        print(f"[dev] worker-a env {visible_env}", flush=True)
    process = subprocess.Popen(spec.args, cwd=spec.cwd, env=child_env)
    print(f"[dev] started {spec.name} pid={process.pid}", flush=True)
    return process


def main() -> int:
    processes: list[subprocess.Popen] = []
    try:
        for spec in build_process_specs():
            processes.append(start(spec))
            if spec.name == "coordinator":
                time.sleep(2)
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    print(f"[dev] process exited pid={process.pid} code={code}", flush=True)
                    return code
            time.sleep(1)
    except KeyboardInterrupt:
        return 130
    finally:
        for process in processes:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
