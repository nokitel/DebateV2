from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import RUNTIME_SETTINGS_KEY, load_settings
from app.core.write_lock import commit_write, flush_write
from app.models.entities import Debate, Generation, Job, Node, Setting, Synthesis, Worker, now_utc, uuid_str
from app.services.events import event_bus
from app.services.prompts import render_prompt
from app.services.routing import routing_engine
from app.services.serialization import debate_to_dict, iso
from app.services.spend import capped_model_ids


DEFAULT_DEBATE_CONFIG = {
    "max_depth": 2,
    "branching": 2,
    "max_tokens": 800,
}
ROLE_OVERRIDE_KEYS = ("role_overrides", "roles", "routing")
MAX_STREAM_DELTA_CHARS = 16_384
MAX_STREAM_BUFFER_CHARS = 200_000
MUTABLE_JOB_STATUSES = {"claimed", "running"}


class StaleJobMutationError(ValueError):
    pass


class StreamOffsetError(ValueError):
    pass


def merged_debate_config(config: dict[str, Any] | None) -> dict[str, Any]:
    incoming = dict(config or {})
    raw_role_overrides = None
    for key in ROLE_OVERRIDE_KEYS:
        if key in incoming:
            raw_role_overrides = incoming.pop(key)
            break
    merged = {**DEFAULT_DEBATE_CONFIG, **incoming}
    merged["max_depth"] = bounded_config_int(merged, "max_depth", 2, 1, 5)
    merged["branching"] = bounded_config_int(merged, "branching", 2, 2, 6)
    merged["max_tokens"] = bounded_config_int(merged, "max_tokens", 800, 128, 4000)
    if raw_role_overrides is not None:
        from app.api.settings import validate_routing

        merged["role_overrides"] = validate_routing(raw_role_overrides)
    return merged


