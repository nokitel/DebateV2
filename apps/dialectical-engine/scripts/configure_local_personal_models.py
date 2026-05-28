#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = ROOT / "worker"
sys.path.insert(0, str(WORKER_ROOT))

from app.config import update_config_file  # noqa: E402


DEFAULT_DB = Path("~/.dialectical/db.sqlite3").expanduser()
DEFAULT_WORKER_CONFIG = Path("~/.dialectical-worker/config.toml").expanduser()
DEFAULT_REPORT = Path("/private/tmp/dialectical-local-personal-models.json")
DEFAULT_LM_STUDIO_URL = "http://127.0.0.1:1234"

CODEX_MODEL = "codex-gpt-5"
CLAUDE_MODEL = "claude-sonnet-4.5"
GEMINI_MODEL = "gemini-2.5-pro"
LM_STUDIO_MODEL = "google_gemma-4-e4b-it"
LM_STUDIO_CAPABILITY = f"lmstudio:{LM_STUDIO_MODEL}"


def now_db() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result


def run(command: list[str], *, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env={**os.environ, **env} if env else None,
        )
        return {
            "command": command,
            "env_overrides": sorted(env or {}),
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "env_overrides": sorted(env or {}),
            "ok": False,
            "returncode": None,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "").strip() if isinstance(exc.stderr, str) else "",
            "error": f"timed out after {timeout}s",
        }
    except OSError as exc:
        return {
            "command": command,
            "env_overrides": sorted(env or {}),
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def contains_ok(result: dict[str, Any]) -> bool:
    output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    return bool(result.get("ok")) and "ok" in output


def probe_cli_models() -> dict[str, dict[str, Any]]:
    probes = {
        CODEX_MODEL: run(
            ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "Reply with exactly: ok"],
            timeout=60,
        ),
        CLAUDE_MODEL: run(["claude", "-p", "--max-turns", "1", "Reply with exactly: ok"], timeout=30),
        GEMINI_MODEL: run(
            ["gemini", "-p", "Reply with exactly: ok"],
            timeout=30,
            env={"GOOGLE_GENAI_USE_GCA": "true"},
        ),
    }
    for model, result in probes.items():
        result["ready"] = contains_ok(result)
        result["model"] = model
    return probes


def probe_lm_studio(base_url: str, model: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        model_ids = [
            item.get("id")
            for item in payload.get("data", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        return {"ok": True, "url": url, "model_ids": model_ids, "ready": model in model_ids}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "url": url, "ready": False, "error": f"{type(exc).__name__}: {exc}"}


def load_runtime_settings(db: sqlite3.Connection) -> dict[str, Any]:
    row = db.execute("select value from settings where key = 'runtime_settings'").fetchone()
    if row is None:
        return {}
    value = json.loads(row[0])
    if not isinstance(value, dict):
        raise RuntimeError("runtime_settings must be a JSON object")
    return value


def save_runtime_settings(db: sqlite3.Connection, runtime: dict[str, Any]) -> None:
    db.execute(
        """
        insert into settings(key, value, updated_at)
        values('runtime_settings', ?, ?)
        on conflict(key) do update set
          value = excluded.value,
          updated_at = excluded.updated_at
        """,
        (json.dumps(runtime, sort_keys=True), now_db()),
    )
    db.commit()


def build_runtime(current: dict[str, Any], enabled_models: list[str]) -> dict[str, Any]:
    runtime = dict(current)
    fallback_models = [model for model in enabled_models if model != CODEX_MODEL]
    runtime["enabled_models"] = enabled_models
    runtime["routing"] = {
        "decomposer": {
            "primary": CODEX_MODEL,
            "fallback": fallback_models,
        },
        "proposer": {
            "pool": enabled_models,
            "strategy": "round_robin",
        },
        "opponent": {
            "pool": enabled_models,
            "strategy": "round_robin",
            "constraint": "not_same_as_claim_author",
        },
        "synthesizer": {
            "primary": CODEX_MODEL,
            "fallback": fallback_models,
        },
    }
    return runtime


def restart_worker_service() -> dict[str, Any]:
    agent = Path("~/Library/LaunchAgents/com.dialectical.worker.plist").expanduser()
    if not agent.exists():
        return {"ok": False, "error": f"missing launch agent: {agent}"}
    unload = run(["launchctl", "unload", str(agent)], timeout=10)
    load = run(["launchctl", "load", str(agent)], timeout=10)
    time.sleep(2)
    return {"ok": bool(load.get("ok")), "unload": unload, "load": load, "agent": str(agent)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enable locally usable personal CLI models for the simplified one-computer setup."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--worker-config", type=Path, default=DEFAULT_WORKER_CONFIG)
    parser.add_argument("--lm-studio-url", default=DEFAULT_LM_STUDIO_URL)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--restart-worker", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cli_probes = probe_cli_models()
    lm_studio = probe_lm_studio(args.lm_studio_url, LM_STUDIO_MODEL)

    cli_ready = [model for model in (CODEX_MODEL, CLAUDE_MODEL, GEMINI_MODEL) if cli_probes[model].get("ready")]
    enabled_models = unique([*cli_ready, LM_STUDIO_CAPABILITY] if lm_studio.get("ready") else cli_ready)
    worker_allowed_models = unique([*cli_ready, LM_STUDIO_CAPABILITY] if lm_studio.get("ready") else cli_ready)

    with sqlite3.connect(args.database) as db:
        runtime_before = load_runtime_settings(db)
        runtime_after = build_runtime(runtime_before, enabled_models)
        if not args.dry_run:
            save_runtime_settings(db, runtime_after)

    worker_config_after = None
    if not args.dry_run:
        worker_config_after = update_config_file(args.worker_config, allowed_models=worker_allowed_models)

    restart = None
    if args.restart_worker and not args.dry_run:
        restart = restart_worker_service()

    report = {
        "ok": CODEX_MODEL in enabled_models and LM_STUDIO_CAPABILITY in enabled_models,
        "dry_run": args.dry_run,
        "cli_probes": cli_probes,
        "lm_studio": lm_studio,
        "enabled_models_before": runtime_before.get("enabled_models"),
        "enabled_models_after": enabled_models,
        "worker_allowed_models_after": worker_allowed_models,
        "worker_config": str(args.worker_config),
        "worker_config_after": worker_config_after.__dict__ if worker_config_after else None,
        "restart": restart,
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Report: {args.report_path}")
    print("Enabled runtime models:")
    for model in enabled_models:
        print(f"- {model}")
    print("Main worker allowed models:")
    for model in worker_allowed_models:
        print(f"- {model}")
    not_ready = [model for model, result in cli_probes.items() if not result.get("ready")]
    if not_ready:
        print("Not enabled yet:")
        for model in not_ready:
            print(f"- {model}")
    if restart is not None:
        print(f"Worker restart: {'ok' if restart.get('ok') else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
