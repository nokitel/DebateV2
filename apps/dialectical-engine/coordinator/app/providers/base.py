from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMResponse:
    text: str
    raw: dict
    usage: dict | None


class ProviderError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def generate(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str | None = None,
        role: str | None = None,
    ) -> LLMResponse:
        ...