def bounded_config_int(config: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    raw = config.get(key, default)
    if raw is None or isinstance(raw, bool):
        raise ValueError(f"{key} must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{key} must be an integer") from None
    return max(minimum, min(value, maximum))


def sanitize_text(value: str, limit: int = 12_000) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def enabled_models(db: Session) -> set[str] | None:
    setting = db.get(Setting, RUNTIME_SETTINGS_KEY)
    if not setting:
        return None
    values = setting.value.get("enabled_models") or []
    if not isinstance(values, list):
        return None
    cleaned = {value.strip() for value in values if isinstance(value, str) and value.strip()}
    configured = configured_routing_models()
    if configured:
        cleaned &= configured
    return cleaned or None


def configured_routing_models(roles: dict[str, dict[str, Any]] | None = None) -> set[str]:
    models: set[str] = set()
    for config in (roles or routing_engine.as_dict() or {}).values():
        if config.get("primary"):
            models.add(str(config["primary"]))
        models.update(str(model) for model in config.get("fallback", []) if model)
        models.update(str(model) for model in config.get("pool", []) if model)
    return models


def routing_roles_for_debate(debate: Debate | None) -> dict[str, dict[str, Any]]:
    roles = {role: dict(role_config) for role, role_config in (routing_engine.as_dict() or {}).items()}
    if not debate or not isinstance(debate.config, dict):
        return roles
    overrides = debate.config.get("role_overrides")
    if not isinstance(overrides, dict):
        return roles
    for role, role_config in overrides.items():
        if isinstance(role, str) and isinstance(role_config, dict):
            roles[role] = dict(role_config)
    return roles


def routing_allowed_models(db: Session) -> set[str] | None:
    allowed = enabled_models(db)
    configured = configured_routing_models()
    capped = capped_model_ids(db, allowed or configured)
    if not capped:
        return allowed
    return (allowed or configured) - capped


def worker_capability_set(worker: Worker) -> set[str]:
    return {str(capability).strip() for capability in worker.capabilities or [] if str(capability).strip()}


def online_capabilities(db: Session) -> set[str]:
    settings = load_settings()
    allowed = routing_allowed_models(db)
    cutoff = now_utc() - timedelta(seconds=settings.worker_offline_seconds)
    workers = db.scalars(select(Worker).where(Worker.last_seen >= cutoff, Worker.status != "offline")).all()
    caps: set[str] = set()
    for worker in workers:
        caps.update(worker_capability_set(worker))
    if allowed is not None:
        caps &= allowed
    return caps


def role_for_node(node_type: str) -> str:
    return "proposer" if node_type == "PRO" else "opponent"


def claim_author_exclusions(db: Session, role: str, parent: Node | None, debate: Debate | None = None) -> set[str]:
    if debate is None and parent is not None:
        debate = db.get(Debate, parent.debate_id)
    role_config = routing_roles_for_debate(debate).get(role, {})
    if role_config.get("constraint") != "not_same_as_claim_author" or not parent:
        return set()
    active_generation = db.get(Generation, parent.active_generation_id) if parent.active_generation_id else None
    if not active_generation:
        return set()
    capabilities = online_capabilities(db)
    if any(model != active_generation.model_id for model in capabilities):
        return {active_generation.model_id}
    return set()


def make_deadline() -> Any:
    settings = load_settings()
    return now_utc() + timedelta(seconds=max(settings.worker_poll_seconds * 2, settings.job_fallback_seconds))


def create_job(
    db: Session,
    debate_id: str,
    job_type: str,
    role: str,
    node_id: str | None,
    required_model: str | None = None,
    exclude_models: set[str] | None = None,
) -> Job:
    allowed_models = routing_allowed_models(db)
    debate = db.get(Debate, debate_id)
    role_configs = routing_roles_for_debate(debate)
    if required_model is not None:
        if allowed_models is not None and required_model not in allowed_models:
            raise ValueError(f"Model {required_model} is not currently allowed")
        model = required_model
    else:
        model = routing_engine.choose(
            role,
            online_capabilities(db),
            exclude_models=exclude_models,
            allowed_models=allowed_models,
            roles=role_configs,
        )
    job = Job(
        debate_id=debate_id,
        node_id=node_id,
        job_type=job_type,
        required_role=role,
        required_model=model,
        status="pending",
        deadline=make_deadline(),
    )
    db.add(job)
    return job


def create_debate(db: Session, topic: str, config: dict[str, Any] | None = None) -> Debate:
    topic = sanitize_text(topic, 2_000)
    if not topic:
        raise ValueError("Topic is required")
    debate = Debate(topic=topic, status="generating", config=merged_debate_config(config))
    db.add(debate)
    flush_write(db)
    root = Node(
        debate_id=debate.id,
        parent_id=None,
        node_type="ROOT_CLAIM",
        depth=0,
        position=0,
        claim=topic,
        status="pending",
        materialized_path="/0",
    )
    db.add(root)
    flush_write(db)
    debate.root_node_id = root.id
    create_job(db, debate.id, "decompose", "decomposer", root.id)
    commit_write(db)
    db.refresh(debate)
    return debate


def extract_jsonish(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    text = str(result).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("Model output did not contain a valid JSON object")


def create_generation(
    db: Session,
    job: Job,
    node: Node,
    argument: str,
    prompt_rendered: str,
    metadata: dict[str, Any],
) -> Generation:
    db.query(Generation).filter(Generation.node_id == node.id, Generation.is_active.is_(True)).update(
        {"is_active": False}
    )
    generation = Generation(
        node_id=node.id,
        model_id=job.required_model,
        role=job.required_role,
        argument=sanitize_text(argument),
        prompt_version="v1",
        prompt_rendered=prompt_rendered,
        tokens_in=metadata.get("tokens_in"),
        tokens_out=metadata.get("tokens_out"),
        latency_ms=int(metadata.get("latency_ms") or 0),
        is_active=True,
        worker_id=str(job.worker_id),
    )
    db.add(generation)
    flush_write(db)
    node.active_generation_id = generation.id
    node.status = "complete"
    return generation


def normalized_decomposition_children(payload: dict[str, Any], debate: Debate) -> list[dict[str, str]]:
    branching = int(debate.config.get("branching", 2))
    raw_children = payload.get("children")
    rows = raw_children if isinstance(raw_children, list) else []
    children: list[dict[str, str]] = []
    for position, row in enumerate(rows):
        if len(children) >= branching:
            break
        if isinstance(row, dict):
            claim = sanitize_text(str(row.get("claim") or ""))
            node_type = str(row.get("node_type") or "").upper()
        else:
            claim = sanitize_text(str(row))
            node_type = ""
        if not claim:
            continue
        if node_type not in {"PRO", "CON"}:
            node_type = "PRO" if position % 2 == 0 else "CON"
        children.append({"node_type": node_type, "claim": claim})
    while len(children) < branching:
        node_type = "PRO" if len(children) % 2 == 0 else "CON"
        stance = "supporting" if node_type == "PRO" else "opposing"
        children.append(
            {
                "node_type": node_type,
                "claim": f"A {stance} opening line for: {debate.topic}",
            }
        )
    return children


def spawn_child_argument_jobs(db: Session, debate: Debate, parent: Node, argument: str) -> None:
    max_depth = int(debate.config.get("max_depth", 2))
    if parent.depth >= max_depth:
        return
    existing = db.scalar(select(Node).where(Node.parent_id == parent.id, Node.status != "stale").limit(1))
    if existing:
        return
    branching = int(debate.config.get("branching", 2))
    child_types = ["PRO", "CON"]
    for position in range(branching):
        node_type = child_types[position % 2]
        stance = "supports" if node_type == "PRO" else "challenges"
        child = Node(
            debate_id=debate.id,
            parent_id=parent.id,
            node_type=node_type,
            depth=parent.depth + 1,
            position=position,
            claim=f"A {stance} line for: {argument[:180]}",
            status="pending",
            materialized_path=f"{parent.materialized_path}/{position}",
        )
        db.add(child)
        flush_write(db)
        role = role_for_node(node_type)
        create_job(
            db,
            debate.id,
            "argue",
            role,
            child.id,
            exclude_models=claim_author_exclusions(db, role, parent, debate),
        )


def stale_descendants(db: Session, node: Node) -> None:
    prefix = f"{node.materialized_path}/"
    descendants = db.scalars(
        select(Node).where(
            Node.debate_id == node.debate_id,
            Node.materialized_path.startswith(prefix),
            Node.status != "stale",
        )
    ).all()
    descendant_ids = [descendant.id for descendant in descendants]
    for descendant in descendants:
        descendant.status = "stale"
    cancel_active_jobs_for_nodes(db, descendant_ids, "Ancestor was regenerated")


def cancel_active_jobs_for_nodes(db: Session, node_ids: list[str], reason: str) -> None:
    if not node_ids:
        return
    jobs = db.scalars(
        select(Job).where(
            Job.node_id.in_(node_ids),
            Job.status.in_(["pending", "claimed", "running"]),
        )
    ).all()
    for job in jobs:
        release_job_claim(db, job)
        job.status = "failed"
        job.error = reason
        job.stream_buffer = ""


def cancel_active_jobs_for_node(db: Session, node: Node, reason: str) -> None:
    cancel_active_jobs_for_nodes(db, [node.id], reason)


def cancel_active_synthesis_jobs(db: Session, debate_id: str, reason: str) -> None:
    jobs = db.scalars(
        select(Job).where(
            Job.debate_id == debate_id,
            Job.job_type == "synthesize",
            Job.status.in_(["pending", "claimed", "running"]),
        )
    ).all()
    for job in jobs:
        release_job_claim(db, job)
        job.status = "failed"
        job.error = reason
        job.stream_buffer = ""


def pending_or_running_jobs(db: Session, debate_id: str) -> list[Job]:
    return list(
        db.scalars(
            select(Job).where(
                Job.debate_id == debate_id,
                Job.status.in_(["pending", "claimed", "running"]),
            )
        ).all()
    )


def capable_online_workers(db: Session, model_id: str) -> list[Worker]:
    allowed = routing_allowed_models(db)
    if allowed is not None and model_id not in allowed:
        return []
    settings = load_settings()
    cutoff = now_utc() - timedelta(seconds=settings.worker_offline_seconds)
    workers = db.scalars(select(Worker).where(Worker.last_seen >= cutoff, Worker.status != "offline")).all()
    return [worker for worker in workers if model_id in worker_capability_set(worker)]


def worker_debate_loads(db: Session, debate_id: str, workers: list[Worker]) -> dict[str, int]:
    worker_ids = [worker.id for worker in workers]
    loads = {worker_id: 0 for worker_id in worker_ids}
    if not worker_ids:
        return loads

    generation_rows = db.execute(
        select(Generation.worker_id, func.count(Generation.id))
        .join(Node, Generation.node_id == Node.id)
        .where(Node.debate_id == debate_id, Generation.worker_id.in_(worker_ids))
        .group_by(Generation.worker_id)
    ).all()
    for worker_id, count in generation_rows:
        loads[str(worker_id)] += int(count)

    synthesis_rows = db.execute(
        select(Synthesis.worker_id, func.count(Synthesis.id))
        .where(Synthesis.debate_id == debate_id, Synthesis.worker_id.in_(worker_ids))
        .group_by(Synthesis.worker_id)
    ).all()
    for worker_id, count in synthesis_rows:
        loads[str(worker_id)] += int(count)

    running_rows = db.execute(
        select(Job.worker_id, func.count(Job.id))
        .where(
            Job.debate_id == debate_id,
            Job.worker_id.in_(worker_ids),
            Job.status.in_(["claimed", "running"]),
        )
        .group_by(Job.worker_id)
    ).all()
    for worker_id, count in running_rows:
        loads[str(worker_id)] += int(count)
    return loads


def worker_can_claim_job(db: Session, worker: Worker, job: Job, now: Any) -> bool:
    capable_workers = capable_online_workers(db, job.required_model)
    if len(capable_workers) <= 1:
        return True

    settings = load_settings()
    loads = worker_debate_loads(db, job.debate_id, capable_workers)
    worker_load = loads.get(worker.id, 0)
    min_load = min(loads.values()) if loads else worker_load
    if worker_load <= min_load:
        return True

    comparable_now = now.replace(tzinfo=None) if job.created_at.tzinfo is None else now
    waited = comparable_now - job.created_at
    if waited >= timedelta(seconds=settings.worker_poll_seconds):
        return True

    idle_lower_load_worker = any(
        other.id != worker.id
        and loads.get(other.id, 0) < worker_load
        and not other.current_job_id
        for other in capable_workers
    )
    return not idle_lower_load_worker


def mark_worker_seen(worker: Worker, now: Any) -> None:
    worker.last_seen = now
    if worker.status != "degraded":
        worker.status = "online"


def release_job_claim(db: Session, job: Job) -> None:
    if job.worker_id:
        worker = db.get(Worker, job.worker_id)
        if worker and worker.current_job_id == job.id:
            worker.current_job_id = None
    job.worker_id = None
    job.claimed_at = None


def reset_job_target_for_retry(db: Session, job: Job) -> None:
    debate = db.get(Debate, job.debate_id)
    if debate and debate.status not in {"archived", "failed"}:
        debate.status = "generating"
    if job.node_id:
        node = db.get(Node, job.node_id)
        if node and node.status != "stale":
            node.status = "pending"


def requeue_active_jobs_for_worker(db: Session, worker: Worker, reason: str) -> None:
    jobs = db.scalars(
        select(Job).where(
            Job.worker_id == worker.id,
            Job.status.in_(["claimed", "running"]),
        )
    ).all()
    for job in jobs:
        release_job_claim(db, job)
        reset_job_target_for_retry(db, job)
        job.status = "pending"
        job.error = reason
        job.stream_buffer = ""
        job.deadline = make_deadline()


def archive_debate(db: Session, debate: Debate) -> None:
    debate.status = "archived"
    for job in pending_or_running_jobs(db, debate.id):
        release_job_claim(db, job)
        job.status = "failed"
        job.error = "Debate archived"
    commit_write(db)


def reroute_unavailable_pending_jobs(db: Session, now: Any) -> None:
    jobs = db.scalars(select(Job).where(Job.status == "pending", Job.deadline < now)).all()
    for job in jobs:
        if capable_online_workers(db, job.required_model):
            continue
        constraint_excludes: set[str] = set()
        if job.node_id:
            node = db.get(Node, job.node_id)
            parent = db.get(Node, node.parent_id) if node and node.parent_id else None
            debate = db.get(Debate, job.debate_id)
            constraint_excludes = claim_author_exclusions(db, job.required_role, parent, debate)
            role_configs = routing_roles_for_debate(debate)
        else:
            debate = db.get(Debate, job.debate_id)
            role_configs = routing_roles_for_debate(debate)
        try:
            replacement = routing_engine.choose(
                job.required_role,
                online_capabilities(db),
                exclude_models={job.required_model, *constraint_excludes},
                allowed_models=routing_allowed_models(db),
                roles=role_configs,
            )
        except ValueError:
            continue
        if replacement != job.required_model:
            job.required_model = replacement
            job.deadline = make_deadline()
            job.attempts += 1


def maybe_queue_synthesis(db: Session, debate: Debate) -> Job | None:
    if debate.synthesis_id:
        return None
    pending_nodes = db.scalar(
        select(Node.id).where(Node.debate_id == debate.id, Node.status.in_(["pending", "generating"])).limit(1)
    )
    if pending_nodes:
        return None
    active_jobs = [
        job
        for job in pending_or_running_jobs(db, debate.id)
        if job.job_type in {"decompose", "argue", "synthesize"}
    ]
    if active_jobs:
        return None
    existing_synthesis_job = db.scalar(
        select(Job)
        .where(
            Job.debate_id == debate.id,
            Job.job_type == "synthesize",
            Job.status.in_(["pending", "claimed", "running"]),
        )
        .limit(1)
    )
    if existing_synthesis_job:
        return None
    return create_job(db, debate.id, "synthesize", "synthesizer", None)


def try_claim_pending_job(db: Session, job: Job, worker: Worker, now: Any) -> bool:
    deadline = make_deadline()
    result = db.execute(
        update(Job)
        .where(Job.id == job.id, Job.status == "pending")
        .values(
            status="running",
            worker_id=worker.id,
            claimed_at=now,
            deadline=deadline,
            stream_buffer="",
            attempts=Job.attempts + 1,
        )
    )
    if result.rowcount != 1:
        db.expire(job)
        return False
    worker.current_job_id = job.id
    mark_worker_seen(worker, now)
    commit_write(db)
    db.refresh(job)
    return True


def ensure_mutable_claim(db: Session, job: Job) -> None:
    expected_worker_id = job.worker_id
    db.refresh(job)
    if not expected_worker_id or job.worker_id != expected_worker_id:
        raise StaleJobMutationError("Job is not claimed by this worker")
    if job.status not in MUTABLE_JOB_STATUSES:
        raise StaleJobMutationError(f"Job is {job.status} and cannot be mutated")


def claim_pending_job(db: Session, worker: Worker) -> Job | None:
    capabilities = worker_capability_set(worker)
    allowed_models = routing_allowed_models(db)
    if allowed_models is not None:
        capabilities &= allowed_models
    now = now_utc()
    reroute_unavailable_pending_jobs(db, now)
    expired = db.scalars(
        select(Job).where(Job.status.in_(["claimed", "running"]), Job.deadline < now)
    ).all()
    for job in expired:
        job.status = "pending"
        release_job_claim(db, job)
        reset_job_target_for_retry(db, job)
        job.stream_buffer = ""
        job.error = "Job deadline expired"
        job.deadline = make_deadline()
        job.attempts += 1
    flush_write(db)

    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.status == "pending", Job.required_model.in_(capabilities))
            .order_by(Job.created_at.asc())
        ).all()
    )
    job = next((candidate for candidate in jobs if worker_can_claim_job(db, worker, candidate, now)), None)
    if not job:
        mark_worker_seen(worker, now)
        commit_write(db)
        return None
    for candidate in [job, *[candidate for candidate in jobs if candidate.id != job.id]]:
        if worker_can_claim_job(db, worker, candidate, now) and try_claim_pending_job(db, candidate, worker, now):
            return candidate
    mark_worker_seen(worker, now)
    commit_write(db)
    return None


