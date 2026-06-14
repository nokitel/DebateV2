from __future__ import annotations

from app.providers.base import LLMResponse


class FakeProvider:
    name = "fake"

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}

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
        key = role or model
        text = self.responses.get(key, self.responses.get(model, "fake response"))
        return LLMResponse(
            text=text,
            raw={"provider": self.name, "model": model, "role": role},
            usage={"tokens_out": len(text.split())},
        )
