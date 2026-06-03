from __future__ import annotations

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