def render_job_payload(db: Session, job: Job) -> dict[str, Any]:
    debate = db.get(Debate, job.debate_id)
    if not debate:
        raise ValueError("Debate not found")
    node = db.get(Node, job.node_id) if job.node_id else None
    claim = node.claim if node else debate.topic
    if job.job_type.startswith("v2_"):
        from app.services.dialectical_v2 import render_v2_job_prompt

        system, user = render_v2_job_prompt(db, job)
    elif job.job_type == "synthesize":
        context = json.dumps(debate_to_dict(db, debate), default=str)
        system, user = render_prompt("synthesizer", debate.topic, debate.topic, 0, context=context)
    else:
        prompt_name = "decomposer" if job.required_role == "decomposer" else job.required_role
        system, user = render_prompt(prompt_name, debate.topic, claim, node.depth if node else 0)
    return {
        "id": job.id,
        "debate_id": job.debate_id,
        "node_id": job.node_id,
        "job_type": job.job_type,
        "required_role": job.required_role,
        "required_model": job.required_model,
        "deadline": iso(job.deadline),
        "prompt": {
            "system": system,
            "user": user,
            "max_tokens": int(debate.config.get("max_tokens", 800)),
        },
    }


async def publish_job_started(db: Session, job: Job) -> None:
    if job.job_type in {"synthesize", "v2_synthesize"}:
        await event_bus.publish(
            job.debate_id,
            "synthesis_started",
            {"debate_id": job.debate_id, "model_id": job.required_model, "worker_id": job.worker_id},
        )
        return
    if job.job_type.startswith("v2_"):
        await event_bus.publish(
            job.debate_id,
            "artifact_started",
            {
                "debate_id": job.debate_id,
                "job_id": job.id,
                "job_type": job.job_type,
                "model_id": job.required_model,
                "worker_id": job.worker_id,
                "role": job.required_role,
            },
        )
        return
    await event_bus.publish(
        job.debate_id,
        "node_started",
        {
            "node_id": job.node_id,
            "model_id": job.required_model,
            "worker_id": job.worker_id,
            "role": job.required_role,
        },
    )


