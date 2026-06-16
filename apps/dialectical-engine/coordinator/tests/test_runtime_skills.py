from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import entities
from app.services.orchestrator import claim_pending_job, complete_job
from app.services import runtime_skills


def valid_runtime_skill(name: str = "statistical-analysis") -> dict:
    return {
        "kind": "runtime_skill",
        "name": name,
        "version": 1,
        "status": "provisional",
        "description": "Use when the task benefits from statistical reasoning about evidence.",
        "subagent_identity": "You are a careful statistician who preserves uncertainty.",
        "method": ["Check base rates", "Separate measurement from inference"],
        "search_guidance": [
            "Use only official documentation, public primary sources, standards, regulations, filings, or institutional documents relevant to the domain."
        ],
        "constraints": ["Do not run code", "Do not request tools", "Do not use private or non-public data"],
        "source_policy": {
            "allowed_sources": ["official_documentation", "public_primary_sources"],
            "forbidden_sources": ["private_databases", "credential-gated_leaks", "random_web_databases"],
        },
        "quality": {"quality_score": None, "reuse_count": 0, "last_used_at": None},
        "provenance": {
            "created_by_model": "codex-gpt-5.5",
            "created_by_worker_id": "worker-1",
            "created_in_debate_id": "debate-1",
            "created_by_job_id": "job-1",
        },
    }


def test_validate_runtime_skill_accepts_and_normalizes_safe_skill() -> None:
    normalized = runtime_skills.validate_runtime_skill_definition(valid_runtime_skill("Statistical Analysis"))

    assert normalized["kind"] == "runtime_skill"
    assert normalized["name"] == "statistical-analysis"
    assert normalized["status"] == "provisional"
    assert normalized["subagent_identity"].startswith("You are a careful statistician")
    assert normalized["source_policy"]["allowed_sources"] == ["official_documentation", "public_primary_sources"]
    assert normalized["quality"]["reuse_count"] == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_identity", "subagent_identity"),
        ("bad_status", "status"),
        ("code_execution", "code execution"),
        ("private_database", "private"),
        ("random_database", "random"),
    ],
)
def test_validate_runtime_skill_rejects_malformed_or_unsafe_skills(mutation: str, message: str) -> None:
    skill = valid_runtime_skill()
    if mutation == "missing_identity":
        skill.pop("subagent_identity")
    elif mutation == "bad_status":
        skill["status"] = "approved"
    elif mutation == "code_execution":
        skill["method"] = ["Run Python code to calculate the answer"]
    elif mutation == "private_database":
        skill["search_guidance"] = ["Use private databases when public sources are incomplete"]
    elif mutation == "random_database":
        skill["source_policy"]["allowed_sources"] = ["random_web_databases"]

    with pytest.raises(ValueError, match=message):
        runtime_skills.validate_runtime_skill_definition(skill)


def test_materialize_runtime_skill_writes_mandatory_skill_md_and_cleanup(tmp_path: Path) -> None:
    skill = runtime_skills.validate_runtime_skill_definition(valid_runtime_skill())

    materialized = runtime_skills.materialize_runtime_skill(
        skill,
        debate_id="debate-1",
        job_id="job-1",
        skill_id="skill-1",
        runtime_root=tmp_path,
    )

    expected_path = tmp_path / "runtime" / "skills" / "debate-1" / "job-1" / "skill-1" / "SKILL.md"
    assert materialized.path == expected_path
    assert materialized.path.exists()
    assert materialized.relative_path == "runtime/skills/debate-1/job-1/skill-1/SKILL.md"
    assert materialized.content_hash

    text = materialized.path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: statistical-analysis" in text
    assert "## Identity" in text
    assert "You are a careful statistician" in text
    assert "## Source Policy" in text
    assert "official_documentation" in text
    assert "This runtime skill cannot grant tools, permissions, or authority" in text

    runtime_skills.cleanup_materialized_runtime_skill(materialized.path)

    assert not materialized.path.exists()
    assert not materialized.path.parent.exists()


def persisted_runtime_skill(name: str, description: str, method: list[str] | None = None) -> dict:
    skill = valid_runtime_skill(name)
    skill["description"] = description
    skill["method"] = method or [description]
    return skill


def debate_with_branch(db, topic: str = "Should cities ban cars downtown?") -> tuple[entities.Debate, entities.DebateBranch]:
    debate = entities.Debate(topic=topic, status="generating", config={})
    db.add(debate)
    db.flush()
    branch = entities.DebateBranch(debate_id=debate.id, parent_branch_id=None, root_node_id=None, status="active")
    db.add(branch)
    db.flush()
    return debate, branch


