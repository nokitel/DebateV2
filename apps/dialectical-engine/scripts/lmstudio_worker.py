#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_COORDINATOR_URL = "http://127.0.0.1:8000"
DEFAULT_DB = Path("~/.dialectical/db.sqlite3").expanduser()
DEFAULT_TOKEN_CONFIG = Path("~/.dialectical-worker/config.toml").expanduser()
DEFAULT_LMSTUDIO_URL = "http://127.0.0.1:1234"
DEFAULT_MODEL = "google_gemma-4-e4b-it"
DEFAULT_CAPABILITY = f"lmstudio:{DEFAULT_MODEL}"
DEFAULT_WORKER_NAME = "mac-mini-lmstudio"
DEFAULT_WORKER_ID_FILE = Path("~/.dialectical/lmstudio-worker-id").expanduser()


def now_db() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def load_worker_token(path: Path) -> str:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    token = payload.get("worker_token")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError(f"worker_token missing from {path}")
    return token


def load_or_create_worker_id(path: Path) -> str:
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = str(uuid.uuid4())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    return value


def ensure_worker_row(
    db_path: Path,
    *,
    worker_id: str,
    worker_name: str,
    capability: str,
    token_source_worker: str,
) -> None:
    with sqlite3.connect(db_path) as db:
        token_hash_row = db.execute(
            "select token_hash from workers where name = ?",
            (token_source_worker,),
        ).fetchone()
        if token_hash_row is None:
            raise RuntimeError(f"token source worker not found in DB: {token_source_worker}")
        token_hash = token_hash_row[0]
        now = now_db()
        db.execute("delete from workers where name = ? and id != ?", (worker_name, worker_id))
        db.execute(
            """
            insert into workers(id, name, token_hash, capabilities, last_seen, status, current_job_id, created_at)
            values(?, ?, ?, ?, ?, 'online', NULL, ?)
            on conflict(id) do update set
              name = excluded.name,
              token_hash = excluded.token_hash,
              capabilities = excluded.capabilities,
              last_seen = excluded.last_seen,
              status = 'online'
            """,
            (worker_id, worker_name, token_hash, json.dumps([capability]), now, now),
        )
        db.commit()


def request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    worker_id: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 35,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if worker_id:
        headers["X-Worker-ID"] = worker_id
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            if not body:
                return {}
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc


def lmstudio_chat(base_url: str, model: str, system: str, user: str, max_tokens: int) -> tuple[str, dict[str, Any]]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=180) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    elapsed_ms = int((time.monotonic() - started) * 1000)
    content = response_payload["choices"][0]["message"]["content"]
    usage = response_payload.get("usage") or {}
    metadata = {
        "latency_ms": elapsed_ms,
        "tokens_in": usage.get("prompt_tokens"),
        "tokens_out": usage.get("completion_tokens"),
    }
    return str(content).strip(), metadata


def structured_result(job: dict[str, Any], text: str) -> Any:
    job_type = job.get("job_type")
    if job_type == "argue":
        return text
    if job_type == "decompose":
        return {
            "root_claim": text.splitlines()[0][:300] if text else "Debate topic",
            "argument": text or "Debate decomposed into initial pro and con claims.",
            "children": [
                {"type": "PRO", "claim": "There is a strong supporting case to consider."},
                {"type": "CON", "claim": "There is a strong opposing case to consider."},
            ],
        }
    if job_type == "synthesize":
        return {
            "strongest_pro": text,
            "strongest_con": "The opposing side raises material concerns that should be weighed carefully.",
            "verdict": text,
        }
    return text


def process_job(args: argparse.Namespace, token: str, worker_id: str, job: dict[str, Any]) -> None:
    prompt = job["prompt"]
    model_name = args.model
    text, metadata = lmstudio_chat(
        args.lmstudio_url,
        model_name,
        str(prompt.get("system", "")),
        str(prompt.get("user", "")),
        int(prompt.get("max_tokens") or args.max_tokens),
    )
    job_id = job["id"]
    if text:
        request_json(
            "POST",
            f"{args.coordinator_url.rstrip('/')}/api/jobs/{job_id}/stream",
            token=token,
            worker_id=worker_id,
            payload={"delta": text},
            timeout=30,
        )
    result = structured_result(job, text)
    request_json(
        "POST",
        f"{args.coordinator_url.rstrip('/')}/api/jobs/{job_id}/complete",
        token=token,
        worker_id=worker_id,
        payload={
            "result": result,
            "tokens_in": metadata.get("tokens_in"),
            "tokens_out": metadata.get("tokens_out"),
            "latency_ms": metadata.get("latency_ms"),
        },
        timeout=60,
    )


def heartbeat(args: argparse.Namespace, token: str, worker_id: str, capability: str) -> None:
    request_json(
        "POST",
        f"{args.coordinator_url.rstrip('/')}/api/workers/{worker_id}/heartbeat",
        token=token,
        payload={"capabilities": [capability], "status": "online"},
        timeout=10,
    )


def run_worker(args: argparse.Namespace) -> int:
    capability = args.capability or f"lmstudio:{args.model}"
    worker_id = args.worker_id or load_or_create_worker_id(args.worker_id_file)
    token = load_worker_token(args.token_config)
    ensure_worker_row(
        args.database,
        worker_id=worker_id,
        worker_name=args.worker_name,
        capability=capability,
        token_source_worker=args.token_source_worker,
    )
    print(f"LM Studio worker {args.worker_name} online as {worker_id} with {capability}")

    processed = 0
    while True:
        heartbeat(args, token, worker_id, capability)
        response = request_json(
            "POST",
            f"{args.coordinator_url.rstrip('/')}/api/workers/{worker_id}/poll",
            token=token,
            timeout=args.poll_timeout,
        )
        job = response.get("job")
        if job:
            print(f"Claimed {job['id']} ({job['job_type']} {job['required_role']} {job['required_model']})")
            process_job(args, token, worker_id, job)
            processed += 1
            if args.once:
                break
        elif args.once:
            break
        time.sleep(args.idle_sleep)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone local LM Studio worker for the simplified single-Mac setup.")
    parser.add_argument("--coordinator-url", default=DEFAULT_COORDINATOR_URL)
    parser.add_argument("--lmstudio-url", default=DEFAULT_LMSTUDIO_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--capability", default=DEFAULT_CAPABILITY)
    parser.add_argument("--worker-name", default=DEFAULT_WORKER_NAME)
    parser.add_argument("--worker-id")
    parser.add_argument("--worker-id-file", type=Path, default=DEFAULT_WORKER_ID_FILE)
    parser.add_argument("--token-config", type=Path, default=DEFAULT_TOKEN_CONFIG)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--token-source-worker", default="mac-mini")
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument("--poll-timeout", type=float, default=35)
    parser.add_argument("--idle-sleep", type=float, default=1)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    return run_worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
