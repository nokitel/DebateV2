from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import load_settings
from app.core.write_lock import commit_write, flush_write
from app.models.entities import Debate, Generation, Node, Worker, now_utc
from app.services.orchestrator import sanitize_text
from app.services.serialization import iso

SINGLE_SHOT_MODE = "single_shot"
OPENAI_WORKER_NAME = "openai-single-shot"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
PROMPT_VERSION = "single-shot-openai-v1"
ROOT = Path(__file__).resolve().parents[3]


class GlobalWinner(BaseModel):
    side: Literal["pro", "con", "balanced"]
    reason: str = Field(min_length=1, max_length=2_000)


class DebateGenerationResult(BaseModel):
    root_claim: str = Field(min_length=3, max_length=2_000)
    pros: list[str] = Field(min_length=3, max_length=7)
    cons: list[str] = Field(min_length=3, max_length=7)
    strongest_pro: str = Field(min_length=1, max_length=2_000)
    strongest_con: str = Field(min_length=1, max_length=2_000)
    global_winner: GlobalWinner
    final_text: str = Field(min_length=1, max_length=8_000)
    model_id: str = Field(min_length=1, max_length=200)
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    created_at: str

    @field_validator("pros", "cons")
    @classmethod
    def clean_arguments(cls, values: list[str]) -> list[str]:
        cleaned = [sanitize_text(value, 2_000) for value in values]
        if any(not value for value in cleaned):
            raise ValueError("arguments cannot be empty")
        return cleaned

    @field_validator("global_winner", mode="before")
    @classmethod
    def normalize_global_winner(cls, value: Any) -> Any:
        if isinstance(value, str):
            side = value.strip().lower()
            side = {"pros": "pro", "pro": "pro", "cons": "con", "con": "con"}.get(side, side)
            if side in {"pro", "con", "balanced"}:
                return {"side": side, "reason": f"Codex selected {side} as the global winner."}
        return value

    @model_validator(mode="after")
    def strongest_arguments_must_match(self) -> "DebateGenerationResult":
        if self.strongest_pro not in self.pros:
            raise ValueError("strongest_pro must be one of pros")
        if self.strongest_con not in self.cons:
            raise ValueError("strongest_con must be one of cons")
        return self


def response_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "single_shot_debate",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "root_claim",
                "pros",
                "cons",
                "strongest_pro",
                "strongest_con",
                "global_winner",
                "final_text",
            ],
            "properties": {
                "root_claim": {"type": "string"},
                "pros": {"type": "array", "minItems": 3, "maxItems": 7, "items": {"type": "string"}},
                "cons": {"type": "array", "minItems": 3, "maxItems": 7, "items": {"type": "string"}},
                "strongest_pro": {"type": "string"},
                "strongest_con": {"type": "string"},
                "global_winner": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["side", "reason"],
                    "properties": {
                        "side": {"type": "string", "enum": ["pro", "con", "balanced"]},
                        "reason": {"type": "string"},
                    },
                },
                "final_text": {"type": "string"},
            },
        },
    }


def system_prompt() -> str:
    return (
        "You generate neutral, factual debate maps. Treat the user's text as the root claim exactly. "
        "Return scientifically cautious arguments, avoid advocacy, avoid invented statistics, and mention uncertainty "
        "when evidence would depend on local context. Choose between 3 and 7 pros and between 3 and 7 cons. "
        "The strongest_pro must exactly match one pro. The strongest_con must exactly match one con. "
        "The global winner is the side with the stronger current evidence; use balanced when neither side is stronger."
    )


def codex_prompt(topic: str) -> str:
    return (
        f"{system_prompt()}\n\n"
        "Return only one JSON object with these keys: root_claim, pros, cons, strongest_pro, "
        "strongest_con, global_winner, final_text. Do not include markdown fences.\n\n"
        f"Root claim:\n{topic}"
    )


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Codex response did not include a JSON object") from None
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Generated response JSON must be an object")
    return parsed


def extract_response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    for output in payload.get("output") or []:
        if not isinstance(output, dict):
            continue
        for content in output.get("content") or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return content["text"]
    raise ValueError("OpenAI response did not include text output")


def usage_tokens(payload: dict[str, Any]) -> tuple[int, int]:
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    tokens_in = usage.get("input_tokens", 0)
    tokens_out = usage.get("output_tokens", 0)
    return int(tokens_in or 0), int(tokens_out or 0)


def validate_single_shot_result(raw: dict[str, Any], *, model_id: str, tokens_in: int, tokens_out: int) -> DebateGenerationResult:
    enriched = {
        **raw,
        "model_id": model_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "created_at": iso(now_utc()),
    }
    return DebateGenerationResult.model_validate(enriched)