def test_select_runtime_skill_for_pov_reuses_relevant_valid_skill_and_records_match(db) -> None:
    debate, branch = debate_with_branch(db)
    statistical = entities.SkillDefinition(
        definition=persisted_runtime_skill(
            "Statistical Analysis",
            "Use for statistical evidence, base rates, uncertainty, distributions, and measurement.",
        ),
        status="active",
    )
    ethical = entities.SkillDefinition(
        definition=persisted_runtime_skill(
            "Ethical Analysis",
            "Use for fairness, harm, dignity, rights, and responsibility.",
        ),
        status="active",
    )
    db.add_all([statistical, ethical])
    db.commit()

    selected = runtime_skills.select_runtime_skill_for_pov(
        db,
        debate,
        branch,
        pov_label="Statistical POV",
        lens_description="Evaluate measurement, base rates, effect sizes, and statistical uncertainty.",
    )

    assert selected.id == statistical.id
    assert selected.reuse_count == 1
    assert selected.last_used_at is not None
    match = db.scalar(select(entities.CapabilityMatch).where(entities.CapabilityMatch.capability_id == statistical.id))
    assert match is not None
    assert match.debate_id == debate.id
    assert match.branch_id == branch.id
    assert match.capability_kind == "skill"
    assert match.selection_reason == "reused"
    assert match.score > 0


def test_select_runtime_skill_for_pov_can_choose_different_skills_for_different_povs(db) -> None:
    debate, branch = debate_with_branch(db)
    scientific = entities.SkillDefinition(
        definition=persisted_runtime_skill(
            "Scientific Method",
            "Use for causal mechanisms, empirical evidence quality, external validity, and scientific uncertainty.",
        ),
        status="active",
    )
    practical = entities.SkillDefinition(
        definition=persisted_runtime_skill(
            "Practical Operations",
            "Use for feasibility, operational complexity, cost, maintainability, rollout risks, and edge cases.",
        ),
        status="active",
    )
    db.add_all([scientific, practical])
    db.commit()

    selected_scientific = runtime_skills.select_runtime_skill_for_pov(
        db,
        debate,
        branch,
        pov_label="Scientific POV",
        lens_description="Evaluate causal mechanisms, empirical evidence quality, uncertainty, and external validity.",
    )
    selected_practical = runtime_skills.select_runtime_skill_for_pov(
        db,
        debate,
        branch,
        pov_label="Practical POV",
        lens_description="Evaluate feasibility, operational complexity, costs, maintainability, and rollout risks.",
    )

    assert selected_scientific.id == scientific.id
    assert selected_practical.id == practical.id


def test_select_runtime_skill_for_pov_skips_rejected_deprecated_and_invalid_skills(db) -> None:
    debate, branch = debate_with_branch(db)
    unsafe = valid_runtime_skill("Unsafe Skill")
    unsafe["method"] = ["Run Python code against private databases"]
    db.add_all(
        [
            entities.SkillDefinition(
                definition=persisted_runtime_skill("Rejected Statistical", "base rates statistical uncertainty"),
                status="rejected",
            ),
            entities.SkillDefinition(
                definition=persisted_runtime_skill("Deprecated Statistical", "base rates statistical uncertainty"),
                status="deprecated",
            ),
            entities.SkillDefinition(definition=unsafe, status="active"),
        ]
    )
    db.commit()

    selected = runtime_skills.select_runtime_skill_for_pov(
        db,
        debate,
        branch,
        pov_label="Statistical POV",
        lens_description="Evaluate base rates and statistical uncertainty.",
    )

    assert selected is None
    assert db.scalars(select(entities.CapabilityMatch).where(entities.CapabilityMatch.debate_id == debate.id)).all() == []


