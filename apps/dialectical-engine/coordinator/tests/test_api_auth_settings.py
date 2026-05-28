from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

import app.main as app_main
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.auth import hash_token
from app.core.config import DEFAULT_ROUTING, RUNTIME_SETTINGS_KEY
from app.main import _public_hits, app, settings_obj
from app.models.entities import Debate, Generation, Job, Node, Setting, Synthesis, Worker, now_utc
from app.api.settings import apply_persisted_runtime_settings
from app.api.jobs import MAX_FAIL_REASON_CHARS
from app.services.orchestrator import MAX_STREAM_BUFFER_CHARS, MAX_STREAM_DELTA_CHARS, claim_pending_job, create_debate
from app.services.routing import routing_engine


USER_HEADERS = {"Authorization": "Bearer user_test_token"}


def reset_routing() -> None:
    routing_engine.roles = deepcopy(DEFAULT_ROUTING)
    routing_engine.counters.clear()


def test_public_reads_are_open_but_writes_and_settings_require_auth(db) -> None:
    _public_hits.clear()
    client = TestClient(app)

    assert client.get("/api/debates").status_code == 200
    assert client.post("/api/debates", json={"topic": "Should cities ban cars?"}).status_code == 401
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/settings", headers={"Authorization": "Bearer wrong"}).status_code == 403


def test_public_rate_limit_uses_forwarded_client_ip_and_skips_auth_reads(db) -> None:
    _public_hits.clear()
    original_limit = settings_obj.public_rate_limit_per_minute
    settings_obj.public_rate_limit_per_minute = 1
    client = TestClient(app)
    try:
        assert client.get("/api/debates", headers={"CF-Connecting-IP": "198.51.100.10"}).status_code == 200
        assert client.get("/api/debates", headers={"CF-Connecting-IP": "198.51.100.10"}).status_code == 429
        assert client.get("/api/debates", headers={"CF-Connecting-IP": "198.51.100.11"}).status_code == 200

        settings_response = client.get("/api/settings", headers={"CF-Connecting-IP": "198.51.100.10"})
        assert settings_response.status_code == 401
    finally:
        settings_obj.public_rate_limit_per_minute = original_limit
        _public_hits.clear()


def test_public_rate_limit_covers_all_public_read_routes(db) -> None:
    _public_hits.clear()
    original_limit = settings_obj.public_rate_limit_per_minute
    settings_obj.public_rate_limit_per_minute = 0
    client = TestClient(app)
    public_paths = [
        "/api/debates",
        "/api/backends/status",
        "/api/debates/example-id",
        "/api/debates/example-id/events",
        "/api/debates/example-id/export.md",
    ]
    try:
        for index, path in enumerate(public_paths, start=20):
            response = client.get(path, headers={"CF-Connecting-IP": f"198.51.100.{index}"})
            assert response.status_code == 429, path

        assert client.get("/api/settings", headers={"CF-Connecting-IP": "198.51.100.30"}).status_code == 401
        assert client.get("/healthz", headers={"CF-Connecting-IP": "198.51.100.31"}).status_code == 200
    finally:
        settings_obj.public_rate_limit_per_minute = original_limit
        _public_hits.clear()


def test_public_rate_limit_prunes_expired_client_buckets(db, monkeypatch) -> None:
    _public_hits.clear()
    original_limit = settings_obj.public_rate_limit_per_minute
    settings_obj.public_rate_limit_per_minute = 100
    now = 1_000.0
    monkeypatch.setattr(app_main.time, "monotonic", lambda: now)
    _public_hits["198.51.100.50"].append(now - app_main.RATE_LIMIT_WINDOW_SECONDS - 1)
    _public_hits["198.51.100.51"].append(now - app_main.RATE_LIMIT_WINDOW_SECONDS + 1)
    client = TestClient(app)
    try:
        response = client.get("/api/debates", headers={"CF-Connecting-IP": "198.51.100.52"})
    finally:
        settings_obj.public_rate_limit_per_minute = original_limit

    assert response.status_code == 200
    assert "198.51.100.50" not in _public_hits
    assert "198.51.100.51" in _public_hits
    assert "198.51.100.52" in _public_hits
    _public_hits.clear()


