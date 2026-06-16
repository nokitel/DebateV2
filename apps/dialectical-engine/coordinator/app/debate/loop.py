from __future__ import annotations

import json
from dataclasses import dataclass, replace
from json import JSONDecodeError
from typing import Any

from app.evidence import EvidenceValidationStub
from app.providers import ProviderRegistry
from app.qbaf import ClaimNode
from app.qbaf.model import require_non_empty, require_unit_interval
from app.scoring import parse_score_sample


@dataclass(frozen=True)
class DebateTurn:
    role: str
    argument: str
    score: float
    evidence: tuple[str, ...]
    round_index: int
    evidence_checks: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "argument": self.argument,
            "score": self.score,
            "evidence": list(self.evidence),
            "round_index": self.round_index,
            "evidence_checks": [dict(check) for check in self.evidence_checks],
        }


@dataclass(frozen=True)
class DebateResult:
    node: ClaimNode
    edge_weight: float


class TwoDebaterJudgeLoop:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        rounds: int = 1,
        evidence: EvidenceValidationStub | None = None,
    ) -> None:
        if rounds < 1:
            raise ValueError("rounds must be at least 1")
        self.registry = registry
        self.rounds = rounds
        self.evidence = evidence or EvidenceValidationStub()

    def score_node(self, node: ClaimNode) -> DebateResult:
        transcript: list[dict[str, object]] = []
        debater_scores: list[float] = []
        for round_index in range(self.rounds):
            for role, stance in (
                ("proponent", "higher trustworthiness"),
                ("opponent", "lower trustworthiness"),
            ):
                turn = self._run_debater(node, role, stance, round_index, transcript)
                transcript.append(turn.to_dict())
                debater_scores.append(turn.score)

        judge_sample = parse_score_sample(
            self.registry.generate_for_role(
                "judge",
                self._judge_messages(node, transcript),
                response_format="json",
            ).text
        )
        uncertainty = max(debater_scores) - min(debater_scores) if debater_scores else 0.0
        judge_turn = {
            "role": "judge",
            "base_score": judge_sample.base_score,
            "edge_weight": judge_sample.edge_weight,
            "rationale": judge_sample.rationale,
        }
        transcript.append(judge_turn)

        updated_node = replace(
            node,
            base_score=judge_sample.base_score,
            final_strength=judge_sample.base_score,
            uncertainty=require_unit_interval(uncertainty, "uncertainty"),
            status="debated",
            transcript=transcript,
        )
        return DebateResult(node=updated_node, edge_weight=judge_sample.edge_weight)

    def _run_debater(
        self,
        node: ClaimNode,
        role: str,
        stance: str,
        round_index: int,
        transcript: list[dict[str, object]],
    ) -> DebateTurn:
        response = self.registry.generate_for_role(
            role,
            self._debater_messages(node, stance, round_index, transcript),
            response_format="json",
        )
        return parse_debate_turn(
            response.text,
            role=role,
            round_index=round_index,
            evidence=self.evidence,
        )

    def _debater_messages(
        self,
        node: ClaimNode,
        stance: str,
        round_index: int,
        transcript: list[dict[str, object]],
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    f"Argue for {stance} of the claim. "
                    "Return only JSON with argument, score, and evidence."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Claim:\n{node.text}\n"
                    f"Round: {round_index + 1} of {self.rounds}\n"
                    f"Prior anonymous turns:\n{_format_anonymous_turns(transcript)}"
                ),
            },
        ]

    def _judge_messages(
        self,
        node: ClaimNode,
        transcript: list[dict[str, object]],
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "Judge the claim after anonymous debate. Return only JSON "
                    "with base_score, edge_weight, and rationale."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Claim:\n{node.text}\n"
                    f"Anonymous debate transcript:\n{_format_anonymous_turns(transcript)}"
                ),
            },
        ]


def parse_debate_turn(
    payload: str,
    *,
    role: str,
    round_index: int,
    evidence: EvidenceValidationStub,
) -> DebateTurn:
    try:
        raw = json.loads(payload)
    except JSONDecodeError as exc:
        raise ValueError("debater response must be valid JSON") from exc

    if not isinstance(raw, dict):
        raise ValueError("debater response JSON must be an object")

    argument = require_non_empty(str(raw.get("argument", "")), "argument")
    score = require_unit_interval(_required_float(raw, "score"), "score")
    references = _required_evidence(raw)
    checks = tuple(check.to_dict() for check in evidence.validate_references(references))
    return DebateTurn(
        role=role,
        argument=argument,
        score=score,
        evidence=tuple(references),
        round_index=round_index,
        evidence_checks=checks,
    )


def anonymize_transcript(transcript: list[dict[str, object]]) -> list[dict[str, object]]:
    anonymized = []
    for turn in transcript:
        clean_turn = {key: value for key, value in turn.items() if key != "role"}
        anonymized.append(clean_turn)
    return anonymized


def _format_anonymous_turns(transcript: list[dict[str, object]]) -> str:
    anonymous = anonymize_transcript(transcript)
    if not anonymous:
        return "None yet."
    return "\n".join(json.dumps(turn, sort_keys=True) for turn in anonymous)


def _required_float(raw: dict[str, Any], key: str) -> float:
    value = raw.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric") from exc


def _required_evidence(raw: dict[str, Any]) -> list[str]:
    evidence = raw.get("evidence", raw.get("citations"))
    if not isinstance(evidence, list):
        raise ValueError("evidence must be a non-empty list")
    references = [require_non_empty(str(reference), "evidence") for reference in evidence]
    if not references:
        raise ValueError("evidence must be a non-empty list")
    return references
