from __future__ import annotations

import json

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.auth import hash_token
from app.core.db import init_db
from app.models.entities import Debate, Generation, Node, Worker, now_utc


def test_sqlite_pragmas_enable_wal_foreign_keys_and_busy_timeout(db) -> None:
    journal_mode = str(db.execute(text("PRAGMA journal_mode")).scalar_one()).lower()
    foreign_keys = int(db.execute(text("PRAGMA foreign_keys")).scalar_one())
    busy_timeout = int(db.execute(text("PRAGMA busy_timeout")).scalar_one())

    assert journal_mode == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 5000


def test_only_one_active_generation_per_node_is_enforced(db) -> None:
    indexes = {index["name"] for index in inspect(db.bind).get_indexes("generations")}
    assert "ux_generations_active_per_node" in indexes

    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    debate = Debate(topic="Should cities ban cars?", status="complete", config={"max_depth": 1})
    db.add_all([worker, debate])
    db.flush()
    node = Node(
        debate_id=debate.id,
        node_type="PRO",
        depth=1,
        position=0,
        claim="Cleaner air.",
        status="complete",
        materialized_path="/0/0",
    )
    db.add(node)
    db.flush()
    db.add(
        Generation(
            node_id=node.id,
            model_id="mock-local",
            role="proposer",
            argument="Cleaner air improves public health.",
            prompt_version="v1",
            prompt_rendered="prompt",
            latency_ms=10,
            is_active=True,
            worker_id=worker.id,
        )
    )
    db.add(
        Generation(
            node_id=node.id,
            model_id="codex-gpt-5.5",
            role="proposer",
            argument="Archived prior view.",
            prompt_version="v1",
            prompt_rendered="prompt",
            latency_ms=12,
            is_active=False,
            worker_id=worker.id,
        )
    )
    db.flush()
    db.add(
        Generation(
            node_id=node.id,
            model_id="gemini-2.5-flash",
            role="proposer",
            argument="Second active view.",
            prompt_version="v1",
            prompt_rendered="prompt",
            latency_ms=14,
            is_active=True,
            worker_id=worker.id,
        )
    )

    with pytest.raises(IntegrityError):
        db.flush()


def test_init_db_backfills_active_generation_index_for_existing_tables(db) -> None:
    db.execute(text("DROP INDEX ux_generations_active_per_node"))
    db.commit()
    assert "ux_generations_active_per_node" not in {
        index["name"] for index in inspect(db.bind).get_indexes("generations")
    }

    init_db()

    assert "ux_generations_active_per_node" in {
        index["name"] for index in inspect(db.bind).get_indexes("generations")
    }


def test_init_db_backfills_v2_synthesis_columns_for_existing_tables(db) -> None:
    db.execute(text("DROP TABLE syntheses"))
    db.execute(
        text(
            """
            CREATE TABLE syntheses (
                id VARCHAR(36) PRIMARY KEY,
                debate_id VARCHAR(36) NOT NULL,
                strongest_pro TEXT NOT NULL,
                strongest_con TEXT NOT NULL,
                verdict TEXT NOT NULL,
                model_id VARCHAR(120) NOT NULL,
                worker_id VARCHAR(36) NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(debate_id) REFERENCES debates (id),
                FOREIGN KEY(worker_id) REFERENCES workers (id)
            )
            """
        )
    )
    db.commit()

    init_db()

    columns = {column["name"] for column in inspect(db.bind).get_columns("syntheses")}
    assert {"upstream_agent_output_ids", "analyzer_findings", "provenance"} <= columns


def test_init_db_backfills_v2_capability_columns_for_existing_tables(db) -> None:
    db.execute(text("DROP TABLE skills"))
    db.execute(
        text(
            """
            CREATE TABLE skills (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(120)
            )
            """
        )
    )
    db.commit()

    init_db()

    columns = {column["name"] for column in inspect(db.bind).get_columns("skills")}
    assert {"definition", "status", "quality_score", "reuse_count", "last_used_at", "created_at"} <= columns


