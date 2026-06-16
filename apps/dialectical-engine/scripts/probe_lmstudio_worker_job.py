#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("~/.dialectical/db.sqlite3").expanduser()
DEFAULT_REPORT = Path("/private/tmp/dialectical-lmstudio-job-probe.json")
DEFAULT_COORDINATOR_URL = "http://127.0.0.1:8000"
DEFAULT_LMSTUDIO_URL = "http://127.0.0.1:1234"
DEFAULT_MODEL = "google_gemma-4-e4b-it"
DEFAULT_CAPABILITY = f"lmstudio:{DEFAULT_MODEL}"


def now_db() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def deadline_db(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")


def insert_probe_job(db: sqlite3.Connection, capability: str, max_tokens: int) -> dict[str, str]:
    debate_id = str(uuid.uuid4())
    root_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    now = now_db()
    topic = "Local LM Studio probe: should public debates use concise evidence summaries?"
    config = json.dumps({"branching": 2, "max_depth": 1, "max_tokens": max_tokens}, sort_keys=True)
    db.execute(
        """
        insert into debates(id, topic, status, config, root_node_id, synthesis_id, created_at, completed_at)
        values(?, ?, 'generating', ?, ?, NULL, ?, NULL)
        """,
        (debate_id, topic, config, root_id, now),
    )
    db.execute(
        """
        insert into nodes(
          id, debate_id, parent_id, node_type, depth, position, claim,
          active_generation_id, status, materialized_path, created_at
        )
        values(?, ?, NULL, 'ROOT', 0, 0, ?, NULL, 'complete', '0', ?)
        """,
        (root_id, debate_id, topic, now),
    )
    db.execute(
        """
        insert into nodes(
          id, debate_id, parent_id, node_type, depth, position, claim,
          active_generation_id, status, materialized_path, created_at
        )
        values(?, ?, ?, 'PRO', 1, 0, ?, NULL, 'pending', '0/0', ?)
        """,
        (
            node_id,
            debate_id,
            root_id,
            "Concise evidence summaries make public debates easier to evaluate.",
            now,
        ),
    )
    db.execute(
        """
        insert into jobs(
          id, node_id, debate_id, job_type, required_role, required_model, status,
          worker_id, claimed_at, deadline, idempotency_key, stream_buffer, attempts,
          error, created_at
        )
        values(?, ?, ?, 'argue', 'proposer', ?, 'pending', NULL, NULL, ?, ?, '', 0, NULL, ?)
        """,
        (job_id, node_id, debate_id, capability, deadline_db(300), str(uuid.uuid4()), now),
    )
    db.commit()
    return {"debate_id": debate_id, "root_id": root_id, "node_id": node_id, "job_id": job_id}


def cleanup_probe(db: sqlite3.Connection, debate_id: str) -> None:
    job_ids = [row[0] for row in db.execute("select id from jobs where debate_id = ?", (debate_id,)).fetchall()]
    if job_ids:
        placeholders = ",".join("?" for _ in job_ids)
        db.execute(f"update workers set current_job_id = NULL where current_job_id in ({placeholders})", job_ids)
    node_ids = [row[0] for row in db.execute("select id from nodes where debate_id = ?", (debate_id,)).fetchall()]
    if node_ids:
        placeholders = ",".join("?" for _ in node_ids)
        db.execute(f"delete from generations where node_id in ({placeholders})", node_ids)
    db.execute("delete from syntheses where debate_id = ?", (debate_id,))
    db.execute("delete from jobs where debate_id = ?", (debate_id,))
    db.execute("delete from nodes where debate_id = ?", (debate_id,))
    db.execute("delete from debates where id = ?", (debate_id,))
    db.commit()


def inspect_probe(db: sqlite3.Connection, ids: dict[str, str]) -> dict[str, Any]:
    job = db.execute(
        "select status, worker_id, required_model, attempts, error, length(stream_buffer) from jobs where id = ?",
        (ids["job_id"],),
    ).fetchone()
    generation = db.execute(
        "select model_id, role, length(argument), tokens_in, tokens_out, latency_ms from generations where node_id = ?",
        (ids["node_id"],),
    ).fetchone()
    synthesis_jobs = db.execute(
        "select id, status, required_model from jobs where debate_id = ? and job_type = 'synthesize'",
        (ids["debate_id"],),
    ).fetchall()
    return {
        "job": {
            "status": job[0] if job else None,
            "worker_id": job[1] if job else None,
            "required_model": job[2] if job else None,
            "attempts": job[3] if job else None,
            "error": job[4] if job else None,
            "stream_buffer_chars": job[5] if job else None,
        },
        "generation": {
            "model_id": generation[0] if generation else None,
            "role": generation[1] if generation else None,
            "argument_chars": generation[2] if generation else None,
            "tokens_in": generation[3] if generation else None,
            "tokens_out": generation[4] if generation else None,
            "latency_ms": generation[5] if generation else None,
        },
        "synthesis_jobs": [
            {"id": row[0], "status": row[1], "required_model": row[2]}
            for row in synthesis_jobs
        ],
    }


def wait_for_probe_completion(db: sqlite3.Connection, ids: dict[str, str], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    inspection = inspect_probe(db, ids)
    while time.monotonic() < deadline:
        if inspection["job"]["status"] in {"complete", "failed"}:
            return inspection
        time.sleep(0.5)
        inspection = inspect_probe(db, ids)
    return inspection


def run_fallback_worker_once(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "lmstudio_worker.py"),
        "--once",
        "--coordinator-url",
        args.coordinator_url,
        "--lmstudio-url",
        args.lmstudio_url,
        "--model",
        args.model,
        "--capability",
        args.capability,
        "--poll-timeout",
        str(args.poll_timeout),
        "--max-tokens",
        str(args.max_tokens),
    ]
    env = os.environ.copy()
    expat = Path("/opt/homebrew/opt/expat/lib")
    if expat.exists() and "DYLD_LIBRARY_PATH" not in env:
        env["DYLD_LIBRARY_PATH"] = str(expat)
    started = time.monotonic()
    proc = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one synthetic LM Studio job and let an online local worker complete it.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--coordinator-url", default=DEFAULT_COORDINATOR_URL)
    parser.add_argument("--lmstudio-url", default=DEFAULT_LMSTUDIO_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--capability", default=DEFAULT_CAPABILITY)
    parser.add_argument("--poll-timeout", type=float, default=40)
    parser.add_argument("--max-tokens", type=int, default=180)
    parser.add_argument("--running-worker-timeout", type=float, default=8)
    parser.add_argument("--claimed-worker-timeout", type=float, default=60)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--keep-fixture", action="store_true")
    args = parser.parse_args()

    ids: dict[str, str] | None = None
    report: dict[str, Any] = {
        "database": str(args.database),
        "coordinator_url": args.coordinator_url,
        "lmstudio_url": args.lmstudio_url,
        "capability": args.capability,
    }
    with sqlite3.connect(args.database) as db:
        try:
            ids = insert_probe_job(db, args.capability, args.max_tokens)
            report["ids"] = ids
            report["running_worker_wait"] = wait_for_probe_completion(db, ids, args.running_worker_timeout)
            if report["running_worker_wait"]["job"]["status"] == "complete":
                report["worker_run"] = {"skipped": True, "reason": "running worker completed the probe job"}
            elif report["running_worker_wait"]["job"]["worker_id"]:
                report["claimed_worker_wait"] = wait_for_probe_completion(db, ids, args.claimed_worker_timeout)
                report["worker_run"] = {"skipped": True, "reason": "probe job was claimed by a running worker"}
            else:
                report["worker_run"] = run_fallback_worker_once(args)
            report["inspection"] = inspect_probe(db, ids)
            job = report["inspection"]["job"]
            generation = report["inspection"]["generation"]
            report["ok"] = (
                (report["worker_run"].get("returncode", 0) == 0)
                and job["status"] == "complete"
                and generation["model_id"] == args.capability
                and int(generation["argument_chars"] or 0) > 0
            )
        finally:
            if ids and not args.keep_fixture:
                cleanup_probe(db, ids["debate_id"])
                report["cleaned_up"] = True

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Report: {args.report_path}")
    print(f"LM Studio job probe: {'ok' if report.get('ok') else 'failed'}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
