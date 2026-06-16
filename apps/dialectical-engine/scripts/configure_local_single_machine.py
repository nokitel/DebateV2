#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("~/.dialectical/db.sqlite3").expanduser()
DEFAULT_REPORT = Path("/private/tmp/dialectical-local-single-machine-config.json")
DEFAULT_CODEX_MODEL = "codex-gpt-5.5"
DEFAULT_LMSTUDIO_MODEL = "google_gemma-4-e4b-it"


def now_db() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def load_runtime_settings(db: sqlite3.Connection) -> dict[str, Any]:
    row = db.execute("select value from settings where key = 'runtime_settings'").fetchone()
    if row is None:
        return {}
    raw = row[0]
    if isinstance(raw, str):
        value = json.loads(raw)
    elif isinstance(raw, dict):
        value = raw
    else:
        raise RuntimeError(f"Unsupported runtime_settings value type: {type(raw).__name__}")
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


def configured_runtime(args: argparse.Namespace, current: dict[str, Any]) -> dict[str, Any]:
    runtime = dict(current)
    lmstudio_capability = args.lmstudio_capability or f"lmstudio:{args.lmstudio_model}"
    optional_models = []
    if args.claude_model:
        optional_models.append(args.claude_model)
    if args.gemini_model:
        optional_models.append(args.gemini_model)

    enabled_models = unique([args.codex_model, lmstudio_capability, *optional_models])
    runtime["enabled_models"] = enabled_models

    fallback_models = [model for model in enabled_models if model != args.codex_model]
    runtime["routing"] = {
        "decomposer": {
            "primary": args.codex_model,
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
            "primary": args.codex_model,
            "fallback": fallback_models,
        },
    }
    return runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure local routing for the simplified one-computer setup.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--codex-model", default=DEFAULT_CODEX_MODEL)
    parser.add_argument("--lmstudio-model", default=DEFAULT_LMSTUDIO_MODEL)
    parser.add_argument("--lmstudio-capability")
    parser.add_argument("--claude-model", help="Optional Claude capability to enable after Claude CLI login works.")
    parser.add_argument("--gemini-model", help="Optional Gemini capability to enable only after non-API auth works.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with sqlite3.connect(args.database) as db:
        before = load_runtime_settings(db)
        after = configured_runtime(args, before)
        if not args.dry_run:
            save_runtime_settings(db, after)

    report = {
        "database": str(args.database),
        "dry_run": args.dry_run,
        "enabled_models_before": before.get("enabled_models"),
        "enabled_models_after": after.get("enabled_models"),
        "routing_after": after.get("routing"),
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Report: {args.report_path}")
    print("Enabled models:")
    for model in after["enabled_models"]:
        print(f"- {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