def test_init_db_rebuilds_legacy_capability_tables_before_v2_debate_creation(db) -> None:
    legacy_skill_definition = {
        "kind": "skill",
        "name": "Urban Mobility Policy Debate Skill",
        "trigger": {"domain_tags": ["urban", "transport", "policy"]},
        "workflow": {"steps": ["Inspect city mobility tradeoffs"]},
    }
    legacy_agent_definition = {
        "kind": "agent",
        "name": "Urban Evidence Agent",
        "domain_tags": ["urban", "transport", "policy"],
        "role": "Debate participant",
        "purpose": "Evaluate transport policy evidence.",
    }
    for table_name in ("agent_outputs", "capability_matches", "perspective_outputs", "agents", "skills"):
        db.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
    db.execute(
        text(
            """
            CREATE TABLE skills (
                id VARCHAR(36) PRIMARY KEY,
                key VARCHAR(120) NOT NULL,
                name VARCHAR(120) NOT NULL,
                family VARCHAR(80) NOT NULL,
                slot_type VARCHAR(80) NOT NULL,
                skill_json TEXT NOT NULL,
                usage_count INTEGER NOT NULL,
                status VARCHAR(24),
                last_used_at DATETIME,
                created_at DATETIME
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE TABLE perspective_outputs (
                id VARCHAR(36) PRIMARY KEY,
                skill_id VARCHAR(36) NOT NULL,
                output_json JSON NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(skill_id) REFERENCES skills (id)
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE TABLE agents (
                id VARCHAR(36) PRIMARY KEY,
                key VARCHAR(120) NOT NULL,
                name VARCHAR(120) NOT NULL,
                family VARCHAR(80) NOT NULL,
                slot_type VARCHAR(80) NOT NULL,
                agent_json TEXT NOT NULL,
                usage_count INTEGER NOT NULL,
                status VARCHAR(24),
                last_used_at DATETIME,
                created_at DATETIME
            )
            """
        )
    )
    db.execute(
        text(
            """
            INSERT INTO skills (
                id, key, name, family, slot_type, skill_json, usage_count, status, last_used_at, created_at
            )
            VALUES (
                'legacy-skill-1',
                'urban_mobility_policy',
                'Urban Mobility Policy Debate Skill',
                'policy',
                'debate',
                :definition,
                7,
                'active',
                '2026-06-09 10:00:00',
                '2026-06-08 10:00:00'
            )
            """
        ),
        {"definition": json.dumps(legacy_skill_definition)},
    )
    db.execute(
        text(
            """
            INSERT INTO perspective_outputs (id, skill_id, output_json, created_at)
            VALUES (
                'legacy-perspective-output-1',
                'legacy-skill-1',
                '{"summary": "Legacy perspective output tied to a persisted skill."}',
                '2026-06-09 12:30:00'
            )
            """
        )
    )
    db.execute(
        text(
            """
            INSERT INTO agents (
                id, key, name, family, slot_type, agent_json, usage_count, status, last_used_at, created_at
            )
            VALUES (
                'legacy-agent-1',
                'urban_evidence_agent',
                'Urban Evidence Agent',
                'policy',
                'debate',
                :definition,
                5,
                'active',
                '2026-06-09 11:00:00',
                '2026-06-08 11:00:00'
            )
            """
        ),
        {"definition": json.dumps(legacy_agent_definition)},
    )
    db.execute(
        text(
            """
            CREATE TABLE capability_matches (
                id VARCHAR(36) PRIMARY KEY,
                debate_id VARCHAR(36) NOT NULL,
                branch_id VARCHAR(36) NOT NULL,
                capability_kind VARCHAR(16) NOT NULL,
                capability_id VARCHAR(36) NOT NULL,
                selection_reason VARCHAR(32) NOT NULL,
                score INTEGER NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE TABLE agent_outputs (
                id VARCHAR(36) PRIMARY KEY,
                debate_id VARCHAR(36) NOT NULL,
                branch_id VARCHAR(36) NOT NULL,
                skill_id VARCHAR(36) NOT NULL,
                agent_id VARCHAR(36) NOT NULL,
                analyzer_run_ids JSON NOT NULL,
                pros JSON NOT NULL,
                cons JSON NOT NULL,
                summary TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                provenance JSON NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(skill_id) REFERENCES skills (id),
                FOREIGN KEY(agent_id) REFERENCES agents (id)
            )
            """
        )
    )
    db.commit()

    init_db()

    from app.services.dialectical_v2 import create_dialectical_debate

    db.add(
        Worker(
            name="codex-worker",
            token_hash="test-token",
            capabilities=["codex-gpt-5.5"],
            last_seen=now_utc(),
            status="online",
        )
    )
    db.commit()
    debate = create_dialectical_debate(db, "Should all mosquitos be exterminated?", {"max_depth": 1})

    inspector = inspect(db.bind)
    skill_columns = {column["name"] for column in inspector.get_columns("skills")}
    agent_columns = {column["name"] for column in inspector.get_columns("agents")}
    assert {"key", "name", "family", "slot_type", "skill_json", "usage_count"}.isdisjoint(skill_columns)
    assert {"key", "name", "family", "slot_type", "agent_json", "usage_count"}.isdisjoint(agent_columns)

    migrated_skill = db.execute(text("SELECT definition, reuse_count, status FROM skills WHERE id = 'legacy-skill-1'")).mappings().one()
    migrated_agent = db.execute(text("SELECT definition, reuse_count, status FROM agents WHERE id = 'legacy-agent-1'")).mappings().one()
    assert json.loads(migrated_skill["definition"])["name"] == "Urban Mobility Policy Debate Skill"
    assert migrated_skill["reuse_count"] == 7
    assert migrated_skill["status"] == "active"
    assert json.loads(migrated_agent["definition"])["name"] == "Urban Evidence Agent"
    assert migrated_agent["reuse_count"] == 5
    assert migrated_agent["status"] == "active"
    assert db.execute(text("SELECT skill_id FROM perspective_outputs")).scalar_one() == "legacy-skill-1"

    assert debate.status == "generating"
    db.execute(text("DROP TABLE perspective_outputs"))
    db.commit()
