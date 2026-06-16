from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


NODE_TYPES = {"root", "sub_claim", "evidence_leaf"}
EDGE_POLARITIES = {"support", "attack"}


def require_non_empty(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    return cleaned


def require_unit_interval(value: float, field_name: str) -> float:
    if value < 0 or value > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return value


@dataclass(frozen=True)
class ClaimNode:
    id: str
    text: str
    type: str
    base_score: float = 0.5
    final_strength: float = 0.5
    uncertainty: float = 0.0
    status: str = "open"
    caveats: list[str] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_empty(self.id, "id"))
        object.__setattr__(self, "text", require_non_empty(self.text, "text"))
        if self.type not in NODE_TYPES:
            raise ValueError(f"type must be one of {sorted(NODE_TYPES)}")
        object.__setattr__(self, "base_score", require_unit_interval(float(self.base_score), "base_score"))
        object.__setattr__(
            self,
            "final_strength",
            require_unit_interval(float(self.final_strength), "final_strength"),
        )
        object.__setattr__(self, "uncertainty", require_unit_interval(float(self.uncertainty), "uncertainty"))
        object.__setattr__(self, "status", require_non_empty(self.status, "status"))
        object.__setattr__(self, "caveats", [str(caveat) for caveat in self.caveats])
        object.__setattr__(self, "transcript", [dict(turn) for turn in self.transcript])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "type": self.type,
            "base_score": self.base_score,
            "final_strength": self.final_strength,
            "uncertainty": self.uncertainty,
            "status": self.status,
            "caveats": list(self.caveats),
            "transcript": [dict(turn) for turn in self.transcript],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ClaimNode":
        return cls(
            id=str(payload["id"]),
            text=str(payload["text"]),
            type=str(payload["type"]),
            base_score=float(payload.get("base_score", 0.5)),
            final_strength=float(payload.get("final_strength", 0.5)),
            uncertainty=float(payload.get("uncertainty", 0.0)),
            status=str(payload.get("status", "open")),
            caveats=[str(caveat) for caveat in payload.get("caveats", [])],
            transcript=[dict(turn) for turn in payload.get("transcript", [])],
        )


@dataclass(frozen=True)
class Edge:
    source_id: str
    target_id: str
    polarity: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", require_non_empty(self.source_id, "source_id"))
        object.__setattr__(self, "target_id", require_non_empty(self.target_id, "target_id"))
        if self.polarity not in EDGE_POLARITIES:
            raise ValueError(f"polarity must be one of {sorted(EDGE_POLARITIES)}")
        object.__setattr__(self, "weight", require_unit_interval(float(self.weight), "weight"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "polarity": self.polarity,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Edge":
        return cls(
            source_id=str(payload["source_id"]),
            target_id=str(payload["target_id"]),
            polarity=str(payload["polarity"]),
            weight=float(payload.get("weight", 1.0)),
        )


@dataclass(frozen=True)
class QBAFGraph:
    root_id: str
    nodes: dict[str, ClaimNode]
    edges: list[Edge] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "root_id", require_non_empty(self.root_id, "root_id"))
        if self.root_id not in self.nodes:
            raise ValueError("root_id must reference an existing node")
        for node_id, node in self.nodes.items():
            if node_id != node.id:
                raise ValueError(f"node key {node_id} does not match node id {node.id}")
        for edge in self.edges:
            if edge.source_id not in self.nodes:
                raise ValueError(f"unknown edge source {edge.source_id}")
            if edge.target_id not in self.nodes:
                raise ValueError(f"unknown edge target {edge.target_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_id": self.root_id,
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "QBAFGraph":
        return cls(
            root_id=str(payload["root_id"]),
            nodes={
                str(node_id): ClaimNode.from_dict(node_payload)
                for node_id, node_payload in payload.get("nodes", {}).items()
            },
            edges=[Edge.from_dict(edge_payload) for edge_payload in payload.get("edges", [])],
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "QBAFGraph":
        return cls.from_dict(json.loads(payload))
