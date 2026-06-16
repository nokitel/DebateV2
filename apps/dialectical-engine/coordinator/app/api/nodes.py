from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, require_user_token
from app.core.db import get_db
from app.models.entities import Debate, Generation, Node, Worker
from app.services.orchestrator import regenerate_node
from app.services.serialization import iso

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


class RegenerateRequest(BaseModel):
    model_id: Optional[str] = Field(default=None, max_length=120)


def visible_node(db: Session, node_id: str) -> Node:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    debate = db.get(Debate, node.debate_id)
    if not debate or debate.status == "archived":
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.post("/{node_id}/regenerate")
async def regenerate(
    node_id: str,
    payload: RegenerateRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthContext, Depends(require_user_token)],
) -> dict[str, str]:
    node = visible_node(db, node_id)
    try:
        job = await regenerate_node(db, node, payload.model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"job_id": job.id, "status": "queued"}


@router.get("/{node_id}/generations")
def generations(
    node_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthContext, Depends(require_user_token)],
) -> dict[str, object]:
    visible_node(db, node_id)
    rows = list(
        db.scalars(select(Generation).where(Generation.node_id == node_id).order_by(Generation.created_at.desc())).all()
    )
    return {
        "node_id": node_id,
        "items": [
            {
                "id": row.id,
                "model_id": row.model_id,
                "role": row.role,
                "argument": row.argument,
                "is_active": row.is_active,
                "tokens_in": row.tokens_in,
                "tokens_out": row.tokens_out,
                "latency_ms": row.latency_ms,
                "worker_id": row.worker_id,
                "worker_name": db.get(Worker, row.worker_id).name if db.get(Worker, row.worker_id) else row.worker_id,
                "created_at": iso(row.created_at),
            }
            for row in rows
        ],
    }