def test_public_debate_list_includes_model_metadata(db) -> None:
    _public_hits.clear()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["codex-gpt-5"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    debate = Debate(
        topic="Should cities ban cars?",
        status="complete",
        config={"max_depth": 1},
        completed_at=now_utc(),
    )
    db.add(debate)
    db.flush()
    node = Node(
        debate_id=debate.id,
        node_type="ROOT_CLAIM",
        depth=0,
        position=0,
        claim=debate.topic,
        status="complete",
        materialized_path="/0",
    )
    db.add(node)
    db.flush()
    debate.root_node_id = node.id
    generation = Generation(
        node_id=node.id,
        model_id="codex-gpt-5",
        role="decomposer",
        argument="Initial decomposition.",
        prompt_version="v1",
        prompt_rendered="prompt",
        latency_ms=10,
        is_active=True,
        worker_id=worker.id,
    )
    db.add(generation)
    db.flush()
    node.active_generation_id = generation.id
    synthesis = Synthesis(
        debate_id=debate.id,
        strongest_pro="Cleaner air.",
        strongest_con="Transition cost.",
        verdict="Conditional support.",
        model_id="claude-opus-4.7",
        worker_id=worker.id,
    )
    db.add(synthesis)
    db.flush()
    debate.synthesis_id = synthesis.id
    db.commit()

    response = TestClient(app).get("/api/debates")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["models"] == ["claude-opus-4.7", "codex-gpt-5"]
    assert datetime.fromisoformat(item["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(item["completed_at"]).tzinfo is not None


def test_user_auth_required_for_archive_regenerate_and_history(db) -> None:
    _public_hits.clear()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["codex-gpt-5"],
        last_seen=now_utc(),
        status="online",
    )
    debate = Debate(topic="Should cities ban cars?", status="complete", config={"max_depth": 1})
    db.add_all([worker, debate])
    db.flush()
    root = Node(
        debate_id=debate.id,
        node_type="ROOT_CLAIM",
        depth=0,
        position=0,
        claim=debate.topic,
        status="complete",
        materialized_path="/0",
    )
    db.add(root)
    db.flush()
    debate.root_node_id = root.id
    node = Node(
        debate_id=debate.id,
        parent_id=root.id,
        node_type="PRO",
        depth=1,
        position=0,
        claim="Cleaner air.",
        status="complete",
        materialized_path="/0/0",
    )
    db.add(node)
    db.flush()
    generation = Generation(
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
    db.add(generation)
    db.flush()
    node.active_generation_id = generation.id
    db.commit()

    client = TestClient(app)

    assert client.delete(f"/api/debates/{debate.id}").status_code == 401
    assert client.get(f"/api/nodes/{node.id}/generations").status_code == 401
    assert client.post(f"/api/nodes/{node.id}/regenerate", json={}).status_code == 401
    assert client.get(f"/api/nodes/{node.id}/generations", headers={"Authorization": "Bearer wrong"}).status_code == 403

    history = client.get(f"/api/nodes/{node.id}/generations", headers=USER_HEADERS)
    assert history.status_code == 200
    item = history.json()["items"][0]
    assert item["id"] == generation.id
    assert datetime.fromisoformat(item["created_at"]).tzinfo is not None

    root_regenerated = client.post(f"/api/nodes/{root.id}/regenerate", headers=USER_HEADERS, json={})
    assert root_regenerated.status_code == 200
    assert db.get(Job, root_regenerated.json()["job_id"]).job_type == "decompose"

    regenerated = client.post(f"/api/nodes/{node.id}/regenerate", headers=USER_HEADERS, json={})
    assert regenerated.status_code == 200
    assert db.get(Job, regenerated.json()["job_id"]) is not None

    archived = client.delete(f"/api/debates/{debate.id}", headers=USER_HEADERS)
    assert archived.status_code == 200
    db.expire_all()
    assert db.get(Debate, debate.id).status == "archived"


def test_archive_cancels_active_jobs_and_blocks_node_mutations(db) -> None:
    _public_hits.clear()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    debate = Debate(topic="Should cities ban cars?", status="generating", config={"max_depth": 1})
    db.add_all([worker, debate])
    db.flush()
    root = Node(
        debate_id=debate.id,
        node_type="ROOT_CLAIM",
        depth=0,
        position=0,
        claim=debate.topic,
        status="generating",
        materialized_path="/0",
    )
    db.add(root)
    db.flush()
    debate.root_node_id = root.id
    generation = Generation(
        node_id=root.id,
        model_id="mock-local",
        role="decomposer",
        argument="Initial decomposition.",
        prompt_version="v1",
        prompt_rendered="prompt",
        latency_ms=10,
        is_active=True,
        worker_id=worker.id,
    )
    running_job = Job(
        debate_id=debate.id,
        node_id=root.id,
        job_type="decompose",
        required_role="decomposer",
        required_model="mock-local",
        status="running",
        worker_id=worker.id,
        deadline=now_utc(),
    )
    db.add_all([generation, running_job])
    db.flush()
    root.active_generation_id = generation.id
    worker.current_job_id = running_job.id
    db.commit()
    client = TestClient(app)

    archived = client.delete(f"/api/debates/{debate.id}", headers=USER_HEADERS)

    assert archived.status_code == 200
    db.expire_all()
    assert db.get(Debate, debate.id).status == "archived"
    assert db.get(Job, running_job.id).status == "failed"
    assert db.get(Job, running_job.id).error == "Debate archived"
    assert db.get(Job, running_job.id).worker_id is None
    assert db.get(Worker, worker.id).current_job_id is None
    assert client.get(f"/api/debates/{debate.id}").status_code == 404
    assert client.get(f"/api/debates/{debate.id}/export.md").status_code == 404
    assert client.post(f"/api/nodes/{root.id}/regenerate", headers=USER_HEADERS, json={}).status_code == 404
    assert client.get(f"/api/nodes/{root.id}/generations", headers=USER_HEADERS).status_code == 404


def test_worker_heartbeat_rejects_invalid_status(db) -> None:
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    client = TestClient(app)
    headers = {"Authorization": "Bearer worker-token"}

    response = client.post(
        f"/api/workers/{worker.id}/heartbeat",
        headers=headers,
        json={"capabilities": ["mock-local"], "status": "busy"},
    )

    assert response.status_code == 422
    db.refresh(worker)
    assert worker.status == "online"


def test_worker_heartbeat_accepts_degraded_status(db) -> None:
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    client = TestClient(app)
    headers = {"Authorization": "Bearer worker-token"}

    response = client.post(
        f"/api/workers/{worker.id}/heartbeat",
        headers=headers,
        json={"capabilities": [" mock-local ", "mock-local"], "status": "degraded"},
    )

    assert response.status_code == 200
    db.refresh(worker)
    assert worker.status == "degraded"
    assert worker.capabilities == ["mock-local"]

    invalid_capability = client.post(
        f"/api/workers/{worker.id}/heartbeat",
        headers=headers,
        json={"capabilities": [" "], "status": "online"},
    )
    assert invalid_capability.status_code == 422
    db.refresh(worker)
    assert worker.status == "degraded"
    assert worker.capabilities == ["mock-local"]


def test_backend_status_requeues_active_jobs_for_stale_worker(db) -> None:
    worker = Worker(
        name="adesso-mbp",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc() - timedelta(seconds=settings_obj.worker_offline_seconds + 5),
        status="online",
    )
    debate = Debate(topic="Should cities ban cars?", status="generating", config={"max_depth": 1})
    db.add_all([worker, debate])
    db.flush()
    node = Node(
        debate_id=debate.id,
        node_type="PRO",
        depth=1,
        position=0,
        claim="Cleaner air.",
        status="generating",
        materialized_path="/0/0",
    )
    db.add(node)
    db.flush()
    running_job = Job(
        debate_id=debate.id,
        node_id=node.id,
        job_type="argue",
        required_role="proposer",
        required_model="mock-local",
        status="running",
        worker_id=worker.id,
        claimed_at=now_utc(),
        deadline=now_utc() + timedelta(seconds=60),
        stream_buffer="partial abandoned output",
    )
    db.add(running_job)
    db.flush()
    worker.current_job_id = running_job.id
    db.commit()

    response = TestClient(app).get("/api/backends/status")

    assert response.status_code == 200
    row = response.json()["workers"][0]
    assert row["status"] == "offline"
    assert row["current_job_id"] is None
    assert datetime.fromisoformat(row["last_seen"]).tzinfo is not None
    assert row["last_seen"].endswith("+00:00")
    db.expire_all()
    refreshed_worker = db.get(Worker, worker.id)
    refreshed_job = db.get(Job, running_job.id)
    refreshed_node = db.get(Node, node.id)
    refreshed_debate = db.get(Debate, debate.id)
    assert refreshed_worker.status == "offline"
    assert refreshed_worker.current_job_id is None
    assert refreshed_job.status == "pending"
    assert refreshed_job.worker_id is None
    assert refreshed_job.claimed_at is None
    assert refreshed_job.stream_buffer == ""
    assert refreshed_job.error == "Worker offline"
    assert refreshed_node.status == "pending"
    assert refreshed_debate.status == "generating"


def test_worker_registration_rejects_blank_identity_or_capabilities(db) -> None:
    _public_hits.clear()
    client = TestClient(app)

    blank_name = client.post(
        "/api/workers/register",
        headers=USER_HEADERS,
        json={"name": " ", "capabilities": ["mock-local"]},
    )
    blank_capability = client.post(
        "/api/workers/register",
        headers=USER_HEADERS,
        json={"name": "mac-mini", "capabilities": [" "]},
    )
    empty_capabilities = client.post(
        "/api/workers/register",
        headers=USER_HEADERS,
        json={"name": "mac-mini", "capabilities": []},
    )

    assert blank_name.status_code == 422
    assert "name" in blank_name.json()["detail"]
    assert blank_capability.status_code == 422
    assert "capabilities" in blank_capability.json()["detail"]
    assert empty_capabilities.status_code == 422
    assert "capabilities" in empty_capabilities.json()["detail"]
    assert db.scalars(select(Worker)).all() == []


def test_worker_reregistration_requeues_active_job_and_rotates_token(db) -> None:
    _public_hits.clear()
    worker = Worker(
        name="adesso-mbp",
        token_hash=hash_token("old-worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    debate = Debate(topic="Should cities ban cars?", status="generating", config={"max_depth": 1})
    db.add_all([worker, debate])
    db.flush()
    node = Node(
        debate_id=debate.id,
        node_type="PRO",
        depth=1,
        position=0,
        claim="Cleaner air.",
        status="generating",
        materialized_path="/0/0",
    )
    db.add(node)
    db.flush()
    running_job = Job(
        debate_id=debate.id,
        node_id=node.id,
        job_type="argue",
        required_role="proposer",
        required_model="mock-local",
        status="running",
        worker_id=worker.id,
        deadline=now_utc(),
        stream_buffer="partial output from old registration",
    )
    db.add(running_job)
    db.flush()
    worker.current_job_id = running_job.id
    db.commit()
    client = TestClient(app)

    response = client.post(
        "/api/workers/register",
        headers=USER_HEADERS,
        json={"name": " adesso-mbp ", "capabilities": [" codex-gpt-5 ", "codex-gpt-5"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["worker_id"] == worker.id
    assert payload["worker_token"] != "old-worker-token"
    assert payload["name"] == "adesso-mbp"
    assert payload["capabilities"] == ["codex-gpt-5"]
    db.expire_all()
    refreshed_worker = db.get(Worker, worker.id)
    refreshed_job = db.get(Job, running_job.id)
    assert refreshed_worker.current_job_id is None
    assert refreshed_worker.capabilities == ["codex-gpt-5"]
    assert refreshed_worker.name == "adesso-mbp"
    assert refreshed_worker.status == "online"
    assert refreshed_job.status == "pending"
    assert refreshed_job.worker_id is None
    assert refreshed_job.claimed_at is None
    assert refreshed_job.error == "Worker re-registered"
    assert refreshed_job.stream_buffer == ""

    old_heartbeat = client.post(
        f"/api/workers/{worker.id}/heartbeat",
        headers={"Authorization": "Bearer old-worker-token"},
        json={"capabilities": ["mock-local"]},
    )
    new_heartbeat = client.post(
        f"/api/workers/{worker.id}/heartbeat",
        headers={"Authorization": f"Bearer {payload['worker_token']}"},
        json={"capabilities": [" codex-gpt-5 ", "codex-gpt-5"]},
    )
    assert old_heartbeat.status_code == 403
    assert new_heartbeat.status_code == 200
    db.expire_all()
    assert len(db.scalars(select(Worker)).all()) == 1
    assert db.get(Worker, worker.id).capabilities == ["codex-gpt-5"]


def test_completed_job_rejects_late_worker_mutations(db) -> None:
    _public_hits.clear()
    reset_routing()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    debate = Debate(topic="Should cities ban cars?", status="generating", config={"max_depth": 1, "branching": 2})
    db.add_all([worker, debate])
    db.flush()
    root = Node(
        debate_id=debate.id,
        node_type="ROOT_CLAIM",
        depth=0,
        position=0,
        claim=debate.topic,
        status="complete",
        materialized_path="/0",
    )
    db.add(root)
    db.flush()
    debate.root_node_id = root.id
    child = Node(
        debate_id=debate.id,
        parent_id=root.id,
        node_type="PRO",
        depth=1,
        position=0,
        claim="Cleaner air.",
        status="generating",
        materialized_path="/0/0",
    )
    db.add(child)
    db.flush()
    job = Job(
        debate_id=debate.id,
        node_id=child.id,
        job_type="argue",
        required_role="proposer",
        required_model="mock-local",
        status="running",
        worker_id=worker.id,
        deadline=now_utc(),
    )
    db.add(job)
    db.flush()
    worker.current_job_id = job.id
    db.commit()
    client = TestClient(app)
    headers = {"Authorization": "Bearer worker-token", "X-Worker-ID": worker.id}

    completed = client.post(
        f"/api/jobs/{job.id}/complete",
        headers=headers,
        json={"result": {"argument": "Cleaner air improves public health."}, "latency_ms": 5},
    )
    late_complete = client.post(
        f"/api/jobs/{job.id}/complete",
        headers=headers,
        json={"result": {"argument": "A duplicate argument."}, "latency_ms": 5},
    )
    late_stream = client.post(f"/api/jobs/{job.id}/stream", headers=headers, json={"delta": "late token"})
    late_fail = client.post(f"/api/jobs/{job.id}/fail", headers=headers, json={"reason": "late failure"})

    assert completed.status_code == 200
    assert late_complete.status_code == 409
    assert late_stream.status_code == 409
    assert late_fail.status_code == 409
    db.expire_all()
    generations = db.scalars(select(Generation).where(Generation.node_id == child.id)).all()
    assert len(generations) == 1
    assert generations[0].argument == "Cleaner air improves public health."
    assert db.get(Job, job.id).status == "complete"


def test_worker_complete_rejects_invalid_metadata_and_malformed_result(db) -> None:
    _public_hits.clear()
    reset_routing()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    debate = create_debate(db, "Should cities ban cars?", {"max_depth": 1, "branching": 2})
    job = claim_pending_job(db, worker)
    assert job is not None
    assert job.job_type == "decompose"
    client = TestClient(app)
    headers = {"Authorization": "Bearer worker-token", "X-Worker-ID": worker.id}

    negative_tokens = client.post(
        f"/api/jobs/{job.id}/complete",
        headers=headers,
        json={"result": {"argument": "Invalid accounting."}, "tokens_in": -1, "tokens_out": 1, "latency_ms": 5},
    )
    malformed_result = client.post(
        f"/api/jobs/{job.id}/complete",
        headers=headers,
        json={"result": "plain text without structured JSON", "tokens_in": 1, "tokens_out": 1, "latency_ms": 5},
    )

    assert negative_tokens.status_code == 422
    assert malformed_result.status_code == 400
    assert "valid JSON object" in malformed_result.json()["detail"]
    db.expire_all()
    refreshed_job = db.get(Job, job.id)
    refreshed_worker = db.get(Worker, worker.id)
    assert refreshed_job.status == "running"
    assert refreshed_job.worker_id == worker.id
    assert refreshed_worker.current_job_id == job.id


def test_worker_stream_rejects_oversized_delta_and_buffer_without_mutating_job(db) -> None:
    _public_hits.clear()
    reset_routing()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    create_debate(db, "Should cities ban cars?", {"max_depth": 1, "branching": 2})
    job = claim_pending_job(db, worker)
    assert job is not None
    original_status = job.status
    client = TestClient(app)
    headers = {"Authorization": "Bearer worker-token", "X-Worker-ID": worker.id}

    oversized_delta = client.post(
        f"/api/jobs/{job.id}/stream",
        headers=headers,
        json={"delta": "x" * (MAX_STREAM_DELTA_CHARS + 1)},
    )

    assert oversized_delta.status_code == 413
    assert "stream delta" in oversized_delta.json()["detail"]
    db.expire_all()
    refreshed_job = db.get(Job, job.id)
    assert refreshed_job.stream_buffer == ""
    assert refreshed_job.status == original_status

    refreshed_job.stream_buffer = "x" * (MAX_STREAM_BUFFER_CHARS - 5)
    refreshed_job.status = "running"
    db.commit()
    overflow_buffer = client.post(f"/api/jobs/{job.id}/stream", headers=headers, content="y" * 6)

    assert overflow_buffer.status_code == 413
    assert "stream buffer" in overflow_buffer.json()["detail"]
    db.expire_all()
    assert db.get(Job, job.id).stream_buffer == "x" * (MAX_STREAM_BUFFER_CHARS - 5)


def test_worker_stream_offset_makes_delta_retries_idempotent(db) -> None:
    _public_hits.clear()
    reset_routing()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    create_debate(db, "Should cities ban cars?", {"max_depth": 1, "branching": 2})
    job = claim_pending_job(db, worker)
    assert job is not None
    client = TestClient(app)
    headers = {"Authorization": "Bearer worker-token", "X-Worker-ID": worker.id}

    first = client.post(f"/api/jobs/{job.id}/stream", headers=headers, json={"delta": "hello ", "offset": 0})
    duplicate = client.post(f"/api/jobs/{job.id}/stream", headers=headers, json={"delta": "hello ", "offset": 0})
    second = client.post(f"/api/jobs/{job.id}/stream", headers=headers, json={"delta": "world", "offset": 6})

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert second.status_code == 200
    db.expire_all()
    assert db.get(Job, job.id).stream_buffer == "hello world"

    conflict = client.post(f"/api/jobs/{job.id}/stream", headers=headers, json={"delta": "oops", "offset": 99})

    assert conflict.status_code == 409
    assert "stream offset" in conflict.json()["detail"]
    db.expire_all()
    assert db.get(Job, job.id).stream_buffer == "hello world"


def test_worker_fail_rejects_blank_or_oversized_reason_without_mutating_job(db) -> None:
    _public_hits.clear()
    reset_routing()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    create_debate(db, "Should cities ban cars?", {"max_depth": 1, "branching": 2})
    job = claim_pending_job(db, worker)
    assert job is not None
    original_status = job.status
    client = TestClient(app)
    headers = {"Authorization": "Bearer worker-token", "X-Worker-ID": worker.id}

    blank_reason = client.post(f"/api/jobs/{job.id}/fail", headers=headers, json={"reason": ""})
    oversized_reason = client.post(
        f"/api/jobs/{job.id}/fail",
        headers=headers,
        json={"reason": "x" * (MAX_FAIL_REASON_CHARS + 1)},
    )

    assert blank_reason.status_code == 422
    assert oversized_reason.status_code == 422
    db.expire_all()
    refreshed_job = db.get(Job, job.id)
    refreshed_worker = db.get(Worker, worker.id)
    assert refreshed_job.status == original_status
    assert refreshed_job.error is None
    assert refreshed_worker.current_job_id == job.id


def test_settings_api_persists_enabled_models_and_filters_created_jobs(db) -> None:
    _public_hits.clear()
    reset_routing()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local", "codex-gpt-5"],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    db.commit()
    client = TestClient(app)

    response = client.put(
        "/api/settings",
        headers=USER_HEADERS,
        json={"enabled_models": [" codex-gpt-5 ", "codex-gpt-5"]},
    )

    assert response.status_code == 200
    assert response.json()["enabled_models"] == ["codex-gpt-5"]
    assert "codex-gpt-5" in response.json()["configured_models"]
    assert "mock-local" in response.json()["configured_models"]
    assert response.json()["grok_monthly_spend_usd"] == 0
    assert response.json()["grok_pricing_usd_per_million_tokens"] == {"input": 1.25, "output": 2.5}
    assert response.json()["model_monthly_caps_usd"]["grok-4"] == 25.0
    assert response.json()["model_monthly_spend_usd"]["codex-gpt-5"] == 0
    assert response.json()["model_pricing_usd_per_million_tokens"]["grok-4"] == {"input": 1.25, "output": 2.5}
    persisted = db.get(Setting, RUNTIME_SETTINGS_KEY)
    assert persisted is not None
    assert persisted.value["enabled_models"] == ["codex-gpt-5"]
    assert "configured_models" not in persisted.value
    assert "grok_monthly_spend_usd" not in persisted.value
    assert "model_monthly_spend_usd" not in persisted.value

    created = client.post(
        "/api/debates",
        headers=USER_HEADERS,
        json={"topic": "Should cities ban cars?", "config": {"max_depth": 1}},
    )

    assert created.status_code == 200
    job = db.scalar(select(Job).where(Job.debate_id == created.json()["id"]))
    assert job is not None
    assert job.required_model == "codex-gpt-5"


def test_settings_api_persists_model_monthly_caps(db) -> None:
    _public_hits.clear()
    reset_routing()
    client = TestClient(app)

    response = client.put(
        "/api/settings",
        headers=USER_HEADERS,
        json={"model_monthly_caps_usd": {" codex-gpt-5 ": 3.5, "mock-local": 0}},
    )

    assert response.status_code == 200
    assert response.json()["model_monthly_caps_usd"]["codex-gpt-5"] == 3.5
    assert response.json()["model_monthly_caps_usd"]["mock-local"] == 0
    assert response.json()["grok_monthly_cap_usd"] == 25.0
    persisted = db.get(Setting, RUNTIME_SETTINGS_KEY)
    assert persisted is not None
    assert persisted.value["model_monthly_caps_usd"] == {"codex-gpt-5": 3.5, "mock-local": 0.0}
    assert persisted.value["grok_monthly_cap_usd"] == 25.0

    legacy = client.put("/api/settings", headers=USER_HEADERS, json={"grok_monthly_cap_usd": 7})

    assert legacy.status_code == 200
    assert legacy.json()["model_monthly_caps_usd"]["grok-4"] == 7
    db.expire_all()
    assert db.get(Setting, RUNTIME_SETTINGS_KEY).value["model_monthly_caps_usd"]["grok-4"] == 7


def test_debate_create_rejects_invalid_config_values(db) -> None:
    _public_hits.clear()
    client = TestClient(app)

    response = client.post(
        "/api/debates",
        headers=USER_HEADERS,
        json={"topic": "Should cities ban cars?", "config": {"branching": []}},
    )

    assert response.status_code == 400
    assert "branching" in response.json()["detail"]
    assert "integer" in response.json()["detail"]
    assert db.scalar(select(Debate)) is None


def test_regenerate_validates_explicit_model_id_before_queuing(db) -> None:
    _public_hits.clear()
    reset_routing()
    worker = Worker(
        name="mac-mini",
        token_hash=hash_token("worker-token"),
        capabilities=["mock-local", "codex-gpt-5"],
        last_seen=now_utc(),
        status="online",
    )
    debate = Debate(topic="Should cities ban cars?", status="complete", config={"max_depth": 1})
    db.add_all([worker, debate])
    db.flush()
    root = Node(
        debate_id=debate.id,
        node_type="ROOT_CLAIM",
        depth=0,
        position=0,
        claim=debate.topic,
        status="complete",
        materialized_path="/0",
    )
    db.add(root)
    db.flush()
    node = Node(
        debate_id=debate.id,
        parent_id=root.id,
        node_type="PRO",
        depth=1,
        position=0,
        claim="Cleaner air.",
        status="complete",
        materialized_path="/0/0",
    )
    db.add(node)
    db.flush()
    generation = Generation(
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
    db.add(generation)
    db.flush()
    node.active_generation_id = generation.id
    db.commit()
    client = TestClient(app)

    blank_model = client.post(
        f"/api/nodes/{node.id}/regenerate",
        headers=USER_HEADERS,
        json={"model_id": "   "},
    )
    unknown_model = client.post(
        f"/api/nodes/{node.id}/regenerate",
        headers=USER_HEADERS,
        json={"model_id": "unknown-model"},
    )
    too_long_model = client.post(
        f"/api/nodes/{node.id}/regenerate",
        headers=USER_HEADERS,
        json={"model_id": "x" * 121},
    )

    assert blank_model.status_code == 400
    assert "model_id" in blank_model.json()["detail"]
    assert unknown_model.status_code == 400
    assert "unknown-model" in unknown_model.json()["detail"]
    assert too_long_model.status_code == 422
    db.expire_all()
    assert db.scalar(select(Job).where(Job.node_id == node.id)) is None
    assert db.get(Node, node.id).status == "complete"
    assert db.get(Debate, debate.id).status == "complete"

    trimmed_model = client.post(
        f"/api/nodes/{node.id}/regenerate",
        headers=USER_HEADERS,
        json={"model_id": " codex-gpt-5 "},
    )

    assert trimmed_model.status_code == 200
    queued_job = db.get(Job, trimmed_model.json()["job_id"])
    assert queued_job.required_model == "codex-gpt-5"


def test_settings_api_rejects_invalid_routing_without_changing_runtime(db) -> None:
    _public_hits.clear()
    reset_routing()
    original_roles = deepcopy(routing_engine.roles)
    client = TestClient(app)

    response = client.put("/api/settings", headers=USER_HEADERS, json={"routing": {"proposer": "not-an-object"}})

    assert response.status_code == 422
    assert "routing.proposer" in response.json()["detail"]
    assert db.get(Setting, RUNTIME_SETTINGS_KEY) is None
    assert routing_engine.roles == original_roles

    invalid_enabled = client.put("/api/settings", headers=USER_HEADERS, json={"enabled_models": [" "]})
    assert invalid_enabled.status_code == 422
    assert "enabled_models" in invalid_enabled.json()["detail"]
    assert db.get(Setting, RUNTIME_SETTINGS_KEY) is None
    assert routing_engine.roles == original_roles

    unknown_enabled = client.put("/api/settings", headers=USER_HEADERS, json={"enabled_models": ["unknown-model"]})
    assert unknown_enabled.status_code == 422
    assert "not present in routing" in unknown_enabled.json()["detail"]
    assert "unknown-model" in unknown_enabled.json()["detail"]
    assert db.get(Setting, RUNTIME_SETTINGS_KEY) is None
    assert routing_engine.roles == original_roles

    invalid_strategy = client.put(
        "/api/settings",
        headers=USER_HEADERS,
        json={"routing": {"proposer": {"pool": ["mock-local"], "strategy": "random"}}},
    )
    assert invalid_strategy.status_code == 422
    assert "routing.proposer.strategy" in invalid_strategy.json()["detail"]
    assert "round_robin" in invalid_strategy.json()["detail"]
    assert db.get(Setting, RUNTIME_SETTINGS_KEY) is None
    assert routing_engine.roles == original_roles

    invalid_constraint = client.put(
        "/api/settings",
        headers=USER_HEADERS,
        json={"routing": {"opponent": {"pool": ["mock-local"], "constraint": "same_as_claim_author"}}},
    )
    assert invalid_constraint.status_code == 422
    assert "routing.opponent.constraint" in invalid_constraint.json()["detail"]
    assert "not_same_as_claim_author" in invalid_constraint.json()["detail"]
    assert db.get(Setting, RUNTIME_SETTINGS_KEY) is None
    assert routing_engine.roles == original_roles

    negative_cap = client.put("/api/settings", headers=USER_HEADERS, json={"grok_monthly_cap_usd": -1})
    assert negative_cap.status_code == 422
    assert db.get(Setting, RUNTIME_SETTINGS_KEY) is None
    assert routing_engine.roles == original_roles

    negative_model_cap = client.put(
        "/api/settings",
        headers=USER_HEADERS,
        json={"model_monthly_caps_usd": {"mock-local": -1}},
    )
    assert negative_model_cap.status_code == 422
    assert "model_monthly_caps_usd.mock-local" in negative_model_cap.json()["detail"]
    assert db.get(Setting, RUNTIME_SETTINGS_KEY) is None
    assert routing_engine.roles == original_roles

    unknown_model_cap = client.put(
        "/api/settings",
        headers=USER_HEADERS,
        json={"model_monthly_caps_usd": {"unknown-model": 1}},
    )
    assert unknown_model_cap.status_code == 422
    assert "not present in routing" in unknown_model_cap.json()["detail"]
    assert "unknown-model" in unknown_model_cap.json()["detail"]
    assert db.get(Setting, RUNTIME_SETTINGS_KEY) is None
    assert routing_engine.roles == original_roles


def test_settings_api_validates_enabled_models_against_updated_routing(db) -> None:
    _public_hits.clear()
    reset_routing()
    client = TestClient(app)

    response = client.put(
        "/api/settings",
        headers=USER_HEADERS,
        json={
            "routing": {
                "decomposer": {"primary": "local-specialist", "fallback": []},
                "proposer": {"pool": ["local-specialist"], "strategy": "round_robin"},
            },
            "enabled_models": ["local-specialist"],
        },
    )

    assert response.status_code == 200
    assert response.json()["configured_models"] == ["local-specialist"]
    assert response.json()["enabled_models"] == ["local-specialist"]
    persisted = db.get(Setting, RUNTIME_SETTINGS_KEY)
    assert persisted is not None
    assert persisted.value["enabled_models"] == ["local-specialist"]


def test_settings_api_reads_and_repairs_legacy_malformed_runtime_settings(db) -> None:
    _public_hits.clear()
    reset_routing()
    db.add(
        Setting(
            key=RUNTIME_SETTINGS_KEY,
            value={
                "routing": {"proposer": "not-an-object"},
                "enabled_models": [" codex-gpt-5 ", " ", None, "codex-gpt-5", "retired-model"],
                "grok_monthly_cap_usd": "not-a-number",
            },
        )
    )
    db.commit()
    client = TestClient(app)

    current = client.get("/api/settings", headers=USER_HEADERS)

    assert current.status_code == 200
    assert current.json()["enabled_models"] == ["codex-gpt-5"]
    assert current.json()["grok_monthly_cap_usd"] == 25.0
    assert current.json()["routing"] == routing_engine.as_dict()

    repaired = client.put(
        "/api/settings",
        headers=USER_HEADERS,
        json={"enabled_models": ["mock-local"], "grok_monthly_cap_usd": 5},
    )

    assert repaired.status_code == 200
    persisted = db.get(Setting, RUNTIME_SETTINGS_KEY)
    assert persisted.value["routing"] == routing_engine.as_dict()
    assert persisted.value["enabled_models"] == ["mock-local"]
    assert persisted.value["grok_monthly_cap_usd"] == 5


def test_persisted_valid_routing_loads_into_runtime_engine(db) -> None:
    _public_hits.clear()
    reset_routing()
    persisted_routing = {
        "decomposer": {"primary": "codex-gpt-5", "fallback": ["mock-local"]},
        "synthesizer": {"primary": "mock-local", "fallback": []},
    }
    db.add(Setting(key=RUNTIME_SETTINGS_KEY, value={"routing": persisted_routing}))
    db.commit()

    apply_persisted_runtime_settings(db)

    try:
        assert routing_engine.roles["decomposer"]["primary"] == "codex-gpt-5"
        worker = Worker(
            name="mac-mini",
            token_hash=hash_token("worker-token"),
            capabilities=["mock-local", "codex-gpt-5"],
            last_seen=now_utc(),
            status="online",
        )
        db.add(worker)
        db.commit()

        debate = create_debate(db, "Should cities ban cars?", {"max_depth": 1})
        job = db.scalar(select(Job).where(Job.debate_id == debate.id))

        assert job.required_model == "codex-gpt-5"
    finally:
        reset_routing()


def test_settings_api_accepts_valid_routing_and_normalizes_models(db) -> None:
    _public_hits.clear()
    reset_routing()
    client = TestClient(app)
    routing = {
        "decomposer": {"primary": " mock-local ", "fallback": [" codex-gpt-5 "]},
        "proposer": {"pool": [" mock-local ", "codex-gpt-5"], "strategy": "round_robin"},
        "opponent": {
            "pool": ["mock-local", " codex-gpt-5 "],
            "strategy": "round_robin",
            "constraint": "not_same_as_claim_author",
        },
        "synthesizer": {"primary": " mock-local ", "fallback": []},
    }

    try:
        response = client.put("/api/settings", headers=USER_HEADERS, json={"routing": routing})

        assert response.status_code == 200
        payload = response.json()
        assert payload["routing"]["decomposer"]["primary"] == "mock-local"
        assert payload["routing"]["decomposer"]["fallback"] == ["codex-gpt-5"]
        assert payload["routing"]["proposer"]["pool"] == ["mock-local", "codex-gpt-5"]
        assert routing_engine.roles["opponent"]["pool"] == ["mock-local", "codex-gpt-5"]
        persisted = db.get(Setting, RUNTIME_SETTINGS_KEY)
        assert persisted is not None
        assert persisted.value["routing"]["synthesizer"]["primary"] == "mock-local"
    finally:
        reset_routing()
