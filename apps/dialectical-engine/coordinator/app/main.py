from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import debates, jobs, nodes, settings, workers
from app.core.auth import ensure_user_token
from app.core.config import load_settings
from app.core.db import SessionLocal, init_db

settings_obj = load_settings()
RATE_LIMIT_WINDOW_SECONDS = 60
app = FastAPI(title="Dialectical Engine Coordinator", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings_obj.web_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(debates.router)
app.include_router(nodes.router)
app.include_router(workers.router)
app.include_router(jobs.router)
app.include_router(settings.router)

_public_hits: dict[str, deque[float]] = defaultdict(deque)


def public_client_ip(request: Request) -> str:
    cloudflare_ip = request.headers.get("cf-connecting-ip")
    if cloudflare_ip:
        return cloudflare_ip.strip()
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def is_public_read_path(path: str) -> bool:
    if path == "/api/debates" or path == "/api/backends/status":
        return True
    if not path.startswith("/api/debates/"):
        return False
    return path.endswith("/events") or path.endswith("/export.md") or path.count("/") == 3


def prune_public_hits(now: float) -> None:
    for client, bucket in list(_public_hits.items()):
        while bucket and bucket[0] < now - RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if not bucket:
            _public_hits.pop(client, None)


@app.middleware("http")
async def public_rate_limit(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    public_read = request.method == "GET" and is_public_read_path(request.url.path)
    if public_read:
        client = public_client_ip(request)
        now = time.monotonic()
        prune_public_hits(now)
        bucket = _public_hits[client]
        while bucket and bucket[0] < now - RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= settings_obj.public_rate_limit_per_minute:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        bucket.append(now)
    return await call_next(request)


@app.on_event("startup")
def startup() -> None:
    init_db()
    with SessionLocal() as db:
        settings.apply_persisted_runtime_settings(db)
        token = ensure_user_token(db, settings_obj.user_token)
    if token:
        print("Dialectical Engine user token (shown once):", token, flush=True)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
