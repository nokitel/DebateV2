from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import AuthContext, require_user_token
from app.evidence import SourceRecord
from app.orchestration import (
    InMemoryQBAFRunRepository,
    QBAFRunRepository,
    RecursiveQBAFOrchestrator,
    run_to_record,
)
from app.providers import ProviderRegistry

router = APIRouter(prefix="/api/qbaf", tags=["qbaf"])
qbaf_repository: QBAFRunRepository = InMemoryQBAFRunRepository()


class SourcePayload(BaseModel):
    reference: str = Field(min_length=1)
    text: str = Field(min_length=1)
    title: str = ""
    retracted: bool = False
    quality_grade: str = "moderate"
    corroboration_count: int = Field(default=0, ge=0)
    statistical_flags: list[str] = Field(default_factory=list)

    def to_source_record(self) -> SourceRecord:
        return SourceRecord(
            reference=self.reference,
            text=self.text,
            title=self.title,
            retracted=self.retracted,
            quality_grade=self.quality_grade,
            corroboration_count=self.corroboration_count,
            statistical_flags=list(self.statistical_flags),
        )


class QBAFRunCreate(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    evidence_sources: list[SourcePayload] = Field(default_factory=list)
    seed_evidence: bool = False
    max_iterations: int = Field(default=8, ge=1, le=50)


def build_orchestrator(max_iterations: int) -> RecursiveQBAFOrchestrator:
    return RecursiveQBAFOrchestrator(
        registry=ProviderRegistry(),
        max_iterations=max_iterations,
    )


@router.post("/runs")
def create_qbaf_run(
    payload: QBAFRunCreate,
    _: Annotated[AuthContext, Depends(require_user_token)],
) -> dict:
    sources = {
        source.reference: source.to_source_record()
        for source in payload.evidence_sources
    }
    orchestrator = build_orchestrator(payload.max_iterations)
    run = orchestrator.run(
        payload.question,
        evidence_sources=sources,
        seed_evidence=payload.seed_evidence,
    )
    record = qbaf_repository.save(run_to_record(run, topic=payload.question))
    return record.to_dict()


@router.get("/runs/{run_id}")
def get_qbaf_run(run_id: str) -> dict:
    record = qbaf_repository.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="QBAF run not found")
    return record.to_dict()
