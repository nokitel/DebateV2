from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.orchestration.recursive import OrchestratorRun


@dataclass(frozen=True)
class QBAFRunRecord:
    id: str
    topic: str
    graph: dict[str, Any]
    root_confidence: float
    trace: dict[str, Any]
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "graph": self.graph,
            "root_confidence": self.root_confidence,
            "trace": self.trace,
            "created_at": self.created_at.isoformat(),
        }


class QBAFRunRepository(Protocol):
    def save(self, record: QBAFRunRecord) -> QBAFRunRecord:
        ...

    def get(self, run_id: str) -> QBAFRunRecord | None:
        ...

    def list(self) -> list[QBAFRunRecord]:
        ...


class InMemoryQBAFRunRepository:
    def __init__(self) -> None:
        self.records: dict[str, QBAFRunRecord] = {}

    def save(self, record: QBAFRunRecord) -> QBAFRunRecord:
        self.records[record.id] = record
        return record

    def get(self, run_id: str) -> QBAFRunRecord | None:
        return self.records.get(run_id)

    def list(self) -> list[QBAFRunRecord]:
        return list(self.records.values())


class Neo4jQBAFRunRepository:
    def __init__(self, driver: Any) -> None:
        self.driver = driver

    def save(self, record: QBAFRunRecord) -> QBAFRunRecord:
        raise NotImplementedError("Neo4j persistence requires deployment driver wiring")

    def get(self, run_id: str) -> QBAFRunRecord | None:
        raise NotImplementedError("Neo4j persistence requires deployment driver wiring")

    def list(self) -> list[QBAFRunRecord]:
        raise NotImplementedError("Neo4j persistence requires deployment driver wiring")


def run_to_record(run: OrchestratorRun, *, topic: str, run_id: str | None = None) -> QBAFRunRecord:
    return QBAFRunRecord(
        id=run_id or uuid4().hex,
        topic=topic,
        graph=run.graph.to_dict(),
        root_confidence=run.root_confidence,
        trace={
            "iterations": run.iterations,
            "root_history": list(run.root_history),
            "decisions": [
                {
                    "should_stop": decision.should_stop,
                    "reasons": list(decision.reasons),
                }
                for decision in run.decisions
            ],
        },
        created_at=datetime.now(timezone.utc),
    )
