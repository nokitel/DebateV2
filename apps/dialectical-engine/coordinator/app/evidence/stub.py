from __future__ import annotations

from dataclasses import dataclass

from app.qbaf.model import require_non_empty


@dataclass(frozen=True)
class EvidenceCheck:
    reference: str
    status: str = "pending_step_8"
    caveats: tuple[str, ...] = ("Evidence validation is pending Step 8.",)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", require_non_empty(self.reference, "reference"))

    def to_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "status": self.status,
            "caveats": list(self.caveats),
        }


class EvidenceValidationStub:
    def validate_references(self, references: list[str]) -> list[EvidenceCheck]:
        return [EvidenceCheck(reference=reference) for reference in references]