class OpenAIDebateGenerator:
    def __init__(self, *, api_key: str | None = None, model_id: str | None = None, timeout_seconds: int = 90) -> None:
        settings = load_settings()
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model_id = model_id or settings.openai_model
        self.timeout_seconds = timeout_seconds

    def __call__(self, topic: str) -> DebateGenerationResult:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for single-shot debate generation")
        request_payload = {
            "model": self.model_id,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt()}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": topic}],
                },
            ],
            "text": {"format": response_schema()},
        }
        with httpx.Client() as client:
            response = client.post(
                OPENAI_RESPONSES_URL,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=request_payload,
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
        raw = json.loads(extract_response_text(payload))
        if not isinstance(raw, dict):
            raise ValueError("OpenAI response JSON must be an object")
        tokens_in, tokens_out = usage_tokens(payload)
        return validate_single_shot_result(raw, model_id=self.model_id, tokens_in=tokens_in, tokens_out=tokens_out)


class CodexCliDebateGenerator:
    def __init__(self, *, command: str | None = None, timeout_seconds: int = 180) -> None:
        settings = load_settings()
        self.command = command or settings.codex_command
        self.timeout_seconds = timeout_seconds
        self.model_id = "codex-cli"

    def __call__(self, topic: str) -> DebateGenerationResult:
        prompt = codex_prompt(topic)
        command = Path(self.command)
        executable = str(command if command.is_absolute() or command.parent == Path(".") else ROOT / command)
        completed = subprocess.run(
            [
                executable,
                "exec",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "-",
            ],
            cwd=ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=True,
        )
        raw = extract_json_object(completed.stdout)
        return validate_single_shot_result(
            raw,
            model_id=self.model_id,
            tokens_in=max(1, len(prompt.split())),
            tokens_out=max(1, len(completed.stdout.split())),
        )


def configured_single_shot_generator() -> Callable[[str], DebateGenerationResult]:
    settings = load_settings()
    if settings.single_shot_provider == "openai":
        return OpenAIDebateGenerator(api_key=settings.openai_api_key, model_id=settings.openai_model)
    if settings.single_shot_provider == "codex":
        return CodexCliDebateGenerator(command=settings.codex_command)
    raise RuntimeError("DIALECTICAL_SINGLE_SHOT_PROVIDER must be 'codex' or 'openai'")


def single_shot_worker(db: Session, model_id: str) -> Worker:
    worker = db.scalar(select(Worker).where(Worker.name == OPENAI_WORKER_NAME))
    if worker:
        worker.capabilities = [model_id]
        worker.last_seen = now_utc()
        worker.status = "online"
        return worker
    worker = Worker(
        name=OPENAI_WORKER_NAME,
        token_hash="internal-openai-single-shot-worker",
        capabilities=[model_id],
        last_seen=now_utc(),
        status="online",
    )
    db.add(worker)
    flush_write(db)
    return worker


def add_generated_node(
    db: Session,
    *,
    debate: Debate,
    root: Node,
    worker: Worker,
    model_id: str,
    node_type: str,
    position: int,
    claim: str,
) -> None:
    child = Node(
        debate_id=debate.id,
        parent_id=root.id,
        node_type=node_type,
        depth=1,
        position=position,
        claim=claim,
        status="complete",
        materialized_path=f"{root.materialized_path}/{position}",
    )
    db.add(child)
    flush_write(db)
    generation = Generation(
        node_id=child.id,
        model_id=model_id,
        role="proposer" if node_type == "PRO" else "opponent",
        argument=claim,
        prompt_version=PROMPT_VERSION,
        prompt_rendered=debate.topic,
        tokens_in=debate.config["single_shot_result"]["tokens_in"],
        tokens_out=max(1, len(claim.split())),
        latency_ms=0,
        is_active=True,
        worker_id=worker.id,
    )
    db.add(generation)
    flush_write(db)
    child.active_generation_id = generation.id


def create_single_shot_debate(
    db: Session,
    topic: str,
    *,
    generator: Callable[[str], DebateGenerationResult] | None = None,
) -> Debate:
    topic = sanitize_text(topic, 2_000)
    if not topic:
        raise ValueError("Topic is required")
    generator = generator or OpenAIDebateGenerator()
    result = generator(topic)
    result_payload = result.model_dump()
    debate = Debate(
        topic=topic,
        status="complete",
        config={"mode": SINGLE_SHOT_MODE, "single_shot_result": result_payload},
        completed_at=now_utc(),
    )
    db.add(debate)
    flush_write(db)
    root = Node(
        debate_id=debate.id,
        parent_id=None,
        node_type="ROOT_CLAIM",
        depth=0,
        position=0,
        claim=topic,
        status="complete",
        materialized_path="/0",
    )
    db.add(root)
    flush_write(db)
    debate.root_node_id = root.id
    worker = single_shot_worker(db, result.model_id)
    for index, claim in enumerate(result.pros):
        add_generated_node(
            db,
            debate=debate,
            root=root,
            worker=worker,
            model_id=result.model_id,
            node_type="PRO",
            position=index,
            claim=claim,
        )
    for index, claim in enumerate(result.cons, start=len(result.pros)):
        add_generated_node(
            db,
            debate=debate,
            root=root,
            worker=worker,
            model_id=result.model_id,
            node_type="CON",
            position=index,
            claim=claim,
        )
    commit_write(db)
    db.refresh(debate)
    return debate
