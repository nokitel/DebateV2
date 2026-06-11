from __future__ import annotations

import argparse
import asyncio
import json
import math
import signal
import time
from typing import Any

import httpx

from app.capabilities import detect_adapters
from app.client import CoordinatorClient
from app.config import load_config


class StructuredOutputError(ValueError):
    pass


def extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise StructuredOutputError("Model output did not contain a valid JSON object")


def parse_result(job: dict[str, Any], text: str) -> Any:
    if job["job_type"] in {
        "decompose",
        "synthesize",
        "v2_skill_create",
        "v2_agent_create",
        "v2_agent_argument",
        "v2_plan",
        "v2_pov",
        "v2_agent_run",
        "v2_synthesize",
    }:
        return extract_json_object(text)
    return {"argument": text.strip()}


def enrich_v2_result(job: dict[str, Any], result: Any, worker_id: str | None) -> Any:
    if not isinstance(result, dict):
        return result
    job_type = str(job.get("job_type") or "")
    if not job_type.startswith("v2_"):
        return result
    enriched = dict(result)
    job_id = str(job.get("id") or "")
    model_id = str(job.get("required_model") or "")
    worker = str(worker_id or "")
    if job_type in {"v2_skill_create", "v2_agent_create"}:
        enriched["provenance"] = {
            **(enriched.get("provenance") if isinstance(enriched.get("provenance"), dict) else {}),
            "created_by_model": model_id,
            "created_by_worker_id": worker,
            "creation_prompt_id": f"prompt-{job_id}",
            "job_id": job_id,
        }
    else:
        enriched["provenance"] = {
            **(enriched.get("provenance") if isinstance(enriched.get("provenance"), dict) else {}),
            "model_id": model_id,
            "worker_id": worker,
            "prompt_id": f"prompt-{job_id}",
            "job_id": job_id,
        }
    return enriched


def estimate_tokens(*parts: str) -> int:
    text = "\n".join(part for part in parts if part)
    if not text.strip():
        return 0
    return max(1, len(text.split()), math.ceil(len(text) / 4))


async def handle_job(client: CoordinatorClient, adapters: dict[str, Any], job: dict[str, Any]) -> None:
    await handle_job_with_heartbeats(client, adapters, job)


def retryable_coordinator_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return False


def stale_job_coordinator_error(exc: Exception) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    if exc.response.status_code not in {403, 404, 409}:
        return False
    detail = ""
    try:
        payload = exc.response.json()
        if isinstance(payload, dict):
            detail = str(payload.get("detail") or "")
    except Exception:  # noqa: BLE001 - best-effort classification for stale job responses.
        detail = exc.response.text
    return detail.startswith("Job ") or "cannot be mutated" in detail


def nonretryable_coordinator_completion_error(exc: Exception) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    return exc.response.status_code == 400 and "/complete" in str(exc.request.url)


async def wait_or_stop(stop: asyncio.Event, seconds: float) -> None:
    if seconds <= 0:
        await asyncio.sleep(0)
        return
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        return


async def register_with_backoff(
    client: CoordinatorClient,
    capabilities: list[str],
    stop: asyncio.Event,
    initial_backoff_seconds: float = 1,
    max_backoff_seconds: float = 30,
) -> None:
    backoff_seconds = initial_backoff_seconds
    while not stop.is_set():
        try:
            await client.register(capabilities)
            await client.heartbeat(capabilities)
            return
        except Exception as exc:
            if not retryable_coordinator_error(exc):
                raise
            print(f"Coordinator unavailable during registration: {exc}. Retrying in {backoff_seconds}s.", flush=True)
            await wait_or_stop(stop, backoff_seconds)
            backoff_seconds = min(max_backoff_seconds, backoff_seconds * 2 if backoff_seconds else max_backoff_seconds)


async def handle_job_with_heartbeats(
    client: CoordinatorClient,
    adapters: dict[str, Any],
    job: dict[str, Any],
    capabilities: list[str] | None = None,
    heartbeat_seconds: float = 30,
) -> None:
    adapter = adapters[job["required_model"]]
    prompt = job["prompt"]
    output: list[str] = []
    started_at = time.monotonic()
    tokens_in = estimate_tokens(prompt["system"], prompt["user"])
    stop_heartbeat = asyncio.Event()

    async def heartbeat_loop() -> None:
        if not capabilities or heartbeat_seconds <= 0:
            return
        while not stop_heartbeat.is_set():
            try:
                await asyncio.wait_for(stop_heartbeat.wait(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                try:
                    await client.heartbeat(capabilities)
                except Exception as exc:  # noqa: BLE001 - keep the in-flight generation running.
                    print(f"Heartbeat failed during job {job['id']}: {exc}", flush=True)

    heartbeat_task = asyncio.create_task(heartbeat_loop())
    try:
        async def chunks():
            async for delta in adapter.stream(prompt["system"], prompt["user"], prompt["max_tokens"]):
                output.append(delta)
                yield delta

        await client.stream_chunks(job["id"], chunks())
        text = "".join(output)
        result = parse_result(job, text)
        client_config = getattr(client, "config", None)
        result = enrich_v2_result(job, result, getattr(client_config, "worker_id", None))
        if str(job.get("job_type") or "").startswith("v2_"):
            print(f"V2 result for {job['id']}: {json.dumps(result, default=str)[:2000]}", flush=True)
        await client.complete(job["id"], result, started_at, tokens_in, estimate_tokens(text))
    except Exception as exc:
        if stale_job_coordinator_error(exc):
            print(f"Coordinator no longer accepts job {job['id']}: {exc}", flush=True)
            return
        try:
            await client.fail(
                job["id"],
                str(exc),
                retryable=not isinstance(exc, StructuredOutputError)
                and not nonretryable_coordinator_completion_error(exc),
            )
        except Exception as fail_exc:
            if stale_job_coordinator_error(fail_exc):
                print(f"Coordinator no longer accepts failure for job {job['id']}: {fail_exc}", flush=True)
                return
            raise
    finally:
        stop_heartbeat.set()
        await heartbeat_task


async def worker_loop(run_once: bool = False) -> None:
    config = load_config()
    adapters = await detect_adapters(config)
    if not adapters:
        raise RuntimeError("No healthy model adapters detected")
    client = CoordinatorClient(config)
    stop = asyncio.Event()

    def request_stop() -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, signame), request_stop)
        except NotImplementedError:
            pass

    try:
        capabilities = sorted(adapters)
        await register_with_backoff(client, capabilities, stop)
        last_heartbeat = time.monotonic()
        backoff_seconds = 1
        while not stop.is_set():
            try:
                if time.monotonic() - last_heartbeat >= config.heartbeat_seconds:
                    await client.heartbeat(capabilities)
                    last_heartbeat = time.monotonic()
                job = await client.poll()
                backoff_seconds = 1
                if job:
                    await handle_job_with_heartbeats(client, adapters, job, capabilities, config.heartbeat_seconds)
            except Exception as exc:
                if not retryable_coordinator_error(exc):
                    raise
                print(f"Coordinator unavailable: {exc}. Retrying in {backoff_seconds}s.", flush=True)
                await wait_or_stop(stop, backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 30)
            if run_once:
                break
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Dialectical Engine worker")
    parser.add_argument("--once", action="store_true", help="Poll and handle at most one job")
    args = parser.parse_args()
    asyncio.run(worker_loop(run_once=args.once))


if __name__ == "__main__":
    main()
