from __future__ import annotations

from app.core.auth import hash_token
from app.models.entities import Debate, Job, Node, Synthesis, Worker, now_utc
from app.services.serialization import debate_to_dict, iso


def test_iso_serializes_naive_datetimes_as_utc() -> None:
    assert iso(now_utc().replace(tzinfo=None)).endswith("+00:00")


def add_worker(db) -> Worker:
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.flush()
    return worker


def test_debate_detail_includes_active_node_stream_snapshot(db) -> None:
    worker = add_worker(db)
    debate = Debate(topic="Should cities ban cars?", status="generating", config={"max_depth": 1})
    db.add(debate)
    db.flush()
    root = Node(
        debate_id=debate.id,
        parent_id=None,
        node_type="ROOT_CLAIM",
        depth=0,
        position=0,
        claim=debate.topic,
        status="complete",
        materialized_path="0",
    )
    db.add(root)
    db.flush()
    child = Node(
        debate_id=debate.id,
        parent_id=root.id,
        node_type="PRO",
        depth=1,
        position=0,
        claim="Fewer cars would reduce street danger.",
        status="pending",
        materialized_path="0/0",
    )
    db.add(child)
    db.flush()
    debate.root_node_id = root.id
    job = Job(
        debate_id=debate.id,
        node_id=child.id,
        job_type="argue",
        required_role="proposer",
        required_model="mock-local",
        status="running",
        worker_id=worker.id,
        claimed_at=now_utc(),
        stream_buffer="A partial streamed argument.",
    )
    db.add(job)
    db.commit()

    visible = debate_to_dict(db, db.get(Debate, debate.id))
    streamed = visible["tree"]["children"][0]

    assert streamed["status"] == "generating"
    assert streamed["active_generation_id"] == child.active_generation_id
    assert streamed["active_generation"] == {
        "id": f"stream:{job.id}",
        "job_id": job.id,
        "model_id": "mock-local",
        "role": "proposer",
        "argument": "A partial streamed argument.",
        "worker_id": worker.id,
        "worker_name": "mac-mini",
        "created_at": iso(job.claimed_at),
        "is_streaming": True,
    }
    assert visible["models"] == ["mock-local"]
    assert visible["workers"] == ["mac-mini"]


def test_debate_detail_includes_active_synthesis_stream_snapshot(db) -> None:
    worker = add_worker(db)
    debate = Debate(topic="Should schools ban phones?", status="generating", config={"max_depth": 1})
    db.add(debate)
    db.flush()
    job = Job(
        debate_id=debate.id,
        node_id=None,
        job_type="synthesize",
        required_role="synthesizer",
        required_model="mock-local",
        status="running",
        worker_id=worker.id,
        claimed_at=now_utc(),
        stream_buffer='{"strongest_pro":"Focus improves',
    )
    db.add(job)
    db.commit()

    visible = debate_to_dict(db, db.get(Debate, debate.id))

    assert visible["active_synthesis"] == {
        "id": f"stream:{job.id}",
        "job_id": job.id,
        "debate_id": debate.id,
        "model_id": "mock-local",
        "worker_id": worker.id,
        "worker_name": "mac-mini",
        "created_at": iso(job.claimed_at),
        "raw": '{"strongest_pro":"Focus improves',
        "is_streaming": True,
    }
    assert visible["models"] == ["mock-local"]
    assert visible["workers"] == ["mac-mini"]


def test_debate_detail_includes_completed_synthesis_worker_name(db) -> None:
    worker = add_worker(db)
    debate = Debate(topic="Should public transit be free?", status="complete", config={"max_depth": 1})
    db.add(debate)
    db.flush()
    synthesis = Synthesis(
        debate_id=debate.id,
        strongest_pro="It expands access.",
        strongest_con="It needs funding.",
        verdict="It depends on the tax design.",
        model_id="mock-local",
        worker_id=worker.id,
    )
    db.add(synthesis)
    db.flush()
    debate.synthesis_id = synthesis.id
    db.commit()

    visible = debate_to_dict(db, db.get(Debate, debate.id))

    assert visible["synthesis"]["worker_id"] == worker.id
    assert visible["synthesis"]["worker_name"] == "mac-mini"
    assert visible["models"] == ["mock-local"]
    assert visible["workers"] == ["mac-mini"]
