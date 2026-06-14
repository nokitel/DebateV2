from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentCapability,
    AgentOutput,
    AgentRun,
    AnalyzerRun,
    CapabilityMatch,
    Debate,
    DebateBranch,
    Generation,
    Job,
    Node,
    ProvenanceRecord,
    SkillCapability,
    Synthesis,
    Worker,
)


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
        "upstream_agent_output_ids": synthesis.upstream_agent_output_ids or [],
        "upstream_agent_run_ids": synthesis.upstream_agent_output_ids or [],
        "analyzer_findings": synthesis.analyzer_findings or {},
        "provenance": synthesis.provenance or {},
        "model_id": synthesis.model_id,
        "worker_id": synthesis.worker_id,
        "worker_name": worker.name if worker else synthesis.worker_id,
        "created_at": iso(synthesis.created_at),
    }


def branch_to_dict(branch: DebateBranch) -> dict[str, Any]:
    return {
        "id": branch.id,
        "debate_id": branch.debate_id,
        "parent_branch_id": branch.parent_branch_id,
        "root_node_id": branch.root_node_id,
        "status": branch.status,
        "created_at": iso(branch.created_at),
    }


def analyzer_run_to_dict(run: AnalyzerRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "debate_id": run.debate_id,
        "branch_id": run.branch_id,
        "analyzer_type": run.analyzer_type,
        "output": run.output,
        "status": run.status,
        "provenance": run.provenance,
        "created_at": iso(run.created_at),
    }


def capability_match_to_dict(db: Session, match: CapabilityMatch) -> dict[str, Any]:
    model = SkillCapability if match.capability_kind == "skill" else AgentCapability
    capability = db.get(model, match.capability_id)
    definition = capability.definition if capability and isinstance(capability.definition, dict) else {}
    return {
        "id": match.capability_id,
        "match_id": match.id,
        "debate_id": match.debate_id,
        "branch_id": match.branch_id,
        "selection_reason": match.selection_reason,
        "score": match.score,
        "status": capability.status if capability else None,
        "reuse_count": capability.reuse_count if capability else 0,
        "definition": definition,
        "name": definition.get("name"),
        "created_at": iso(match.created_at),
    }


def agent_output_to_dict(output: AgentOutput) -> dict[str, Any]:
    return {
        "id": output.id,
        "debate_id": output.debate_id,
        "branch_id": output.branch_id,
        "skill_id": output.skill_id,
        "agent_id": output.agent_id,
        "analyzer_run_ids": output.analyzer_run_ids or [],
        "pros": output.pros or [],
        "cons": output.cons or [],
        "summary": output.summary,
        "confidence": output.confidence,
        "provenance": output.provenance or {},
        "created_at": iso(output.created_at),
    }


def agent_run_to_dict(db: Session, run: AgentRun) -> dict[str, Any]:
    agent = db.get(AgentCapability, run.agent_definition_id or run.agent_id)
    agent_definition = agent.definition if agent and isinstance(agent.definition, dict) else {}
    skills = [db.get(SkillCapability, skill_id) for skill_id in (run.selected_skill_ids or [])]
    skill_definitions = [skill.definition for skill in skills if skill and isinstance(skill.definition, dict)]
    return {
        "id": run.id,
        "debate_id": run.debate_id,
        "branch_id": run.branch_id,
        "agent_definition_id": run.agent_definition_id or run.agent_id,
        "selected_skill_ids": run.selected_skill_ids or ([run.skill_id] if run.skill_id else []),
        "agent": agent_definition,
        "agent_name": agent_definition.get("name") or run.role,
        "role": run.role,
        "lens": run.lens,
        "status": run.status,
        "prompt_input": run.prompt_input or {},
        "output": run.output or {},
        "pros": run.pros or [],
        "cons": run.cons or [],
        "summary": run.summary,
        "confidence": run.confidence,
        "skills_used": [
            {
                "id": skill.id,
                "name": definition.get("name"),
                "type": definition.get("type") or definition.get("kind"),
                "description": definition.get("description"),
                "tags": definition.get("tags") or definition.get("trigger", {}).get("domain_tags", []),
            }
            for skill, definition in zip([skill for skill in skills if skill], skill_definitions, strict=False)
        ],
        "job_id": run.job_id,
        "worker_id": run.worker_id,
        "model_id": run.model_id,
        "provenance": run.provenance or {},
        "created_at": iso(run.created_at),
    }


