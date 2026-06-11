from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import entities
from app.main import app
from app.models.entities import Debate, Worker, now_utc
from app.services.orchestrator import claim_pending_job, complete_job
from app.services.events import event_bus
from app.services.serialization import debate_to_dict


USER_HEADERS = {"Authorization": "Bearer user_test_token"}


def v2_models():
    return {
        "AgentCapability": getattr(entities, "AgentCapability"),
        "AgentDefinition": getattr(entities, "AgentDefinition"),
        "AgentOutput": getattr(entities, "AgentOutput"),
        "AgentRun": getattr(entities, "AgentRun"),
        "AnalyzerRun": getattr(entities, "AnalyzerRun"),
        "CapabilityMatch": getattr(entities, "CapabilityMatch"),
        "DebateBranch": getattr(entities, "DebateBranch"),
        "ProvenanceRecord": getattr(entities, "ProvenanceRecord"),
        "SkillCapability": getattr(entities, "SkillCapability"),
        "SkillDefinition": getattr(entities, "SkillDefinition"),
    }


def v2_service():
    from app.services import dialectical_v2

    return dialectical_v2


def persisted_skill_json(debate_id: str) -> dict:
    return {
        "kind": "skill",
        "name": "Urban Mobility Policy Debate Skill",
        "version": 1,
        "status": "active",
        "description": "Structures mobility policy questions into evidence, risk, and implementation tradeoffs.",
        "trigger": {
            "question_types": ["policy", "urban mobility"],
            "domain_tags": ["transport", "policy"],
            "activation_rules": ["Use for city transport policy tradeoffs."],
        },
        "workflow": {
            "context_to_inspect": [
                "question",
                "classification",
                "statistical_analyzer_output",
                "scientific_analyzer_output",
                "psychological_analyzer_output",
            ],
            "steps": [
                "Identify required perspectives",
                "Search for matching Agents",
                "Create missing Agents",
                "Invoke Agents",
                "Enforce 5 pros and 5 cons per Agent",
            ],
        },
        "constraints": {
            "must_use_default_analyzers": True,
            "must_preserve_provenance": True,
            "must_require_exactly_5_pros_5_cons": True,
        },
        "output_contract": {
            "format": "structured_json",
            "sections": ["selected_agents", "agent_outputs", "skill_findings"],
        },
        "quality": {"created_by": "system", "creation_reason": "Seeded reusable policy skill.", "reuse_count": 0},
        "provenance": {
            "created_in_debate_id": debate_id,
            "created_by_model": "codex-gpt-5.5",
            "created_by_worker_id": "worker-real-1",
            "creation_prompt_id": "prompt-skill-1",
            "job_id": "job-skill-1",
        },
    }


def persisted_agent_json(debate_id: str) -> dict:
    return {
        "kind": "agent",
        "name": "Scientific Skeptic",
        "version": 1,
        "status": "active",
        "description": "Evaluates claims through empirical evidence and methodological rigor.",
        "domain_tags": ["science", "evidence", "transport"],
        "role": "Debate participant",
        "purpose": "Challenge weak empirical claims and surface evidence quality.",
        "instructions": {
            "operating_principles": ["Prefer measured evidence over slogans."],
            "reasoning_style": "methodical, evidence-weighted, skeptical",
            "boundaries": ["Do not invent statistics."],
            "allowed_tools": ["default_analyzers"],
            "allowed_skills": ["Urban Mobility Policy Debate Skill"],
        },
        "input_contract": {"required": ["question", "analyzer_outputs"], "optional": ["skill_context"]},
        "output_contract": {"pros_count": 5, "cons_count": 5, "requires_summary": True, "requires_confidence": True},
        "quality": {"created_by": "system", "creation_reason": "Seeded reusable scientific agent.", "reuse_count": 0},
        "provenance": {
            "created_in_debate_id": debate_id,
            "created_by_model": "codex-gpt-5.5",
            "created_by_worker_id": "worker-real-1",
            "creation_prompt_id": "prompt-agent-1",
            "job_id": "job-agent-1",
        },
    }


