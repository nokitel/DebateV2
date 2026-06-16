from __future__ import annotations

from dataclasses import replace

from app.evidence.entailment import classify_entailment
from app.evidence.model import EntailmentLabel, EvidenceScore, SourceRecord
from app.evidence.quality import quality_multiplier
from app.evidence.retraction import retraction_caveats
from app.qbaf import ClaimNode
from app.qbaf.model import require_non_empty, require_unit_interval


SUPPORT_BASE_SCORE = 0.85
NOINFO_SCORE = 0.05
REFUTES_SCORE = 0.05
RETRACTED_SCORE = 0.02
CORROBORATION_BOOST = 0.0125


class EvidenceValidationPipeline:
    def score_claim_source(self, claim: str, source: SourceRecord) -> EvidenceScore:
        clean_claim = require_non_empty(claim, "claim")
        entailment = classify_entailment(clean_claim, source.text)
        caveats: list[str] = []

        caveats.extend(retraction_caveats(source))
        if source.retracted:
            return EvidenceScore(
                reference=source.reference,
                base_score=RETRACTED_SCORE,
                uncertainty=1.0,
                entailment=entailment,
                caveats=tuple(caveats),
            )

        if entailment == EntailmentLabel.REFUTES:
            caveats.append("Source refutes the claim.")
            score = REFUTES_SCORE
        elif entailment == EntailmentLabel.NOINFO:
            caveats.append("Source does not contain information for the claim.")
            score = NOINFO_SCORE
        else:
            multiplier, quality_caveats = quality_multiplier(source.quality_grade)
            caveats.extend(quality_caveats)
            score = SUPPORT_BASE_SCORE * multiplier
            score = min(1.0, score + source.corroboration_count * CORROBORATION_BOOST)

        caveats.extend(_statistical_caveats(source))
        return EvidenceScore(
            reference=source.reference,
            base_score=require_unit_interval(score, "base_score"),
            uncertainty=_uncertainty(source, caveats),
            entailment=entailment,
            caveats=tuple(caveats),
        )

    def ground_leaf(self, node: ClaimNode, source: SourceRecord) -> ClaimNode:
        if node.type != "evidence_leaf":
            raise ValueError("ground_leaf requires an evidence_leaf node")
        score = self.score_claim_source(node.text, source)
        return replace(
            node,
            base_score=score.base_score,
            final_strength=score.base_score,
            uncertainty=score.uncertainty,
            status="grounded",
            caveats=list(score.caveats),
        )


def _statistical_caveats(source: SourceRecord) -> list[str]:
    return [f"Statistical red flag: {flag}" for flag in source.statistical_flags]


def _uncertainty(source: SourceRecord, caveats: list[str]) -> float:
    uncertainty = 0.10
    if source.quality_grade == "moderate":
        uncertainty += 0.15
    elif source.quality_grade == "low":
        uncertainty += 0.30
    elif source.quality_grade == "very_low":
        uncertainty += 0.50
    uncertainty += 0.05 * len(source.statistical_flags)
    if caveats:
        uncertainty += 0.10
    return require_unit_interval(min(1.0, uncertainty), "uncertainty")
