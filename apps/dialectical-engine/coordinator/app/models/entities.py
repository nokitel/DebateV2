from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
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