def real_codex_worker(db, *, name: str = "codex-worker") -> Worker:
    worker = Worker(
        name=name,
        token_hash="test-token",
        capabilities=["codex-gpt-5.5"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    return worker


def mock_worker(db) -> Worker:
    worker = Worker(
        name="mock-worker",
        token_hash="test-token",
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    return worker


def claim_for_worker(db, worker: Worker):
    job = claim_pending_job(db, worker)
    assert job is not None
    return job


def worker_agent_output(worker: Worker, job_id: str) -> dict:
    return {
        "pros": [f"Substantive pro argument {index} about downtown car restrictions." for index in range(1, 6)],
        "cons": [f"Substantive con argument {index} about downtown car restrictions." for index in range(1, 6)],
        "summary": "The policy has measurable upside but depends on evidence, exemptions, and implementation quality.",
        "confidence": 0.72,
        "provenance": {
            "model_id": "codex-gpt-5.5",
            "worker_id": worker.id,
            "prompt_id": f"prompt-{job_id}",
            "job_id": job_id,
        },
    }


def worker_synthesis(worker: Worker, job_id: str) -> dict:
    return {
        "strongest_pro": "Reduced downtown car traffic can improve safety, air quality, and street reliability.",
        "strongest_con": "Restrictions can burden access, deliveries, and people with limited mobility options.",
        "verdict": "Treat the proposal as a design-sensitive tradeoff rather than a direct yes/no answer.",
        "provenance": {
            "model_id": "codex-gpt-5.5",
            "worker_id": worker.id,
            "prompt_id": f"prompt-{job_id}",
            "job_id": job_id,
        },
    }


def worker_plan() -> dict:
    return {
        "agents": [
            {
                "name": "Scientific Skeptic",
                "description": "Evaluates claims through empirical evidence and methodological rigor.",
                "lens": "scientific evidence",
                "domain": "urban mobility",
                "default_prompt": "Challenge weak empirical claims and surface evidence quality.",
                "skill_names": ["Evidence Weighing"],
            },
            {
                "name": "Access Advocate",
                "description": "Evaluates access, equity, disability, and delivery tradeoffs.",
                "lens": "access and equity",
                "domain": "urban mobility",
                "default_prompt": "Identify who benefits, who loses access, and what mitigations matter.",
                "skill_names": ["Equity Impact Framing"],
            },
        ],
        "skills": [
            {
                "name": "Evidence Weighing",
                "type": "prompt",
                "description": "Separate measured evidence from assumptions.",
                "body": "State evidence quality, uncertainty, and missing causal links before arguing.",
                "tags": ["transport", "evidence", "policy"],
            },
            {
                "name": "Equity Impact Framing",
                "type": "prompt",
                "description": "Frame access and equity tradeoffs.",
                "body": "Identify affected groups, burdens, mitigations, and implementation risks.",
                "tags": ["transport", "equity", "policy"],
            },
        ],
    }


def worker_agent_run_output(worker: Worker, job_id: str) -> dict:
    payload = worker_agent_output(worker, job_id)
    payload["contribution_summary"] = "This run adds a distinct lens to the final synthesis."
    return payload


def worker_pov_output(worker: Worker, job_id: str, pov: str) -> dict:
    prefix = "scientific" if pov == "Scientific POV" else "statistical"
    return {
        "title": f"{pov} assessment",
        "content": f"A concise {prefix} assessment of the question based on the strongest available reasoning.",
        "strongest_pro": {
            "title": f"{pov} strongest pro",
            "content": f"The strongest {prefix} pro relies on the clearest relevant evidence.",
            "pro": {
                "title": f"{pov} pro support",
                "content": f"Supporting detail that strengthens the {prefix} pro without padding.",
            },
            "con": {
                "title": f"{pov} pro limitation",
                "content": f"Counter-detail that limits the {prefix} pro and identifies uncertainty.",
            },
        },
        "strongest_con": {
            "title": f"{pov} strongest con",
            "content": f"The strongest {prefix} con identifies the most important risk or weakness.",
            "pro": {
                "title": f"{pov} con support",
                "content": f"Supporting detail that strengthens the {prefix} con without padding.",
            },
            "con": {
                "title": f"{pov} con limitation",
                "content": f"Counter-detail that limits the {prefix} con and identifies uncertainty.",
            },
        },
        "provenance": {
            "model_id": "codex-gpt-5.5",
            "worker_id": worker.id,
            "prompt_id": f"prompt-{job_id}",
            "job_id": job_id,
        },
    }


def worker_non_adjudicating_synthesis(worker: Worker, job_id: str) -> dict:
    return {
        "title": "Synthesis",
        "content": "Both perspectives agree evidence quality matters, disagree on what uncertainty implies, and leave gaps for local baseline data.",
        "tensions": ["Measured effects may not transfer cleanly to every setting."],
        "agreements": ["Both branches need transparent assumptions and scoped evidence."],
        "evidence_gaps": ["Baseline rates, population exposure, and implementation details remain under-specified."],
        "key_takeaways": ["Treat the question as evidence-sensitive rather than settled."],
        "provenance": {
            "model_id": "codex-gpt-5.5",
            "worker_id": worker.id,
            "prompt_id": f"prompt-{job_id}",
            "job_id": job_id,
        },
    }


def complete_worker_v2_plan_pipeline(db, debate: Debate, worker: Worker) -> None:
    for _ in range(2):
        job = claim_for_worker(db, worker)
        assert job.job_type == "v2_pov"
        asyncio.run(complete_job(db, job, worker_pov_output(worker, job.id, job.required_role), {"latency_ms": 12}))
    synthesis = claim_for_worker(db, worker)
    assert synthesis.job_type == "v2_synthesize"
    asyncio.run(complete_job(db, synthesis, worker_non_adjudicating_synthesis(worker, synthesis.id), {"latency_ms": 13}))


def complete_worker_v2_pipeline(db, debate: Debate, worker: Worker) -> None:
    complete_worker_v2_plan_pipeline(db, debate, worker)


def test_create_debate_queues_planner_before_agent_execution(db) -> None:
    service = v2_service()
    real_codex_worker(db)

    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {"max_depth": 1})
    jobs = db.scalars(select(entities.Job).where(entities.Job.debate_id == debate.id).order_by(entities.Job.created_at)).all()

    assert [job.job_type for job in jobs if job.job_type.startswith("v2_")] == ["v2_pov", "v2_pov"]
    assert {job.required_role for job in jobs if job.job_type == "v2_pov"} == {"Scientific POV", "Statistical POV"}
    assert {job.required_model for job in jobs if job.job_type == "v2_pov"} == {"codex-gpt-5.5"}
    assert all(job.required_model != "mock-local" for job in jobs)
    assert db.scalar(select(entities.AgentRun).where(entities.AgentRun.debate_id == debate.id)) is None


def test_create_debate_creates_visible_scientific_and_statistical_pov_branches(db) -> None:
    service = v2_service()
    real_codex_worker(db)

    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {"max_depth": 2})
    detail = debate_to_dict(db, debate)

    assert detail["tree"]["node_type"] == "ROOT_CLAIM"
    assert [child["node_type"] for child in detail["tree"]["children"]] == ["SCIENTIFIC_POV", "STATISTICAL_POV"]
    assert [child["claim"] for child in detail["tree"]["children"]] == ["Scientific POV", "Statistical POV"]
    assert [child["status"] for child in detail["tree"]["children"]] == ["pending", "pending"]
    assert detail["models"] == []


def test_claimed_v2_planner_does_not_render_as_root_node_generation(db) -> None:
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should mosquitoes be exterminated?", {})
    job = claim_for_worker(db, worker)

    assert job.job_type == "v2_pov"
    assert job.node_id != debate.root_node_id
    job.stream_buffer = '{"error":"missing_requested_shape"}'
    detail = debate_to_dict(db, debate)

    assert detail["tree"]["status"] == "complete"
    assert detail["tree"]["active_generation"] is None
    streaming_branch = next(child for child in detail["tree"]["children"] if child["id"] == job.node_id)
    assert streaming_branch["status"] == "generating"
    assert streaming_branch["active_generation"]["model_id"] == "codex-gpt-5.5"


def test_planner_completion_persists_definitions_and_real_agent_runs_before_queueing_agents(db) -> None:
    models = v2_models()
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    job = claim_for_worker(db, worker)

    asyncio.run(complete_job(db, job, worker_pov_output(worker, job.id, job.required_role), {"latency_ms": 9}))

    assert db.scalar(select(models["SkillDefinition"])) is None
    assert db.scalar(select(models["AgentDefinition"])) is None
    runs = db.scalars(select(models["AgentRun"]).where(models["AgentRun"].debate_id == debate.id)).all()
    assert runs == []
    agent_jobs = db.scalars(
        select(entities.Job).where(entities.Job.debate_id == debate.id, entities.Job.job_type == "v2_agent_run")
    ).all()
    assert agent_jobs == []


def test_pov_completion_materializes_title_content_and_nested_pro_con_cards(db) -> None:
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})

    first_job = claim_for_worker(db, worker)
    assert first_job.job_type == "v2_pov"
    assert first_job.required_role in {"Scientific POV", "Statistical POV"}
    asyncio.run(complete_job(db, first_job, worker_pov_output(worker, first_job.id, first_job.required_role), {"latency_ms": 12}))

    detail = debate_to_dict(db, debate)
    completed_branch = next(child for child in detail["tree"]["children"] if child["claim"] == first_job.required_role)

    assert completed_branch["status"] == "complete"
    assert completed_branch["active_generation"]["model_id"] == "codex-gpt-5.5"
    assert completed_branch["active_generation"]["role"] == first_job.required_role
    assert completed_branch["active_generation"]["argument"].startswith(f"{first_job.required_role} assessment")
    assert [child["node_type"] for child in completed_branch["children"]] == ["PRO", "CON"]
    assert [child["claim"] for child in completed_branch["children"]] == [
        f"{first_job.required_role} strongest pro",
        f"{first_job.required_role} strongest con",
    ]
    for stance in completed_branch["children"]:
        assert stance["status"] == "complete"
        assert stance["active_generation"]["model_id"] == "codex-gpt-5.5"
        assert [child["node_type"] for child in stance["children"]] == ["PRO", "CON"]
        assert all(child["status"] == "complete" for child in stance["children"])


