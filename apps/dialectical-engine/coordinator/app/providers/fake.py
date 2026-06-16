from __future__ import annotations

from app.providers.base import LLMResponse

ResponseValue = str | list[str]


class FakeProvider:
    name = "fake"

    def __init__(self, responses: dict[str, ResponseValue] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict] = []
        self._response_indexes: dict[str, int] = {}

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
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": response_format,
                "role": role,
            }
        )
        key = role or model
        text = self._response_text(key, model)
        return LLMResponse(
            text=text,
            raw={"provider": self.name, "model": model, "role": role},
            usage={"tokens_out": len(text.split())},
        )

    def _response_text(self, key: str, model: str) -> str:
        response_key = key if key in self.responses else model if model in self.responses else key
        value = self.responses.get(response_key, "fake response")
        if isinstance(value, list):
            if not value:
                return ""
            index = self._response_indexes.get(response_key, 0)
            self._response_indexes[response_key] = index + 1
            return value[min(index, len(value) - 1)]
        return value
