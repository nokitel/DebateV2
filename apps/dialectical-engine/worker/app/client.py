from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from app.config import WorkerConfig, save_config


def retryable_stream_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return False


class CoordinatorClient:
    def __init__(self, config: WorkerConfig) -> None:
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.coordinator_url.rstrip("/"),
            timeout=httpx.Timeout(config.request_timeout_seconds, connect=10),
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    @property
    def worker_headers(self) -> dict[str, str]:
        if not self.config.worker_id or not self.config.worker_token:
            raise RuntimeError("Worker is not registered")
        return {
            "Authorization": f"Bearer {self.config.worker_token}",
            "X-Worker-ID": self.config.worker_id,
        }

    async def register(self, capabilities: list[str], *, persist: bool = True, save_path: Path | None = None) -> None:
        if self.config.worker_id and self.config.worker_token:
            return
        if not self.config.user_token:
            raise RuntimeError("Set user_token in worker config or DIALECTICAL_USER_TOKEN to register")
        response = await self.client.post(
            "/api/workers/register",
            headers={"Authorization": f"Bearer {self.config.user_token}"},
            json={"name": self.config.name, "capabilities": capabilities},
        )
        response.raise_for_status()
        payload = response.json()
        self.config.worker_id = payload["worker_id"]
        self.config.worker_token = payload["worker_token"]
        if isinstance(payload.get("name"), str) and payload["name"].strip():
            self.config.name = payload["name"].strip()
        if persist:
            save_config(self.config, save_path)

    async def heartbeat(self, capabilities: list[str], status: str = "online") -> None:
        response = await self.client.post(
            f"/api/workers/{self.config.worker_id}/heartbeat",
            headers=self.worker_headers,
            json={"capabilities": capabilities, "status": status},
        )
        response.raise_for_status()

    async def poll(self) -> dict[str, Any] | None:
        response = await self.client.post(f"/api/workers/{self.config.worker_id}/poll", headers=self.worker_headers)
        response.raise_for_status()
        return response.json().get("job")

    async def stream(self, job_id: str, delta: str, offset: int | None = None) -> None:
        payload: dict[str, object] = {"delta": delta}
        if offset is not None:
            payload["offset"] = offset
        response = await self.client.post(
            f"/api/jobs/{job_id}/stream",
            headers=self.worker_headers,
            json=payload,
        )
        response.raise_for_status()

    async def stream_delta_with_backoff(
        self,
        job_id: str,
        delta: str,
        offset: int,
        *,
        initial_backoff_seconds: float = 1,
        max_backoff_seconds: float = 30,
    ) -> None:
        backoff_seconds = initial_backoff_seconds
        while True:
            try:
                await self.stream(job_id, delta, offset=offset)
                return
            except Exception as exc:
                if not retryable_stream_error(exc):
                    raise
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(
                    max_backoff_seconds,
                    backoff_seconds * 2 if backoff_seconds else max_backoff_seconds,
                )

    async def stream_chunks(
        self,
        job_id: str,
        chunks: AsyncIterator[str],
        *,
        initial_backoff_seconds: float = 1,
        max_backoff_seconds: float = 30,
        max_chunks_per_batch: int = 8,
        max_batch_chars: int = 1_024,
    ) -> None:
        offset = 0
        pending: list[str] = []
        pending_chars = 0

        async def flush() -> None:
            nonlocal offset, pending, pending_chars
            if not pending:
                return
            batch = "".join(pending)
            await self.stream_delta_with_backoff(
                job_id,
                batch,
                offset,
                initial_backoff_seconds=initial_backoff_seconds,
                max_backoff_seconds=max_backoff_seconds,
            )
            offset += len(batch)
            pending = []
            pending_chars = 0

        async for chunk in chunks:
            if not chunk:
                continue
            pending.append(chunk)
            pending_chars += len(chunk)
            if len(pending) >= max_chunks_per_batch or pending_chars >= max_batch_chars:
                await flush()
        await flush()

    async def complete(
        self,
        job_id: str,
        result: Any,
        started_at: float,
        tokens_in: int,
        tokens_out: int,
    ) -> dict[str, Any]:
        latency_ms = int((time.monotonic() - started_at) * 1000)
        response = await self.client.post(
            f"/api/jobs/{job_id}/complete",
            headers=self.worker_headers,
            json={"result": result, "latency_ms": latency_ms, "tokens_in": tokens_in, "tokens_out": tokens_out},
        )
        response.raise_for_status()
        return response.json()

    async def fail(self, job_id: str, reason: str, retryable: bool = True) -> None:
        response = await self.client.post(
            f"/api/jobs/{job_id}/fail",
            headers=self.worker_headers,
            json={"reason": reason, "retryable": retryable},
        )
        response.raise_for_status()
