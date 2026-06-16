from __future__ import annotations

from app.evidence.model import SourceRecord


def retraction_caveats(source: SourceRecord) -> tuple[str, ...]:
    if source.retracted:
        return ("Source is retracted.",)
    return ()
