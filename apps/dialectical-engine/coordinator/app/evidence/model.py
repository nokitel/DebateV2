from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.qbaf.model import require_non_empty, require_unit_interval


class EntailmentLabel(str, Enum):
    SUPPORTS = "SUPPORTS"
    REFUTES = "REFUTES"
    NOINFO = "NOINFO"


@dataclass(frozen=True)
class SourceRecord:
    reference: str
    text: str
    title: str = ""
    retracted: bool = False
    quality_grade: str = "moderate"
    corroboration_count: int = 0
    statistical_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", require_non_empty(self.reference, "reference"))
        object.__setattr__(self, "text", require_non_empty(self.text, "text"))
        object.__setattr__(self, "title", str(self.title).strip())
        object.__setattr__(self, "quality_grade", require_non_empty(self.quality_grade, "quality_grade").lower())
        if self.corroboration_count < 0:
            raise ValueError("corroboration_count cannot be negative")
        object.__setattr__(self, "corroboration_count", int(self.corroboration_count))
        object.__setattr__(self, "statistical_flags", [str(flag) for flag in self.statistical_flags])


@dataclass(frozen=True)
class EvidenceScore:
    reference: str
    base_score: float
    uncertainty: float
    entailment: EntailmentLabel
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", require_non_empty(self.reference, "reference"))
        object.__setattr__(self, "base_score", require_unit_interval(float(self.base_score), "base_score"))
        object.__setattr__(self, "uncertainty", require_unit_interval(float(self.uncertainty), "uncertainty"))
        object.__setattr__(self, "caveats", tuple(str(caveat) for caveat in self.caveats))