def provenance_to_dict(record: ProvenanceRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "debate_id": record.debate_id,
        "branch_id": record.branch_id,
        "artifact_kind": record.artifact_kind,
        "artifact_id": record.artifact_id,
        "model_id": record.model_id,
        "worker_id": record.worker_id,
        "prompt_id": record.prompt_id,
        "job_id": record.job_id,
        "metadata": record.metadata_json,
        "created_at": iso(record.created_at),
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
        if job.job_type in {"synthesize", "v2_synthesize"}:
            active_synthesis_job = active_synthesis_job or job
        elif job.job_type in {"decompose", "argue", "v2_pov"} and job.node_id and job.node_id not in streaming_jobs_by_node:
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
    branches = list(
        db.scalars(select(DebateBranch).where(DebateBranch.debate_id == debate.id).order_by(DebateBranch.created_at.asc())).all()
    )
    analyzer_runs = list(
        db.scalars(select(AnalyzerRun).where(AnalyzerRun.debate_id == debate.id).order_by(AnalyzerRun.created_at.asc())).all()
    )
    matches = list(
        db.scalars(select(CapabilityMatch).where(CapabilityMatch.debate_id == debate.id).order_by(CapabilityMatch.created_at.asc())).all()
    )
    agent_outputs = list(
        db.scalars(select(AgentOutput).where(AgentOutput.debate_id == debate.id).order_by(AgentOutput.created_at.asc())).all()
    )
    agent_runs = list(
        db.scalars(select(AgentRun).where(AgentRun.debate_id == debate.id).order_by(AgentRun.created_at.asc())).all()
    )
    serialized_agent_runs = [agent_run_to_dict(db, run) for run in agent_runs]
    skills_used = []
    seen_skill_names: set[str] = set()
    for run in serialized_agent_runs:
        for skill in run["skills_used"]:
            name = skill.get("name")
            if name and name not in seen_skill_names:
                seen_skill_names.add(name)
                skills_used.append(name)
    provenance_records = list(
        db.scalars(select(ProvenanceRecord).where(ProvenanceRecord.debate_id == debate.id).order_by(ProvenanceRecord.created_at.asc())).all()
    )
    return {
        "id": debate.id,
        "topic": debate.topic,
        "status": debate.status,
        "config": debate.config,
        "direct_answer": None,
        "root_node_id": debate.root_node_id,
        "synthesis_id": debate.synthesis_id,
        "created_at": iso(debate.created_at),
        "completed_at": iso(debate.completed_at),
        "tree": node_to_dict(db, root, children_by_parent, streaming_jobs_by_node) if root else None,
        "synthesis": synthesis_to_dict(db, synthesis),
        "active_synthesis": active_synthesis_summary(db, active_synthesis_job) if active_synthesis_job else None,
        "branch_lineage": [branch_to_dict(branch) for branch in branches],
        "analyzer_runs": [analyzer_run_to_dict(run) for run in analyzer_runs],
        "selected_skills": [capability_match_to_dict(db, match) for match in matches if match.capability_kind == "skill"],
        "selected_agents": [capability_match_to_dict(db, match) for match in matches if match.capability_kind == "agent"],
        "agent_outputs": [agent_output_to_dict(output) for output in agent_outputs],
        "agent_runs": serialized_agent_runs,
        "skills_used": skills_used,
        "provenance_records": [provenance_to_dict(record) for record in provenance_records],
        "workers": sorted(worker_names),
        "models": sorted(models),
        "node_count": len(nodes),
    }
