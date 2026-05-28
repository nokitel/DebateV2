from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from app.core.auth import require_worker_header
from app.core.db import get_db
from app.models.entities import Job, Worker
from app.services.orchestrator import (
    MUTABLE_JOB_STATUSES,
    StaleJobMutationError,
    StreamOffsetError,
    append_stream_delta,
    complete_job,
    fail_job,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
MAX_FAIL_REASON_CHARS = 2_000


class StreamRequest(BaseModel):
    delta: str
    offset: Optional[int] = Field(default=None, ge=0)


class CompleteRequest(BaseModel):
    result: Any
    tokens_in: Optional[int] = Field(default=None, ge=0)
    tokens_out: Optional[int] = Field(default=None, ge=0)
    latency_ms: Optional[int] = Field(default=None, ge=0)


class FailRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_FAIL_REASON_CHARS)
    retryable: bool = True


def require_job_for_worker(job_id: str, worker: Worker, db: Session) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.worker_id != worker.id:
        raise HTTPException(status_code=403, detail="Job is not claimed by this worker")
    if job.status not in MUTABLE_JOB_STATUSES:
        raise HTTPException(status_code=409, detail=f"Job is {job.status} and cannot be mutated")
    return job


@router.post("/{job_id}/stream")
async def stream_delta(
    job_id: str,
    request: Request,
    worker: Annotated[Worker, Depends(require_worker_header)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    job = require_job_for_worker(job_id, worker, db)
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = StreamRequest.model_validate(await request.json())
        try:
            await append_stream_delta(db, job, payload.delta, offset=payload.offset)
        except StaleJobMutationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except StreamOffsetError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
    else:
        try:
            async for chunk in request.stream():
                if chunk:
                    try:
                        await append_stream_delta(db, job, chunk.decode("utf-8", errors="replace"))
                    except StaleJobMutationError as exc:
                        raise HTTPException(status_code=409, detail=str(exc)) from exc
                    except ValueError as exc:
                        raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ClientDisconnect:
            return {"status": "client_disconnected"}
    return {"status": "ok"}


@router.post("/{job_id}/complete")
async def complete(
    job_id: str,
    payload: CompleteRequest,
    worker: Annotated[Worker, Depends(require_worker_header)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    job = require_job_for_worker(job_id, worker, db)
    metadata = {
        "tokens_in": payload.tokens_in,
        "tokens_out": payload.tokens_out,
        "latency_ms": payload.latency_ms or 0,
    }
    try:
        return await complete_job(db, job, payload.result, metadata)
    except StaleJobMutationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{job_id}/fail")
async def fail(
    job_id: str,
    payload: FailRequest,
    worker: Annotated[Worker, Depends(require_worker_header)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    job = require_job_for_worker(job_id, worker, db)
    try:
        await fail_job(db, job, payload.reason, payload.retryable)
    except StaleJobMutationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "queued" if payload.retryable else "failed"}
