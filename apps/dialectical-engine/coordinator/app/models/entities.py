from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def uuid_str() -> str:
    return str(uuid.uuid4())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Debate(Base):
    __tablename__ = "debates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    root_node_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    synthesis_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    nodes: Mapped[list["Node"]] = relationship("Node", back_populates="debate", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="debate", cascade="all, delete-orphan")


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    debate_id: Mapped[str] = mapped_column(ForeignKey("debates.id"), index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("nodes.id"), nullable=True, index=True)
    node_type: Mapped[str] = mapped_column(String(16), index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    active_generation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    materialized_path: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    debate: Mapped[Debate] = relationship("Debate", back_populates="nodes")
    parent: Mapped[Optional["Node"]] = relationship("Node", remote_side=[id])
    generations: Mapped[list["Generation"]] = relationship(
        "Generation", back_populates="node", cascade="all, delete-orphan"
    )


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id"), index=True)
    model_id: Mapped[str] = mapped_column(String(120), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    argument: Mapped[str] = mapped_column(Text, default="")
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1")
    prompt_rendered: Mapped[str] = mapped_column(Text, default="")
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    node: Mapped[Node] = relationship("Node", back_populates="generations")
    worker: Mapped["Worker"] = relationship("Worker")


Index(
    "ux_generations_active_per_node",
    Generation.node_id,
    unique=True,
    sqlite_where=Generation.is_active.is_(True),
)


class Synthesis(Base):
    __tablename__ = "syntheses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    debate_id: Mapped[str] = mapped_column(ForeignKey("debates.id"), index=True)
    strongest_pro: Mapped[str] = mapped_column(Text, default="")
    strongest_con: Mapped[str] = mapped_column(Text, default="")
    verdict: Mapped[str] = mapped_column(Text, default="")
    upstream_agent_output_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    analyzer_findings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_id: Mapped[str] = mapped_column(String(120), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    status: Mapped[str] = mapped_column(String(24), default="online", index=True)
    current_job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    node_id: Mapped[Optional[str]] = mapped_column(ForeignKey("nodes.id"), nullable=True, index=True)
    debate_id: Mapped[str] = mapped_column(ForeignKey("debates.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(24), index=True)
    required_role: Mapped[str] = mapped_column(String(32), index=True)
    required_model: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    worker_id: Mapped[Optional[str]] = mapped_column(ForeignKey("workers.id"), nullable=True, index=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(36), default=uuid_str, unique=True)
    stream_buffer: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    debate: Mapped[Debate] = relationship("Debate", back_populates="jobs")


class DebateBranch(Base):
    __tablename__ = "debate_branches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    debate_id: Mapped[str] = mapped_column(ForeignKey("debates.id"), index=True)
    parent_branch_id: Mapped[Optional[str]] = mapped_column(ForeignKey("debate_branches.id"), nullable=True, index=True)
    root_node_id: Mapped[Optional[str]] = mapped_column(ForeignKey("nodes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SkillDefinition(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="provisional", index=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reuse_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AgentDefinition(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="provisional", index=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reuse_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AnalyzerRun(Base):
    __tablename__ = "analyzer_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    debate_id: Mapped[str] = mapped_column(ForeignKey("debates.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("debate_branches.id"), index=True)
    analyzer_type: Mapped[str] = mapped_column(String(80), index=True)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="complete", index=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CapabilityMatch(Base):
    __tablename__ = "capability_matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    debate_id: Mapped[str] = mapped_column(ForeignKey("debates.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("debate_branches.id"), index=True)
    capability_kind: Mapped[str] = mapped_column(String(16), index=True)
    capability_id: Mapped[str] = mapped_column(String(36), index=True)
    selection_reason: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AgentRun(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    debate_id: Mapped[str] = mapped_column(ForeignKey("debates.id"), index=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("debate_branches.id"), index=True)
    skill_id: Mapped[Optional[str]] = mapped_column(ForeignKey("skills.id"), nullable=True, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    agent_definition_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    selected_skill_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    role: Mapped[str] = mapped_column(String(120), default="")
    lens: Mapped[str] = mapped_column(String(120), default="")
    prompt_input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    job_id: Mapped[Optional[str]] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    worker_id: Mapped[Optional[str]] = mapped_column(ForeignKey("workers.id"), nullable=True, index=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    analyzer_run_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    pros: Mapped[list[str]] = mapped_column(JSON, default=list)
    cons: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


SkillCapability = SkillDefinition
AgentCapability = AgentDefinition
AgentOutput = AgentRun


class ProvenanceRecord(Base):
    __tablename__ = "provenance_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    debate_id: Mapped[str] = mapped_column(ForeignKey("debates.id"), index=True)
    branch_id: Mapped[Optional[str]] = mapped_column(ForeignKey("debate_branches.id"), nullable=True, index=True)
    artifact_kind: Mapped[str] = mapped_column(String(40), index=True)
    artifact_id: Mapped[str] = mapped_column(String(36), index=True)
    model_id: Mapped[str] = mapped_column(String(120), default="")
    worker_id: Mapped[str] = mapped_column(String(120), default="")
    prompt_id: Mapped[str] = mapped_column(String(120), default="")
    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
