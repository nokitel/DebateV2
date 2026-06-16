from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx


DEFAULT_LM_STUDIO_URL = "http://127.0.0.1:1234"


class LMStudioAdapter:
    role_pool = {"decomposer", "proposer", "opponent", "synthesizer"}

    def __init__(self, model_name: str, base_url: str | None = None) -> None:
        self.model_name = model_name
        self.model_id = f"lmstudio:{model_name}"
        self.base_url = (base_url or os.getenv("DIALECTICAL_LMSTUDIO_URL") or DEFAULT_LM_STUDIO_URL).rstrip("/")

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.base_url}/v1/models")
                response.raise_for_status()
                models = response.json().get("data", [])
                return any(model.get("id") == self.model_name for model in models if isinstance(model, dict))
        except Exception:
            return False

    async def stream(self, system: str, user: str, max_tokens: int) -> AsyncIterator[str]:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if content:
                yield str(content)
