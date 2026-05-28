from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Debate, Generation, Job, Node, Synthesis, Worker


STREAMING_JOB_STATUSES = {"claimed", "running"}


def iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def generation_summary(db: Session, generation_id: str | None) -> dict[str, Any] | None:
    if not generation_id:
        return None
    generation = db.get(Generation, generation_id)
    if not generation:
        return None
    worker = db.get(Worker, generation.worker_id)
    return {
        "id": generation.id,
        "model_id": generation.model_id,
        "role": generation.role,
        "argument": generation.argument,
        "worker_id": generation.worker_id,
        "worker_name": worker.name if worker else generation.worker_id,
        "created_at": iso(generation.created_at),
    }


def streaming_generation_summary(db: Session, job: Job) -> dict[str, Any]:
    worker = db.get(Worker, job.worker_id) if job.worker_id else None
    worker_name = worker.name if worker else job.worker_id or ""
    return {
        "id": f"stream:{job.id}",
        "job_id": job.id,
        "model_id": job.required_model,
        "role": job.required_role,
        "argument": job.stream_buffer or "",
        "worker_id": job.worker_id or "",
        "worker_name": worker_name,
        "created_at": iso(job.claimed_at or job.created_at),
        "is_streaming": True,
    }


def active_synthesis_summary(db: Session, job: Job) -> dict[str, Any]:
    worker = db.get(Worker, job.worker_id) if job.worker_id else None
    worker_name = worker.name if worker else job.worker_id or ""
    return {
        "id": f"stream:{job.id}",
        "job_id": job.id,
        "debate_id": job.debate_id,
        "model_id": job.required_model,
        "worker_id": job.worker_id or "",
        "worker_name": worker_name,
        "created_at": iso(job.claimed_at or job.created_at),
        "raw": job.stream_buffer or "",
        "is_streaming": True,
    }


def node_to_dict(
    db: Session,
    node: Node,
    children_by_parent: dict[str | None, list[Node]],
    streaming_jobs_by_node: dict[str, Job] | None = None,
) -> dict[str, Any]:
    streaming_job = (streaming_jobs_by_node or {}).get(node.id)
    active_generation = (
        streaming_generation_summary(db, streaming_job)
        if streaming_job
        else generation_summary(db, node.active_generation_id)
    )
    return {
        "id": node.id,
        "debate_id": node.debate_id,
        "parent_id": node.parent_id,
        "node_type": node.node_type,
        "depth": node.depth,
        "position": node.position,
        "claim": node.claim,
        "status": "generating" if streaming_job else node.status,
        "materialized_path": node.materialized_path,
        "active_generation_id": node.active_generation_id,
        "active_generation": active_generation,
        "children": [
            node_to_dict(db, child, children_by_parent, streaming_jobs_by_node)
            for child in sorted(children_by_parent.get(node.id, []), key=lambda item: item.position)
        ],
    }


def synthesis_to_dict(db: Session, synthesis: Synthesis | None) -> dict[str, Any] | None:
    if not synthesis:
        return None
    worker = db.get(Worker, synthesis.worker_id)
    return {
        "id": synthesis.id,
        "debate_id": synthesis.debate_id,
        "strongest_pro": synthesis.strongest_pro,
        "strongest_con": synthesis.strongest_con,
        "verdict": synthesis.verdict,
        "model_id": synthesis.model_id,
        "worker_id": synthesis.worker_id,
        "worker_name": worker.name if worker else synthesis.worker_id,
        "created_at": iso(synthesis.created_at),
    }


def debate_to_dict(db: Session, debate: Debate) -> dict[str, Any]:
    nodes = list(db.scalars(select(Node).where(Node.debate_id == debate.id, Node.status != "stale")).all())
    streaming_jobs = list(
        db.scalars(
            select(Job)
            .where(Job.debate_id == debate.id, Job.status.in_(STREAMING_JOB_STATUSES))
            .order_by(Job.claimed_at.desc(), Job.created_at.desc(), Job.id.desc())
        ).all()
    )
    streaming_jobs_by_node: dict[str, Job] = {}
    active_synthesis_job: Job | None = None
    for job in streaming_jobs:
        if job.job_type == "synthesize":
            active_synthesis_job = active_synthesis_job or job
        elif job.node_id and job.node_id not in streaming_jobs_by_node:
            streaming_jobs_by_node[job.node_id] = job
    children_by_parent: dict[str | None, list[Node]] = defaultdict(list)
    for node in nodes:
        children_by_parent[node.parent_id].append(node)
    root = db.get(Node, debate.root_node_id) if debate.root_node_id else None
    synthesis = db.get(Synthesis, debate.synthesis_id) if debate.synthesis_id else None
    generations = list(
        db.scalars(
            select(Generation).join(Node, Generation.node_id == Node.id).where(Node.debate_id == debate.id)
        ).all()
    )
    worker_names: set[str] = set()
    models = {generation.model_id for generation in generations}
    for generation in generations:
        worker = db.get(Worker, generation.worker_id)
        worker_names.add(worker.name if worker else generation.worker_id)
    if synthesis:
        models.add(synthesis.model_id)
        worker = db.get(Worker, synthesis.worker_id)
        worker_names.add(worker.name if worker else synthesis.worker_id)
    for job in streaming_jobs:
        models.add(job.required_model)
        if job.worker_id:
            worker = db.get(Worker, job.worker_id)
            worker_names.add(worker.name if worker else job.worker_id)
    return {
        "id": debate.id,
        "topic": debate.topic,
        "status": debate.status,
        "config": debate.config,
        "root_node_id": debate.root_node_id,
        "synthesis_id": debate.synthesis_id,
        "created_at": iso(debate.created_at),
        "completed_at": iso(debate.completed_at),
        "tree": node_to_dict(db, root, children_by_parent, streaming_jobs_by_node) if root else None,
        "synthesis": synthesis_to_dict(db, synthesis),
        "active_synthesis": active_synthesis_summary(db, active_synthesis_job) if active_synthesis_job else None,
        "workers": sorted(worker_names),
        "models": sorted(models),
        "node_count": len(nodes),
    }