async def append_stream_delta(db: Session, job: Job, delta: str, offset: int | None = None) -> None:
    if not delta:
        return
    ensure_mutable_claim(db, job)
    if len(delta) > MAX_STREAM_DELTA_CHARS:
        raise ValueError(f"stream delta exceeds {MAX_STREAM_DELTA_CHARS} characters")
    current_buffer = job.stream_buffer or ""
    if offset is not None:
        if offset < 0:
            raise StreamOffsetError("stream offset cannot be negative")
        if offset < len(current_buffer):
            existing = current_buffer[offset : offset + len(delta)]
            if existing == delta:
                return
            raise StreamOffsetError("stream offset does not match buffered output")
        if offset > len(current_buffer):
            raise StreamOffsetError("stream offset is ahead of buffered output")
    if len(current_buffer) + len(delta) > MAX_STREAM_BUFFER_CHARS:
        raise ValueError(f"stream buffer exceeds {MAX_STREAM_BUFFER_CHARS} characters")
    job.stream_buffer = current_buffer + delta
    job.status = "running"
    job.deadline = make_deadline()
    commit_write(db)
    if job.job_type in {"synthesize", "v2_synthesize"}:
        await event_bus.publish(job.debate_id, "synthesis_token", {"debate_id": job.debate_id, "delta": delta})
    elif job.job_type.startswith("v2_"):
        await event_bus.publish(
            job.debate_id,
            "artifact_token",
            {"debate_id": job.debate_id, "job_id": job.id, "job_type": job.job_type, "delta": delta},
        )
    else:
        await event_bus.publish(job.debate_id, "node_token", {"node_id": job.node_id, "delta": delta})