def real_codex_worker(db) -> entities.Worker:
    worker = entities.Worker(
        name="codex-worker",
        token_hash="test-token",
        capabilities=["codex-gpt-5.5"],
        last_seen=entities.now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    return worker


def test_create_debate_with_empty_runtime_skills_queues_skill_create_before_pov_jobs(db) -> None:
    from app.services import dialectical_v2

    real_codex_worker(db)

    debate = dialectical_v2.create_dialectical_debate(db, "Should cities ban cars downtown?", {})

    nodes = db.scalars(select(entities.Node).where(entities.Node.debate_id == debate.id)).all()
    root_nodes = [node for node in nodes if node.node_type == "ROOT_CLAIM"]
    pov_nodes = [node for node in nodes if node.node_type in {node_type for node_type, _label in dialectical_v2.POV_BRANCHES}]
    queued_v2_jobs = db.scalars(
        select(entities.Job)
        .where(entities.Job.debate_id == debate.id, entities.Job.job_type.like("v2_%"))
        .order_by(entities.Job.created_at.asc())
    ).all()

    assert len(root_nodes) == 1
    assert root_nodes[0].status == "complete"
    assert len(pov_nodes) == 4
    assert {node.status for node in pov_nodes} == {"pending"}
    assert [job.job_type for job in queued_v2_jobs] == ["v2_skill_create"]
    assert queued_v2_jobs[0].required_role == "v2_skill_creator"
    assert queued_v2_jobs[0].required_model == "codex-gpt-5.5"
    assert queued_v2_jobs[0].node_id in {debate.root_node_id, None}
    assert db.scalar(select(entities.SkillDefinition)) is None
    assert db.scalars(
        select(entities.Job).where(entities.Job.debate_id == debate.id, entities.Job.job_type == "v2_pov")
    ).all() == []


def test_v2_skill_create_prompt_requests_runtime_skill_schema(db) -> None:
    from app.services import dialectical_v2

    worker = real_codex_worker(db)
    debate, _branch = debate_with_branch(db)
    job = dialectical_v2.queue_v2_job(db, debate, "v2_skill_create", "v2_skill_creator", "codex-gpt-5.5", None)
    job.worker_id = worker.id

    _system, user = dialectical_v2.render_v2_job_prompt(db, job)

    assert '"kind":"runtime_skill"' in user
    assert '"subagent_identity"' in user
    assert '"source_policy"' in user
    assert "official documentation" in user
    assert "Do not run code" in user
    assert "Do not request tools" in user
    assert '"kind":"skill"' not in user


def test_v2_skill_create_completion_validates_persists_and_matches_runtime_skill(db) -> None:
    from app.services import dialectical_v2

    worker = real_codex_worker(db)
    debate = dialectical_v2.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    branch = db.scalar(select(entities.DebateBranch).where(entities.DebateBranch.debate_id == debate.id))
    queued = db.scalar(select(entities.Job).where(entities.Job.debate_id == debate.id, entities.Job.job_type == "v2_skill_create"))
    job = claim_pending_job(db, worker)
    assert job.id == queued.id
    payload = valid_runtime_skill("Created Statistical Skill")
    payload["provenance"] = {
        "created_by_model": "codex-gpt-5.5",
        "created_by_worker_id": worker.id,
        "created_in_debate_id": debate.id,
        "created_by_job_id": job.id,
        "creation_prompt_id": f"prompt-{job.id}",
        "job_id": job.id,
    }

    import asyncio

    asyncio.run(complete_job(db, job, payload, {"latency_ms": 4}))

    saved = db.scalar(select(entities.SkillDefinition).where(entities.SkillDefinition.definition["kind"].as_string() == "runtime_skill"))
    assert saved is not None
    assert saved.status == "provisional"
    assert saved.definition["name"] == "created-statistical-skill"
    match = db.scalar(select(entities.CapabilityMatch).where(entities.CapabilityMatch.capability_id == saved.id))
    assert match is not None
    assert match.selection_reason == "created"
    assert match.branch_id == branch.id
    provenance = db.scalar(select(entities.ProvenanceRecord).where(entities.ProvenanceRecord.artifact_id == saved.id))
    assert provenance is not None
    assert provenance.artifact_kind == "skill"
    assert provenance.job_id == job.id
    queued_pov_jobs = db.scalars(
        select(entities.Job)
        .where(entities.Job.debate_id == debate.id, entities.Job.job_type == "v2_pov")
        .order_by(entities.Job.created_at.asc())
    ).all()
    assert [pov_job.required_role for pov_job in queued_pov_jobs] == [
        "Scientific POV",
        "Statistical POV",
        "Ethical POV",
        "Practical POV",
    ]
    assert {pov_job.node_id for pov_job in queued_pov_jobs} == {
        node.id
        for node in db.scalars(
            select(entities.Node).where(
                entities.Node.debate_id == debate.id,
                entities.Node.node_type.in_([node_type for node_type, _label in dialectical_v2.POV_BRANCHES]),
            )
        )
    }


def test_v2_skill_create_completion_rejects_invalid_runtime_skill(db) -> None:
    from app.services import dialectical_v2

    worker = real_codex_worker(db)
    debate, _branch = debate_with_branch(db)
    queued = dialectical_v2.queue_v2_job(db, debate, "v2_skill_create", "v2_skill_creator", "codex-gpt-5.5", None)
    job = claim_pending_job(db, worker)
    assert job.id == queued.id
    invalid = valid_runtime_skill("Unsafe Skill")
    invalid["method"] = ["Run Python code to fetch private database rows"]

    import asyncio

    with pytest.raises(ValueError, match="code execution"):
        asyncio.run(complete_job(db, job, invalid, {"latency_ms": 4}))


def test_created_runtime_skill_is_injected_into_first_pov_prompt_immediately(db) -> None:
    from app.core.db import settings
    from app.services import dialectical_v2

    worker = real_codex_worker(db)
    debate = dialectical_v2.create_dialectical_debate(db, "Should cities ban cars downtown?", {})

    skill_create_job = claim_pending_job(db, worker)
    assert skill_create_job.job_type == "v2_skill_create"
    payload = valid_runtime_skill("Fresh Runtime Scaffold")
    payload["description"] = "Use for careful framing, provenance discipline, and public-source boundaries."
    payload["subagent_identity"] = "You are a careful specialist who maintains provenance."
    payload["method"] = ["Track assumptions", "Check source fit"]
    payload["provenance"] = {
        "created_by_model": "codex-gpt-5.5",
        "created_by_worker_id": worker.id,
        "created_in_debate_id": debate.id,
        "created_by_job_id": skill_create_job.id,
    }

    import asyncio

    asyncio.run(complete_job(db, skill_create_job, payload, {"latency_ms": 4}))
    saved = db.scalar(select(entities.SkillDefinition).where(entities.SkillDefinition.definition["name"].as_string() == "fresh-runtime-scaffold"))
    assert saved is not None

    for pending_non_pov in db.scalars(
        select(entities.Job).where(
            entities.Job.debate_id == debate.id,
            entities.Job.status == "pending",
            entities.Job.job_type != "v2_pov",
        )
    ).all():
        pending_non_pov.status = "complete"
    db.commit()
    if db.scalar(select(entities.Job).where(entities.Job.debate_id == debate.id, entities.Job.job_type == "v2_pov")) is None:
        first_pov_node = db.scalar(
            select(entities.Node).where(
                entities.Node.debate_id == debate.id,
                entities.Node.node_type == dialectical_v2.POV_BRANCHES[0][0],
            )
        )
        assert first_pov_node is not None
        dialectical_v2.queue_v2_job(db, debate, "v2_pov", dialectical_v2.POV_BRANCHES[0][1], "codex-gpt-5.5", first_pov_node.id)

    pov_job = claim_pending_job(db, worker)
    assert pov_job.job_type == "v2_pov"
    assert pov_job.required_role == "Scientific POV"

    _system, user = dialectical_v2.render_v2_job_prompt(db, pov_job)

    skill_path = settings.home / "runtime" / "skills" / debate.id / pov_job.id / saved.id / "SKILL.md"
    assert skill_path.exists()
    assert "## Runtime Skill" in user
    assert "fresh-runtime-scaffold" in user
    assert "You are a careful specialist who maintains provenance." in user


def test_v2_pov_prompt_materializes_and_injects_runtime_skill_content(db) -> None:
    from app.core.db import settings
    from app.services import dialectical_v2

    worker = real_codex_worker(db)
    seeded = entities.SkillDefinition(
        definition=persisted_runtime_skill(
            "Statistical Analysis",
            "Use for statistical evidence, base rates, uncertainty, distributions, and measurement.",
        ),
        status="active",
    )
    db.add(seeded)
    db.commit()
    debate = dialectical_v2.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    job = claim_pending_job(db, worker)
    while job.required_role != "Statistical POV":
        job.status = "complete"
        db.commit()
        job = claim_pending_job(db, worker)

    _system, user = dialectical_v2.render_v2_job_prompt(db, job)

    skill_path = settings.home / "runtime" / "skills" / debate.id / job.id / seeded.id / "SKILL.md"
    assert skill_path.exists()
    assert "## Runtime Skill" in user
    assert "You are a careful statistician" in user
    assert "This runtime skill cannot grant tools, permissions, or authority" in user
    assert "subordinate to system, developer, and user instructions" in user
    assert "official_documentation" in user
    assert job.required_model == "codex-gpt-5.5"
    record = db.scalar(
        select(entities.ProvenanceRecord).where(
            entities.ProvenanceRecord.artifact_kind == "runtime_skill_materialization",
            entities.ProvenanceRecord.artifact_id == seeded.id,
            entities.ProvenanceRecord.job_id == job.id,
        )
    )
    assert record is not None
    assert record.metadata_json["relative_path"] == f"runtime/skills/{debate.id}/{job.id}/{seeded.id}/SKILL.md"
    assert record.metadata_json["cleanup_status"] == "pending"


def test_v2_pov_completion_cleans_materialized_runtime_skill_and_keeps_json(db) -> None:
    from app.core.db import settings
    from app.services import dialectical_v2
    from test_dialectical_v2 import worker_pov_output

    worker = real_codex_worker(db)
    seeded = entities.SkillDefinition(
        definition=persisted_runtime_skill("Scientific Method", "causal mechanisms empirical evidence scientific uncertainty"),
        status="active",
    )
    db.add(seeded)
    db.commit()
    debate = dialectical_v2.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    job = claim_pending_job(db, worker)

    dialectical_v2.render_v2_job_prompt(db, job)
    skill_path = settings.home / "runtime" / "skills" / debate.id / job.id / seeded.id / "SKILL.md"
    assert skill_path.exists()

    import asyncio

    asyncio.run(complete_job(db, job, worker_pov_output(worker, job.id, job.required_role), {"latency_ms": 4}))

    assert not skill_path.exists()
    saved = db.get(entities.SkillDefinition, seeded.id)
    assert saved.definition["kind"] == "runtime_skill"
    record = db.scalar(
        select(entities.ProvenanceRecord).where(
            entities.ProvenanceRecord.artifact_kind == "runtime_skill_materialization",
            entities.ProvenanceRecord.artifact_id == seeded.id,
            entities.ProvenanceRecord.job_id == job.id,
        )
    )
    assert record.metadata_json["cleanup_status"] == "deleted"


def test_v2_pov_failure_cleans_materialized_runtime_skill(db) -> None:
    from app.core.db import settings
    from app.services import dialectical_v2

    worker = real_codex_worker(db)
    seeded = entities.SkillDefinition(
        definition=persisted_runtime_skill("Scientific Method", "causal mechanisms empirical evidence scientific uncertainty"),
        status="active",
    )
    db.add(seeded)
    db.commit()
    debate = dialectical_v2.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    job = claim_pending_job(db, worker)

    dialectical_v2.render_v2_job_prompt(db, job)
    skill_path = settings.home / "runtime" / "skills" / debate.id / job.id / seeded.id / "SKILL.md"
    assert skill_path.exists()

    import asyncio

    with pytest.raises(ValueError, match="POV output"):
        asyncio.run(complete_job(db, job, {"not": "valid"}, {"latency_ms": 4}))

    assert not skill_path.exists()


def test_public_debate_response_hides_runtime_skill_selection_and_provenance(db) -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import dialectical_v2

    worker = real_codex_worker(db)
    seeded = entities.SkillDefinition(
        definition=persisted_runtime_skill("Scientific Method", "causal mechanisms empirical evidence scientific uncertainty"),
        status="active",
    )
    db.add(seeded)
    db.commit()
    debate = dialectical_v2.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    job = claim_pending_job(db, worker)

    dialectical_v2.render_v2_job_prompt(db, job)
    assert db.scalar(select(entities.CapabilityMatch).where(entities.CapabilityMatch.debate_id == debate.id)) is not None
    assert db.scalar(select(entities.ProvenanceRecord).where(entities.ProvenanceRecord.debate_id == debate.id)) is not None
    db.commit()

    payload = TestClient(app).get(f"/api/debates/{debate.id}").json()
    encoded = str(payload)

    assert payload["selected_skills"] == []
    assert payload["selected_agents"] == []
    assert payload["skills_used"] == []
    assert payload["provenance_records"] == []
    assert "runtime_skill" not in encoded
    assert "Scientific Method" not in encoded
    assert "runtime_skill_materialization" not in encoded


def test_cleanup_stale_runtime_skill_dirs_removes_inactive_jobs_and_preserves_active(tmp_path: Path) -> None:
    stale = tmp_path / "runtime" / "skills" / "debate-1" / "stale-job" / "skill-1" / "SKILL.md"
    active = tmp_path / "runtime" / "skills" / "debate-1" / "active-job" / "skill-2" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    active.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")
    active.write_text("active", encoding="utf-8")

    removed = runtime_skills.cleanup_stale_runtime_skill_dirs(tmp_path, active_job_ids={"active-job"})

    assert removed == [stale.parent]
    assert not stale.parent.exists()
    assert active.exists()
