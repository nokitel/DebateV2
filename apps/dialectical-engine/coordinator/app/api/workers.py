from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, hash_token, require_user_token, require_worker
from app.core.config import load_settings, new_secret_token
from app.core.db import get_db
from app.core.write_lock import commit_write
from app.models.entities import Worker, now_utc
from app.services.orchestrator import (
    claim_pending_job,
    mark_worker_seen,
    publish_job_started,
    render_job_payload,
    requeue_active_jobs_for_worker,
)

router = APIRouter(prefix="/api", tags=["workers"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    capabilities: list[str] = Field(default_factory=list)


class HeartbeatRequest(BaseModel):
    capabilities: Optional[list[str]] = None
    status: Literal["online", "offline", "degraded"] = "online"


def clean_worker_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("name must be a non-empty string")
    return cleaned


def clean_capabilities(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("capabilities must be a list")
    capabilities: list[str] = []
    seen: set[str] = set()
    for capability in value:
        if not isinstance(capability, str) or not capability.strip():
            raise ValueError("capabilities must contain non-empty strings")
        cleaned = capability.strip()
        if cleaned in seen:
            continue
        capabilities.append(cleaned)
        seen.add(cleaned)
    if not capabilities:
        raise ValueError("capabilities must contain at least one model")
    return capabilities


def utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


@router.post("/workers/register")
def register_worker(
    payload: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthContext, Depends(require_user_token)],
) -> dict[str, object]:
    try:
        name = clean_worker_name(payload.name)
        capabilities = clean_capabilities(payload.capabilities)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    token = new_secret_token("worker")
    worker = db.scalar(select(Worker).where(Worker.name == name))
    if worker:
        requeue_active_jobs_for_worker(db, worker, "Worker re-registered")
        worker.token_hash = hash_token(token)
        worker.capabilities = capabilities
        worker.status = "online"
        worker.last_seen = now_utc()
    else:
        worker = Worker(
            name=name,
            token_hash=hash_token(token),
            capabilities=capabilities,
            status="online",
            last_seen=now_utc(),
        )
        db.add(worker)
    commit_write(db)
    db.refresh(worker)
    return {"worker_id": worker.id, "worker_token": token, "name": worker.name, "capabilities": worker.capabilities}


@router.post("/workers/{worker_id}/heartbeat")
def heartbeat(
    worker: Annotated[Worker, Depends(require_worker)],
    payload: HeartbeatRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    if payload.capabilities is not None:
        try:
            worker.capabilities = clean_capabilities(payload.capabilities)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    worker.last_seen = now_utc()
    worker.status = payload.status
    commit_write(db)
    return {"status": worker.status}


@router.post("/workers/{worker_id}/poll")
async def poll(worker: Annotated[Worker, Depends(require_worker)], db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    settings = load_settings()
    deadline = asyncio.get_running_loop().time() + settings.worker_poll_seconds
    while True:
        job = claim_pending_job(db, worker)
        if job:
            await publish_job_started(db, job)
            return {"job": render_job_payload(db, job)}
        if asyncio.get_running_loop().time() >= deadline:
            mark_worker_seen(worker, now_utc())
            commit_write(db)
            return {"job": None}
        await asyncio.sleep(1)


@router.get("/backends/status")
def backend_status(db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    settings = load_settings()
    offline_cutoff = now_utc() - timedelta(seconds=settings.worker_offline_seconds)
    rows = list(db.scalars(select(Worker).order_by(Worker.name.asc())).all())
    for worker in rows:
        last_seen_is_aware = (
            worker.last_seen.tzinfo is not None
            and worker.last_seen.tzinfo.utcoffset(worker.last_seen) is not None
        )
        comparable_cutoff = offline_cutoff if last_seen_is_aware else offline_cutoff.replace(tzinfo=None)
        if worker.last_seen < comparable_cutoff and (worker.status != "offline" or worker.current_job_id):
            requeue_active_jobs_for_worker(db, worker, "Worker offline")
            worker.status = "offline"
    commit_write(db)
    return {
        "workers": [
            {
                "id": worker.id,
                "name": worker.name,
                "capabilities": worker.capabilities,
                "last_seen": utc_isoformat(worker.last_seen),
                "status": worker.status,
                "current_job_id": worker.current_job_id,
            }
            for worker in rows
        ]
    }