def test_synthesis_queues_only_after_both_pov_branches_complete(db) -> None:
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})

    first_job = claim_for_worker(db, worker)
    asyncio.run(complete_job(db, first_job, worker_pov_output(worker, first_job.id, first_job.required_role), {"latency_ms": 12}))
    assert db.scalar(select(entities.Job).where(entities.Job.debate_id == debate.id, entities.Job.job_type == "v2_synthesize")) is None

    second_job = claim_for_worker(db, worker)
    assert second_job.job_type == "v2_pov"
    asyncio.run(complete_job(db, second_job, worker_pov_output(worker, second_job.id, second_job.required_role), {"latency_ms": 12}))

    synthesis_job = db.scalar(select(entities.Job).where(entities.Job.debate_id == debate.id, entities.Job.job_type == "v2_synthesize"))
    assert synthesis_job is not None
    assert synthesis_job.required_model == "codex-gpt-5.5"


def test_non_adjudicating_synthesis_completes_without_declaring_winner(db) -> None:
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})

    for _ in range(2):
        job = claim_for_worker(db, worker)
        assert job.job_type == "v2_pov"
        asyncio.run(complete_job(db, job, worker_pov_output(worker, job.id, job.required_role), {"latency_ms": 12}))

    synthesis_job = claim_for_worker(db, worker)
    assert synthesis_job.job_type == "v2_synthesize"
    asyncio.run(
        complete_job(
            db,
            synthesis_job,
            worker_non_adjudicating_synthesis(worker, synthesis_job.id),
            {"latency_ms": 13},
        )
    )

    detail = TestClient(app).get(f"/api/debates/{debate.id}").json()

    assert detail["status"] == "complete"
    assert detail["synthesis"]["strongest_pro"] == "Synthesis"
    assert "Both perspectives agree" in detail["synthesis"]["verdict"]
    assert "winner" not in detail["synthesis"]["verdict"].lower()
    assert detail["synthesis"]["provenance"]["tensions"]
    assert detail["synthesis"]["model_id"] == "codex-gpt-5.5"