async def complete_job(db: Session, job: Job, result: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    ensure_mutable_claim(db, job)
    debate = db.get(Debate, job.debate_id)
    if not debate:
        raise ValueError("Debate not found")
    worker = db.get(Worker, job.worker_id) if job.worker_id else None
    if worker:
        worker.current_job_id = None
        worker.last_seen = now_utc()
        worker.status = "online"
    job.status = "complete"

    if job.job_type == "decompose":
        node = db.get(Node, job.node_id)
        if not node:
            raise ValueError("Root node not found")
        payload = extract_jsonish(result)
        node.claim = sanitize_text(payload.get("root_claim") or node.claim)
        root_argument = payload.get("argument") or "Debate decomposed into initial pro and con claims."
        create_generation(db, job, node, root_argument, job.stream_buffer or json.dumps(payload), metadata)
        stale_descendants(db, node)
        children = normalized_decomposition_children(payload, debate)
        for position, child_payload in enumerate(children):
            child = Node(
                debate_id=debate.id,
                parent_id=node.id,
                node_type=child_payload["node_type"],
                depth=1,
                position=position,
                claim=child_payload["claim"],
                status="pending",
                materialized_path=f"{node.materialized_path}/{position}",
            )
            db.add(child)
            flush_write(db)
            role = role_for_node(child.node_type)
            create_job(
                db,
                debate.id,
                "argue",
                role,
                child.id,
                exclude_models=claim_author_exclusions(db, role, node, debate),
            )
        commit_write(db)
        await event_bus.publish(job.debate_id, "tree_ready", {"tree": debate_to_dict(db, debate)})
        await event_bus.publish(job.debate_id, "node_complete", {"node_id": node.id, "generation_id": node.active_generation_id})

    elif job.job_type == "argue":
        node = db.get(Node, job.node_id)
        if not node:
            raise ValueError("Node not found")
        argument = result.get("argument") if isinstance(result, dict) else str(result)
        generation = create_generation(db, job, node, argument, job.stream_buffer or str(result), metadata)
        spawn_child_argument_jobs(db, debate, node, generation.argument)
        flush_write(db)
        maybe_queue_synthesis(db, debate)
        commit_write(db)
        await event_bus.publish(job.debate_id, "node_complete", {"node_id": node.id, "generation_id": generation.id})

    elif job.job_type == "synthesize":
        payload = extract_jsonish(result)
        synthesis = Synthesis(
            debate_id=debate.id,
            strongest_pro=sanitize_text(payload.get("strongest_pro", "")),
            strongest_con=sanitize_text(payload.get("strongest_con", "")),
            verdict=sanitize_text(payload.get("verdict", "")),
            model_id=job.required_model,
            worker_id=str(job.worker_id),
        )
        db.add(synthesis)
        flush_write(db)
        debate.synthesis_id = synthesis.id
        debate.status = "complete"
        debate.completed_at = now_utc()
        commit_write(db)
        await event_bus.publish(job.debate_id, "synthesis_complete", {"synthesis": payload})
        await event_bus.publish(job.debate_id, "debate_complete", {"debate_id": debate.id})
    elif job.job_type.startswith("v2_"):
        from app.services.dialectical_v2 import complete_v2_worker_job

        await complete_v2_worker_job(db, job, extract_jsonish(result), metadata)
    else:
        raise ValueError(f"Unsupported job type {job.job_type}")

    db.refresh(debate)
    return debate_to_dict(db, debate)


async def fail_job(db: Session, job: Job, reason: str, retryable: bool) -> None:
    ensure_mutable_claim(db, job)
    job.error = sanitize_text(reason, 2_000)
    job.status = "pending" if retryable else "failed"
    if job.worker_id:
        worker = db.get(Worker, job.worker_id)
        if worker:
            worker.current_job_id = None
            worker.status = "degraded" if retryable else worker.status
    if retryable:
        release_job_claim(db, job)
        job.stream_buffer = ""
        job.deadline = make_deadline()
    else:
        debate = db.get(Debate, job.debate_id)
        if debate:
            debate.status = "failed"
    if job.node_id and not job.job_type.startswith("v2_"):
        node = db.get(Node, job.node_id)
        if node:
            node.status = "pending" if retryable else "failed"
    commit_write(db)
    if job.node_id and not job.job_type.startswith("v2_"):
        await event_bus.publish(job.debate_id, "node_failed", {"node_id": job.node_id, "reason": reason, "retry_in_s": 5})
    else:
        await event_bus.publish(job.debate_id, "error", {"scope": job.job_type, "message": reason, "retry_in_s": 5})


async def regenerate_node(db: Session, node: Node, model_id: str | None = None) -> Job:
    if model_id is not None:
        model_id = model_id.strip()
        if not model_id:
            raise ValueError("model_id must be a non-empty string")
    debate = db.get(Debate, node.debate_id)
    if not debate:
        raise ValueError("Debate not found")
    active_generation = db.get(Generation, node.active_generation_id) if node.active_generation_id else None
    online_models = online_capabilities(db)
    role = "decomposer" if node.node_type == "ROOT_CLAIM" else role_for_node(node.node_type)
    job_type = "decompose" if node.node_type == "ROOT_CLAIM" else "argue"
    parent = db.get(Node, node.parent_id) if node.parent_id else None
    role_configs = routing_roles_for_debate(debate)
    constrained_excludes = claim_author_exclusions(db, role, parent, debate)
    if model_id and model_id not in (configured_routing_models(role_configs) | online_models):
        raise ValueError(f"Model {model_id} is not configured or online")
    if model_id and model_id in constrained_excludes:
        raise ValueError(f"Model {model_id} violates role constraint {role}: not_same_as_claim_author")
    exclude = (
        {active_generation.model_id}
        if active_generation and not model_id and any(model != active_generation.model_id for model in online_models)
        else set()
    )
    exclude |= constrained_excludes if not model_id else set()
    cancel_active_jobs_for_node(db, node, "Node regeneration superseded")
    cancel_active_synthesis_jobs(db, debate.id, "Node regeneration superseded synthesis")
    job = create_job(
        db,
        debate.id,
        job_type,
        role,
        node.id,
        required_model=model_id,
        exclude_models=exclude,
    )
    stale_descendants(db, node)
    node.status = "pending"
    debate.status = "generating"
    debate.synthesis_id = None
    debate.completed_at = None
    commit_write(db)
    return job


def markdown_export(db: Session, debate: Debate) -> str:
    data = debate_to_dict(db, debate)
    models = ", ".join(data["models"]) or "none"
    workers = ", ".join(data["workers"]) or "none"
    lines = [
        f"# Debate: {data['topic']}",
        "",
        f"**Created:** {data['created_at']} - **Workers:** {workers} - **Models:** {models} - "
        f"**Depth:** {data['config'].get('max_depth')} - **Nodes:** {data['node_count']}",
        "",
        "## Synthesis",
        "",
    ]
    synthesis = data.get("synthesis")
    if synthesis:
        lines.extend(
            [
                f"**Strongest Pro** *(by {synthesis['model_id']})*: {synthesis['strongest_pro']}",
                f"**Strongest Con** *(by {synthesis['model_id']})*: {synthesis['strongest_con']}",
                f"**Verdict** *(by {synthesis['model_id']})*: {synthesis['verdict']}",
            ]
        )
    else:
        lines.append("_Synthesis pending._")
    lines.extend(["", "---", "", "## Tree", ""])

    def walk(node: dict[str, Any], prefix: str = "") -> None:
        if node["node_type"] == "ROOT_CLAIM":
            lines.extend(["### Root Claim", f"> {node['claim']}", ""])
        else:
            marker = "▲ Pro" if node["node_type"] == "PRO" else "▼ Con"
            generation = node.get("active_generation") or {}
            model = generation.get("model_id", "pending")
            worker = generation.get("worker_name", generation.get("worker_id", "pending"))
            hashes = "#" * min(6, 4 + node["depth"])
            lines.append(f"{prefix}{hashes} {marker} {node['position'] + 1} - *{model}* (worker: {worker})")
            lines.append(generation.get("argument") or "_Pending._")
            lines.append("")
        for child in node.get("children", []):
            walk(child, prefix + "  ")

    if data["tree"]:
        walk(data["tree"])

    lines.extend(["", "---", "", "## Generation History", ""])
    history_nodes = list(
        db.scalars(
            select(Node)
            .where(Node.debate_id == debate.id)
            .order_by(Node.materialized_path, Node.depth, Node.position, Node.created_at)
        ).all()
    )
    history_count = 0
    for node in history_nodes:
        generations = list(
            db.scalars(
                select(Generation)
                .where(Generation.node_id == node.id)
                .order_by(Generation.created_at.desc(), Generation.id.desc())
            ).all()
        )
        if not generations:
            continue
        history_count += len(generations)
        if node.node_type == "ROOT_CLAIM":
            node_label = "Root Claim"
        else:
            marker = "Pro" if node.node_type == "PRO" else "Con"
            node_label = f"{marker} {node.position + 1}: {node.claim}"
        status_suffix = f" [{node.status}]" if node.status != "complete" else ""
        lines.extend([f"### {node_label}{status_suffix}", ""])
        for generation in generations:
            state = "Active" if generation.is_active else "Archived"
            worker = db.get(Worker, generation.worker_id)
            worker_name = worker.name if worker else generation.worker_id
            created_at = iso(generation.created_at) or "unknown"
            lines.append(
                f"- **{state}** `{generation.id}` - *{generation.model_id}* "
                f"(worker: {worker_name}, role: {generation.role}, created: {created_at})"
            )
            argument = generation.argument or "_No argument text._"
            for argument_line in argument.splitlines() or [argument]:
                lines.append(f"  > {argument_line}")
            lines.append("")
    if history_count == 0:
        lines.append("_No generations recorded._")
    return "\n".join(lines).strip() + "\n"
