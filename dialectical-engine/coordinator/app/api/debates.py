from __future__ import annotations

from collections.abc import Callable
import subprocess
from typing import Annotated, Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, require_user_token
from app.core.db import get_db
from app.models.entities import Debate, Generation, Node, Synthesis
from app.services.events import event_bus
from app.services.orchestrator import archive_debate as archive_debate_state
from app.services.orchestrator import create_debate, markdown_export
from app.services.serialization import debate_to_dict, iso
from app.services.single_shot import (
    DebateGenerationResult,
    SINGLE_SHOT_MODE,
    configured_single_shot_generator,
    create_single_shot_debate,
)

router = APIRouter(prefix="/api/debates", tags=["debates"])


class DebateCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=2000)
    config: Optional[dict[str, Any]] = None


def single_shot_generator_dependency() -> Callable[[str], DebateGenerationResult]:
    return configured_single_shot_generator()


def debate_models(db: Session, debate_id: str) -> list[str]:
    generation_models = db.scalars(
        select(Generation.model_id)
        .join(Node, Generation.node_id == Node.id)
        .where(Node.debate_id == debate_id)
        .distinct()
        .order_by(Generation.model_id.asc())
    ).all()
    synthesis_models = db.scalars(
        select(Synthesis.model_id).where(Synthesis.debate_id == debate_id).distinct()
    ).all()
    return sorted({*generation_models, *synthesis_models})


@router.get("")
def list_debates(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(Debate)
            .where(Debate.status != "archived")
            .order_by(Debate.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return {
        "items": [
            {
                "id": debate.id,
                "topic": debate.topic,
                "status": debate.status,
                "created_at": iso(debate.created_at),
                "completed_at": iso(debate.completed_at),
                "models": debate_models(db, debate.id),
            }
            for debate in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.post("")
def post_debate(
    payload: DebateCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthContext, Depends(require_user_token)],
    single_shot_generator: Annotated[Callable[[str], DebateGenerationResult], Depends(single_shot_generator_dependency)],
) -> dict[str, Any]:
    try:
        if payload.config and payload.config.get("mode") == SINGLE_SHOT_MODE:
            debate = create_single_shot_debate(db, payload.topic, generator=single_shot_generator)
        else:
            debate = create_debate(db, payload.topic, payload.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, httpx.HTTPError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return debate_to_dict(db, debate)


@router.get("/{debate_id}")
def get_debate(debate_id: str, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    debate = db.get(Debate, debate_id)
    if not debate or debate.status == "archived":
        raise HTTPException(status_code=404, detail="Debate not found")
    return debate_to_dict(db, debate)


@router.delete("/{debate_id}")
def archive_debate(
    debate_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AuthContext, Depends(require_user_token)],
) -> dict[str, str]:
    debate = db.get(Debate, debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")
    archive_debate_state(db, debate)
    return {"status": "archived"}


@router.get("/{debate_id}/events")
async def debate_events(
    debate_id: str,
    db: Annotated[Session, Depends(get_db)],
    replay_history: bool = True,
) -> StreamingResponse:
    debate = db.get(Debate, debate_id)
    if not debate or debate.status == "archived":
        raise HTTPException(status_code=404, detail="Debate not found")
    return StreamingResponse(event_bus.subscribe(debate_id, replay_history=replay_history), media_type="text/event-stream")


@router.get("/{debate_id}/export.md", response_class=PlainTextResponse)
def export_debate(debate_id: str, db: Annotated[Session, Depends(get_db)]) -> PlainTextResponse:
    debate = db.get(Debate, debate_id)
    if not debate or debate.status == "archived":
        raise HTTPException(status_code=404, detail="Debate not found")
    return PlainTextResponse(
        markdown_export(db, debate),
        headers={"Content-Disposition": f'attachment; filename="debate-{debate.id}.md"'},
    )
