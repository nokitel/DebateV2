from __future__ import annotations

import re

from app.evidence.model import EntailmentLabel
from app.qbaf.model import require_non_empty


REFUTE_MARKERS = (
    "does not support",
    "no association",
    "refute",
    "refutes",
    "refuted",
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "is",
    "of",
    "the",
    "to",
}

TOKEN_RE = re.compile(r"[a-z0-9]+")


def classify_entailment(claim: str, source_text: str) -> EntailmentLabel:
    claim_text = require_non_empty(claim, "claim")
    evidence_text = require_non_empty(source_text, "source_text")
    lowered_source = evidence_text.lower()
    if any(marker in lowered_source for marker in REFUTE_MARKERS):
        return EntailmentLabel.REFUTES

    claim_tokens = _content_tokens(claim_text)
    source_tokens = _content_tokens(evidence_text)
    if not claim_tokens:
        return EntailmentLabel.NOINFO

    overlap = len(claim_tokens & source_tokens) / len(claim_tokens)
    if overlap >= 0.5:
        return EntailmentLabel.SUPPORTS
    return EntailmentLabel.NOINFO


def _content_tokens(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS}