def test_planner_rejects_invalid_json_and_executable_skills(db) -> None:
    service = v2_service()
    valid = worker_plan()
    assert service.validate_planner_contract(valid)["agents"][0]["name"] == "Scientific Skeptic"

    with pytest.raises(ValueError, match="Planner output"):
        service.validate_planner_contract({"agents": [], "skills": []})

    invalid_skill_type = json.loads(json.dumps(valid))
    invalid_skill_type["skills"][0]["type"] = "executable"
    with pytest.raises(ValueError, match="Only prompt skills"):
        service.validate_planner_contract(invalid_skill_type)

    missing_body = json.loads(json.dumps(valid))
    missing_body["skills"][0]["body"] = ""
    with pytest.raises(ValueError, match="body"):
        service.validate_planner_contract(missing_body)


def test_synthesis_waits_until_all_pov_branches_complete(db) -> None:
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})

    first_pov_job = claim_for_worker(db, worker)
    assert first_pov_job.job_type == "v2_pov"
    asyncio.run(complete_job(db, first_pov_job, worker_pov_output(worker, first_pov_job.id, first_pov_job.required_role), {"latency_ms": 12}))

    queued_synthesis = db.scalar(select(entities.Job).where(entities.Job.debate_id == debate.id, entities.Job.job_type == "v2_synthesize"))
    assert queued_synthesis is None
    incomplete_pov = db.scalars(
        select(entities.Node).where(
            entities.Node.debate_id == debate.id,
            entities.Node.node_type.in_(["SCIENTIFIC_POV", "STATISTICAL_POV"]),
            entities.Node.status != "complete",
        )
    ).all()
    assert len(incomplete_pov) == 1


