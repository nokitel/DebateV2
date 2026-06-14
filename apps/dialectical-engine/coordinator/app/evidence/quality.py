from __future__ import annotations


QUALITY_MULTIPLIERS = {
    "high": 1.0,
    "moderate": 0.75,
    "low": 0.45,
    "very_low": 0.20,
}

QUALITY_CAVEATS = {
    "moderate": "Moderate quality evidence multiplier applied.",
    "low": "Low quality evidence multiplier applied.",
    "very_low": "Very low quality evidence multiplier applied.",
}


def quality_multiplier(grade: str) -> tuple[float, tuple[str, ...]]:
    normalized = grade.strip().lower()
    if normalized not in QUALITY_MULTIPLIERS:
        return 0.50, (f"Unknown quality grade: {grade}",)
    caveat = QUALITY_CAVEATS.get(normalized)
    return QUALITY_MULTIPLIERS[normalized], (caveat,) if caveat else ()
