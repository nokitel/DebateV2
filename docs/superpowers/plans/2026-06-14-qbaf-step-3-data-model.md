# QBAF Step 3 Data Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the pure in-memory QBAF graph data model and JSON round-trip support.

**Architecture:** The model lives under `coordinator/app/qbaf/` and has no provider, database, network, or orchestration dependency. `ClaimNode`, `Edge`, and `QBAFGraph` are dataclasses with explicit validation and stable `to_dict` / `from_dict` / `to_json` / `from_json` helpers.

**Tech Stack:** Python 3.12, dataclasses, standard-library JSON, pytest, no new dependencies.

---

## File Structure

- Create `apps/dialectical-engine/coordinator/app/qbaf/model.py`: QBAF dataclasses, validation, serialization.
- Modify `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`: export model types.
- Create `apps/dialectical-engine/coordinator/tests/test_qbaf_model.py`: round-trip and validation tests.

## Step Goal, Files, DoD, And Tests

Step goal: represent a hand-made QBAF graph in memory and serialize/reload it without loss.

Files touched:

- `apps/dialectical-engine/coordinator/app/qbaf/model.py`
- `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`
- `apps/dialectical-engine/coordinator/tests/test_qbaf_model.py`

Definition of Done:

- `ClaimNode` supports `id`, `text`, `type`, `base_score`, `final_strength`, `uncertainty`, `status`, `caveats`, and `transcript`.
- `Edge` supports `source_id`, `target_id`, `polarity`, and `weight`.
- `QBAFGraph` validates node IDs, edge endpoints, score ranges, uncertainty ranges, edge weights, and allowed node/edge types.
- A hand-made root/subclaim/evidence graph round-trips through JSON.
- No provider, time, randomness, file I/O, network I/O, or database access is introduced.
- Focused tests pass, then full `make test` passes on Python 3.12.
- Step 3 commit is created with message `feat(step-3): add qbaf graph data model`.

Exact focused test:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_model.py -q
```

Full app test:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

---

### Task 1: Add Failing QBAF Model Tests

**Files:**
- Create: `apps/dialectical-engine/coordinator/tests/test_qbaf_model.py`

- [x] **Step 1: Write the failing tests**

Create `apps/dialectical-engine/coordinator/tests/test_qbaf_model.py`:

```python
from __future__ import annotations

import json

import pytest

from app.qbaf import ClaimNode, Edge, QBAFGraph


def test_qbaf_graph_round_trips_json() -> None:
    graph = QBAFGraph(
        root_id="root",
        nodes={
            "root": ClaimNode(
                id="root",
                text="Remote work improves productivity",
                type="root",
                base_score=0.55,
                final_strength=0.55,
                uncertainty=0.20,
                status="open",
                caveats=["evidence quality still pending"],
                transcript=[{"role": "judge", "content": "initial estimate"}],
            ),
            "sub-1": ClaimNode(
                id="sub-1",
                text="Workers report fewer interruptions",
                type="sub_claim",
                base_score=0.70,
                final_strength=0.70,
                uncertainty=0.10,
                status="scored",
            ),
            "evidence-1": ClaimNode(
                id="evidence-1",
                text="Survey result supports fewer interruptions",
                type="evidence_leaf",
                base_score=0.80,
                final_strength=0.80,
                uncertainty=0.05,
                status="grounded",
            ),
        },
        edges=[
            Edge(source_id="sub-1", target_id="root", polarity="support", weight=0.60),
            Edge(source_id="evidence-1", target_id="sub-1", polarity="support", weight=0.75),
        ],
    )

    reloaded = QBAFGraph.from_json(graph.to_json())

    assert reloaded == graph
    assert json.loads(reloaded.to_json())["root_id"] == "root"
    assert reloaded.nodes["root"].caveats == ["evidence quality still pending"]
    assert reloaded.nodes["root"].transcript == [{"role": "judge", "content": "initial estimate"}]


def test_claim_node_rejects_invalid_score_ranges() -> None:
    with pytest.raises(ValueError, match="base_score must be between 0 and 1"):
        ClaimNode(id="bad", text="bad", type="root", base_score=1.1)

    with pytest.raises(ValueError, match="uncertainty must be between 0 and 1"):
        ClaimNode(id="bad", text="bad", type="root", uncertainty=-0.1)


def test_graph_rejects_invalid_edges() -> None:
    node = ClaimNode(id="root", text="Root", type="root")

    with pytest.raises(ValueError, match="unknown edge source"):
        QBAFGraph(
            root_id="root",
            nodes={"root": node},
            edges=[Edge(source_id="missing", target_id="root", polarity="support", weight=0.5)],
        )

    with pytest.raises(ValueError, match="weight must be between 0 and 1"):
        Edge(source_id="root", target_id="root", polarity="support", weight=2.0)
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_model.py -q
```

Expected: FAIL because `ClaimNode`, `Edge`, and `QBAFGraph` are not exported yet.

---

### Task 2: Add QBAF Model Implementation

**Files:**
- Create: `apps/dialectical-engine/coordinator/app/qbaf/model.py`
- Modify: `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`

- [x] **Step 1: Implement model dataclasses**

Create `apps/dialectical-engine/coordinator/app/qbaf/model.py`:

```python
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
```

- [x] **Step 2: Export model types**

Update `apps/dialectical-engine/coordinator/app/qbaf/__init__.py`:

```python
from __future__ import annotations

from app.qbaf.model import ClaimNode, Edge, QBAFGraph

FOUNDATION_STEP = "proposal-b-step-1"

__all__ = ["ClaimNode", "Edge", "FOUNDATION_STEP", "QBAFGraph"]
```

---

### Task 3: Run Step 3 Verification And Commit

**Files:**
- Verify all Step 3 files.

- [x] **Step 1: Run focused model tests**

Run:

```bash
cd apps/dialectical-engine/coordinator
PYTHONPYCACHEPREFIX=/private/tmp/dialectical-test-pycache \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
../.venv312/bin/python -m pytest -p pytest_asyncio.plugin tests/test_qbaf_model.py -q
```

Expected: all tests PASS.

- [x] **Step 2: Run full app tests**

Run:

```bash
cd apps/dialectical-engine
make test PYTHON=/Users/stefan.nour/Library/CloudStorage/OneDrive-adessoGroup/Debate/V4/apps/dialectical-engine/.venv312/bin/python
```

Expected: full tests PASS.

- [x] **Step 3: Review git diff**

Run:

```bash
git diff -- apps/dialectical-engine/coordinator/app/qbaf apps/dialectical-engine/coordinator/tests/test_qbaf_model.py docs/superpowers/plans/2026-06-14-qbaf-step-3-data-model.md
```

Expected: only Step 3 data-model changes appear.

- [x] **Step 4: Commit Step 3**

Run:

```bash
git add apps/dialectical-engine/coordinator/app/qbaf apps/dialectical-engine/coordinator/tests/test_qbaf_model.py docs/superpowers/plans/2026-06-14-qbaf-step-3-data-model.md
git commit -m "feat(step-3): add qbaf graph data model"
```

Expected: commit succeeds.