def test_pov_pipeline_completes_from_real_jobs_and_returns_breakdown(db) -> None:
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {"max_depth": 1})

    complete_worker_v2_plan_pipeline(db, debate, worker)
    detail = TestClient(app).get(f"/api/debates/{debate.id}").json()

    assert detail["status"] == "complete"
    assert [child["claim"] for child in detail["tree"]["children"]] == ["Scientific POV", "Statistical POV"]
    assert all(child["status"] == "complete" for child in detail["tree"]["children"])
    assert detail["selected_agents"] == []
    assert detail["selected_skills"] == []
    assert detail["agent_runs"] == []
    assert detail["synthesis"]["provenance"]["model_id"] == "codex-gpt-5.5"


def test_agent_and_skill_json_contracts_persist_and_retrieve(db) -> None:
    models = v2_models()
    debate = Debate(topic="Should cities ban cars downtown?", status="generating", config={})
    db.add(debate)
    db.flush()
    skill = models["SkillCapability"](definition=persisted_skill_json(debate.id), status="active", quality_score=0.91)
    agent = models["AgentCapability"](definition=persisted_agent_json(debate.id), status="active", quality_score=0.94)
    db.add_all([skill, agent])
    db.commit()

    saved_skill = db.get(models["SkillCapability"], skill.id)
    saved_agent = db.get(models["AgentCapability"], agent.id)

    assert saved_skill.definition["trigger"]["activation_rules"] == ["Use for city transport policy tradeoffs."]
    assert saved_skill.definition["workflow"]["steps"][3] == "Invoke Agents"
    assert saved_skill.definition["constraints"]["must_preserve_provenance"] is True
    assert saved_agent.definition["role"] == "Debate participant"
    assert saved_agent.definition["purpose"].startswith("Challenge weak empirical claims")
    assert saved_agent.definition["instructions"]["reasoning_style"] == "methodical, evidence-weighted, skeptical"
    assert saved_agent.definition["instructions"]["allowed_tools"] == ["default_analyzers"]
    assert saved_agent.definition["output_contract"]["pros_count"] == 5
    assert saved_agent.definition["provenance"]["created_in_debate_id"] == debate.id


