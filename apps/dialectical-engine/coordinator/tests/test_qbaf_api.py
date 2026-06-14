from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import qbaf as qbaf_api
from app.main import app
from app.metareasoning import StoppingDecision
from app.orchestration import InMemoryQBAFRunRepository, Neo4jQBAFRunRepository, OrchestratorRun, run_to_record
from app.qbaf import ClaimNode, QBAFGraph


USER_HEADERS = {"Authorization": "Bearer user_test_token"}


def sample_run() -> OrchestratorRun:
    graph = QBAFGraph(
        root_id="root",
        nodes={
            "root": ClaimNode(
                id="root",
                text="Remote work improves productivity",
                type="root",
                base_score=0.7,
                final_strength=0.8,
                status="debated",
            )
        },
    )
    return OrchestratorRun(
        graph=graph,
        root_confidence=0.8,
        iterations=2,
        root_history=(0.5, 0.7, 0.8),
        decisions=(StoppingDecision(should_stop=True),),
    )


class FakeOrchestrator:
    def __init__(self, run: OrchestratorRun) -> None:
        self.run_result = run
        self.calls: list[dict] = []

    def run(self, question: str, *, evidence_sources=None, seed_evidence=False) -> OrchestratorRun:
        self.calls.append(
            {
                "question": question,
                "evidence_sources": evidence_sources,
                "seed_evidence": seed_evidence,
            }
        )
        return self.run_result


def test_in_memory_qbaf_run_repository_persists_and_retrieves_graph() -> None:
    repository = InMemoryQBAFRunRepository()
    record = run_to_record(sample_run(), topic="Remote work improves productivity")

    repository.save(record)

    assert repository.get(record.id) == record
    assert repository.list()[0].id == record.id
    assert repository.get(record.id).graph["root_id"] == "root"


def test_neo4j_qbaf_run_repository_uses_injected_driver() -> None:
    class FakeResult:
        def __init__(self, row=None) -> None:
            self.row = row

        def single(self):
            return self.row

    class FakeSession:
        def __init__(self) -> None:
            self.records = {}
            self.queries = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute_write(self, callback, record):
            return callback(self, record)

        def execute_read(self, callback, run_id):
            return callback(self, run_id)

        def run(self, query, **params):
            self.queries.append((query, params))
            if query.strip().startswith("MERGE"):
                self.records[params["id"]] = dict(params)
                return FakeResult()
            record = self.records.get(params["id"])
            if record is None:
                return FakeResult()
            return FakeResult({"record": record})

    class FakeDriver:
        def __init__(self) -> None:
            self.session_obj = FakeSession()

        def session(self):
            return self.session_obj

    driver = FakeDriver()
    repository = Neo4jQBAFRunRepository(driver)
    record = run_to_record(sample_run(), topic="Remote work improves productivity", run_id="run-1")

    repository.save(record)
    reloaded = repository.get("run-1")

    assert reloaded == record
    assert driver.session_obj.queries[0][0].strip().startswith("MERGE")


def test_qbaf_api_starts_persists_and_fetches_run(db, monkeypatch) -> None:
    repository = InMemoryQBAFRunRepository()
    fake_orchestrator = FakeOrchestrator(sample_run())
    monkeypatch.setattr(qbaf_api, "qbaf_repository", repository)
    monkeypatch.setattr(qbaf_api, "build_orchestrator", lambda max_iterations: fake_orchestrator)
    client = TestClient(app)

    response = client.post(
        "/api/qbaf/runs",
        headers=USER_HEADERS,
        json={
            "question": "Remote work improves productivity",
            "seed_evidence": True,
            "max_iterations": 3,
            "evidence_sources": [
                {
                    "reference": "doi:10/support",
                    "text": "A study reports remote work improves productivity.",
                    "quality_grade": "high",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["topic"] == "Remote work improves productivity"
    assert body["root_confidence"] == 0.8
    assert body["graph"]["root_id"] == "root"
    assert body["trace"]["root_history"] == [0.5, 0.7, 0.8]
    assert fake_orchestrator.calls[0]["seed_evidence"] is True
    assert "doi:10/support" in fake_orchestrator.calls[0]["evidence_sources"]

    fetch = client.get(f"/api/qbaf/runs/{body['id']}")
    assert fetch.status_code == 200
    assert fetch.json() == body


def test_qbaf_api_requires_auth_for_starting_run(db) -> None:
    response = TestClient(app).post(
        "/api/qbaf/runs",
        json={"question": "Remote work improves productivity"},
    )

    assert response.status_code == 401
