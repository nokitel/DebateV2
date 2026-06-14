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
        with self.driver.session() as session:
            session.execute_write(self._save_record, record)
        return record

    def get(self, run_id: str) -> QBAFRunRecord | None:
        with self.driver.session() as session:
            return session.execute_read(self._get_record, run_id)

    def list(self) -> list[QBAFRunRecord]:
        with self.driver.session() as session:
            return session.execute_read(self._list_records)

    @staticmethod
    def _save_record(tx: Any, record: QBAFRunRecord) -> None:
        tx.run(
            """
            MERGE (run:QBAFRun {id: $id})
            SET run.topic = $topic,
                run.graph = $graph,
                run.root_confidence = $root_confidence,
                run.trace = $trace,
                run.created_at = $created_at
            """,
            **_record_to_params(record),
        )

    @staticmethod
    def _get_record(tx: Any, run_id: str) -> QBAFRunRecord | None:
        result = tx.run(
            """
            MATCH (run:QBAFRun {id: $id})
            RETURN run {.*} AS record
            """,
            id=run_id,
        )
        row = result.single()
        if row is None:
            return None
        return _record_from_params(dict(row["record"]))

    @staticmethod
    def _list_records(tx: Any) -> list[QBAFRunRecord]:
        result = tx.run(
            """
            MATCH (run:QBAFRun)
            RETURN run {.*} AS record
            ORDER BY run.created_at DESC
            """
        )
        return [_record_from_params(dict(row["record"])) for row in result]


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


def _record_to_params(record: QBAFRunRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "topic": record.topic,
        "graph": record.graph,
        "root_confidence": record.root_confidence,
        "trace": record.trace,
        "created_at": record.created_at.isoformat(),
    }


def _record_from_params(params: dict[str, Any]) -> QBAFRunRecord:
    return QBAFRunRecord(
        id=str(params["id"]),
        topic=str(params["topic"]),
        graph=dict(params["graph"]),
        root_confidence=float(params["root_confidence"]),
        trace=dict(params["trace"]),
        created_at=datetime.fromisoformat(str(params["created_at"])),
    )