def test_empty_database_question_creates_full_pipeline_without_direct_answer(db) -> None:
    models = v2_models()
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {"max_depth": 1})
    complete_worker_v2_pipeline(db, debate, worker)
    detail = TestClient(app).get(f"/api/debates/{debate.id}").json()

    assert detail["topic"] == "Should cities ban cars downtown?"
    assert detail["direct_answer"] is None
    assert detail["status"] == "complete"
    assert detail["branch_lineage"][0]["parent_branch_id"] is None
    assert detail["analyzer_runs"] == []
    assert detail["selected_skills"] == []
    assert detail["selected_agents"] == []
    assert detail["agent_outputs"] == []
    assert detail["synthesis"]["upstream_agent_output_ids"] == []
    assert detail["synthesis"]["analyzer_findings"] == {}
    assert detail["synthesis"]["provenance"]["model_id"] == "codex-gpt-5.5"
    assert detail["synthesis"]["provenance"]["worker_id"] == worker.id
    assert {child["node_type"] for child in detail["tree"]["children"]} == {"SCIENTIFIC_POV", "STATISTICAL_POV"}

    db.expire_all()
    assert db.scalar(select(models["DebateBranch"]).where(models["DebateBranch"].debate_id == debate.id)) is not None
    assert db.scalars(select(models["AnalyzerRun"]).where(models["AnalyzerRun"].debate_id == debate.id)).all() == []
    assert db.scalar(select(models["CapabilityMatch"]).where(models["CapabilityMatch"].debate_id == debate.id)) is None
    assert db.scalar(select(models["AgentOutput"]).where(models["AgentOutput"].debate_id == debate.id)) is None
    assert db.scalar(select(models["ProvenanceRecord"]).where(models["ProvenanceRecord"].debate_id == debate.id)) is not None


def test_second_similar_question_does_not_reuse_local_skill_or_agent(db) -> None:
    models = v2_models()
    service = v2_service()
    worker = real_codex_worker(db)
    first = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    complete_worker_v2_pipeline(db, first, worker)
    created_skill = db.scalar(select(models["SkillCapability"]))
    created_agent = db.scalar(select(models["AgentCapability"]))
    assert created_skill is None
    assert created_agent is None

    second = service.create_dialectical_debate(db, "Should a city restrict downtown car traffic?", {})
    complete_worker_v2_pipeline(db, second, worker)
    db.expire_all()

    assert first.id != second.id
    assert db.scalars(select(models["CapabilityMatch"]).where(models["CapabilityMatch"].debate_id == second.id)).all() == []


def test_low_quality_or_rejected_capabilities_are_not_selected(db) -> None:
    models = v2_models()
    service = v2_service()
    debate = Debate(topic="Should cities ban cars downtown?", status="draft", config={})
    db.add(debate)
    db.flush()
    rejected_skill = models["SkillCapability"](
        definition=persisted_skill_json(debate.id),
        status="rejected",
        quality_score=0.99,
    )
    poor_agent = models["AgentCapability"](
        definition=persisted_agent_json(debate.id),
        status="active",
        quality_score=0.1,
    )
    db.add_all([rejected_skill, poor_agent])
    db.commit()
    real_codex_worker(db)

    created = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    complete_worker_v2_pipeline(db, created, db.scalar(select(Worker).where(Worker.name == "codex-worker")))
    matches = db.scalars(select(models["CapabilityMatch"]).where(models["CapabilityMatch"].debate_id == created.id)).all()

    assert matches == []


