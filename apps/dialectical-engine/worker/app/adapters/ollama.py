from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx


class OllamaAdapter:
    role_pool = {"proposer", "opponent", "synthesizer"}

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.model_id = f"ollama:{model_name.split(':')[0]}"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get("http://localhost:11434/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                return any(model.get("name", "").split(":")[0] == self.model_name.split(":")[0] for model in models)
        except Exception:
            return False

    async def stream(self, system: str, user: str, max_tokens: int) -> AsyncIterator[str]:
        prompt = f"{system}\n\n{user}"
        payload = {"model": self.model_name, "prompt": prompt, "stream": True, "options": {"num_predict": max_tokens}}
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", "http://localhost:11434/api/generate", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    delta = chunk.get("response", "")
                    if delta:
                        yield delta