def test_deterministic_capabilities_are_not_reused_for_product_v2(db) -> None:
    models = v2_models()
    service = v2_service()
    debate = Debate(topic="Should cities ban cars downtown?", status="draft", config={})
    db.add(debate)
    db.flush()
    deterministic_skill = persisted_skill_json(debate.id)
    deterministic_skill["provenance"] = {
        "created_in_debate_id": debate.id,
        "created_by_model": "coordinator-deterministic-v2",
        "created_by_worker_id": "coordinator",
        "creation_prompt_id": "old-skill",
    }
    deterministic_agent = persisted_agent_json(debate.id)
    deterministic_agent["provenance"] = {
        "created_in_debate_id": debate.id,
        "created_by_model": "coordinator-deterministic-v2",
        "created_by_worker_id": "coordinator",
        "creation_prompt_id": "old-agent",
    }
    old_skill = models["SkillCapability"](definition=deterministic_skill, status="active", quality_score=0.99)
    old_agent = models["AgentCapability"](definition=deterministic_agent, status="active", quality_score=0.99)
    db.add_all([old_skill, old_agent])
    db.commit()
    real_codex_worker(db)

    created = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    jobs = db.scalars(select(entities.Job).where(entities.Job.debate_id == created.id)).all()

    assert [job.job_type for job in jobs if job.job_type.startswith("v2_")] == ["v2_pov", "v2_pov"]
    assert not db.scalars(
        select(models["CapabilityMatch"]).where(
            models["CapabilityMatch"].debate_id == created.id,
            models["CapabilityMatch"].capability_id.in_([old_skill.id, old_agent.id]),
        )
    ).all()


def test_agent_output_contract_requires_exactly_five_pros_cons_and_provenance(db) -> None:
    service = v2_service()
    valid = {
        "pros": [f"Substantive pro argument {index}" for index in range(1, 6)],
        "cons": [f"Substantive con argument {index}" for index in range(1, 6)],
        "summary": "The tradeoff depends on implementation details.",
        "confidence": 0.72,
        "provenance": {
            "model_id": "codex-gpt-5.5",
            "worker_id": "worker-real-1",
            "prompt_id": "prompt-1",
            "job_id": "job-1",
        },
    }

    assert service.validate_agent_output_contract(valid)["pros"] == valid["pros"]

    for mutation in ("short_pros", "long_cons", "missing_provenance"):
        invalid = json.loads(json.dumps(valid))
        if mutation == "short_pros":
            invalid["pros"] = invalid["pros"][:4]
        elif mutation == "long_cons":
            invalid["cons"].append("A sixth con should fail.")
        else:
            invalid.pop("provenance")
        with pytest.raises(ValueError):
            service.validate_agent_output_contract(invalid)


def test_sse_replays_v2_pipeline_events_after_debate_creation(db) -> None:
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    complete_worker_v2_pipeline(db, debate, worker)
    stream = event_bus.subscribe(debate.id, replay_history=True)

    async def collect_events() -> list[str]:
        try:
            events = []
            while True:
                try:
                    events.append(await asyncio.wait_for(stream.__anext__(), timeout=0.1))
                except TimeoutError:
                    return events
            return events
        finally:
            await stream.aclose()

    names = [event.split("\n", 1)[0].replace("event: ", "") for event in asyncio.run(collect_events())]

    assert "v2_pov_queued" in names
    assert "pov_completed" in names
    assert "synthesis_completed" in names


def test_post_debate_runs_v2_pipeline_and_detail_api_returns_contract(db) -> None:
    real_codex_worker(db)
    client = TestClient(app)

    response = client.post(
        "/api/debates",
        headers=USER_HEADERS,
        json={"topic": "Should cities ban cars downtown?", "config": {"max_depth": 1}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"].get("mode") != "single_shot"
    assert payload["status"] == "generating"
    assert payload["analyzer_runs"] == []
    assert payload["selected_skills"] == []
    assert payload["selected_agents"] == []
    assert payload["agent_outputs"] == []
    assert payload["branch_lineage"][0]["debate_id"] == payload["id"]
    assert [child["claim"] for child in payload["tree"]["children"]] == ["Scientific POV", "Statistical POV"]
    jobs = db.scalars(select(entities.Job).where(entities.Job.debate_id == payload["id"])).all()
    assert [job.job_type for job in jobs if job.job_type.startswith("v2_")] == ["v2_pov", "v2_pov"]


def test_v2_rejects_mock_only_workers(db) -> None:
    service = v2_service()
    mock_worker(db)

    with pytest.raises(RuntimeError, match="No real Codex worker online"):
        service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})


def test_v2_requires_real_codex_capable_worker_even_if_deterministic_worker_exists(db) -> None:
    service = v2_service()
    worker = Worker(
        name="coordinator-v2",
        token_hash="internal",
        capabilities=["coordinator-deterministic-v2"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()

    with pytest.raises(RuntimeError, match="No real Codex worker online"):
        service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})


def test_v2_creates_worker_jobs_for_pov_branches_and_synthesis(db) -> None:
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})

    first_jobs = db.scalars(select(entities.Job).where(entities.Job.debate_id == debate.id, entities.Job.job_type == "v2_pov")).all()
    assert len(first_jobs) == 2
    assert {job.required_model for job in first_jobs} == {"codex-gpt-5.5"}
    complete_worker_v2_pipeline(db, debate, worker)

    job_types = [
        job.job_type
        for job in db.scalars(select(entities.Job).where(entities.Job.debate_id == debate.id).order_by(entities.Job.created_at)).all()
    ]
    assert job_types.count("v2_pov") == 2
    assert "v2_agent_run" not in job_types
    assert "v2_synthesize" in job_types


def test_v2_pov_prompt_rejects_status_wrapper_and_includes_schema(db) -> None:
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    job = claim_for_worker(db, worker)

    system, user = service.render_v2_job_prompt(db, job)

    assert "strict JSON object" in system
    assert "Do not include markdown or status wrappers" in system
    assert '"strongest_pro"' in user
    assert '"strongest_con"' in user
    assert '"title"' in user
    assert job.required_role in user


def test_v2_persists_pov_tree_and_synthesis_from_worker_completed_json(db) -> None:
    models = v2_models()
    service = v2_service()
    worker = real_codex_worker(db)
    debate = service.create_dialectical_debate(db, "Should cities ban cars downtown?", {})
    complete_worker_v2_pipeline(db, debate, worker)

    skill = db.scalar(select(models["SkillCapability"]))
    agent = db.scalar(select(models["AgentCapability"]))
    output = db.scalar(select(models["AgentOutput"]).where(models["AgentOutput"].debate_id == debate.id))
    provenance_records = db.scalars(select(models["ProvenanceRecord"]).where(models["ProvenanceRecord"].debate_id == debate.id)).all()

    assert skill is None
    assert agent is None
    assert output is None
    detail = debate_to_dict(db, db.get(Debate, debate.id))
    assert detail["models"] == ["codex-gpt-5.5"]
    assert all(child["active_generation"]["model_id"] == "codex-gpt-5.5" for child in detail["tree"]["children"])
    assert {record.artifact_kind for record in provenance_records} >= {"pov_branch", "synthesis"}


def test_post_debate_returns_clear_error_when_no_real_codex_worker_online(db) -> None:
    mock_worker(db)
    client = TestClient(app)

    response = client.post(
        "/api/debates",
        headers=USER_HEADERS,
        json={"topic": "Should cities ban cars downtown?", "config": {"max_depth": 1}},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "No real Codex worker online for Dialectical V2 artifact generation"


def test_new_page_starts_orchestration_mode_not_single_shot() -> None:
    source = Path(__file__).resolve().parents[2] / "web" / "app" / "new" / "page.tsx"
    text = source.read_text(encoding="utf-8")

    assert '{ mode: "single_shot" }' not in text
    assert "Pro/Con debate tree" in text
