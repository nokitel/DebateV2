from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.adapters.credentials import configured_api_key


class GeminiApiAdapter:
    model_id = "gemini-2.5-flash"
    role_pool = {"decomposer", "proposer", "opponent", "synthesizer"}

    async def health_check(self) -> bool:
        return configured_api_key("GEMINI_API_KEY") is not None

    async def stream(self, system: str, user: str, max_tokens: int) -> AsyncIterator[str]:
        api_key = configured_api_key("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set or is a placeholder")
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self.model_id}:streamGenerateContent?alt=sse"
        )
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if not data or data == "[DONE]":
                        continue
                    for chunk in self.text_chunks(json.loads(data)):
                        yield chunk

    @staticmethod
    def text_chunks(payload: object) -> list[str]:
        if isinstance(payload, list):
            chunks: list[str] = []
            for item in payload:
                chunks.extend(GeminiApiAdapter.text_chunks(item))
            return chunks
        if not isinstance(payload, dict):
            return []
        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            return []
        chunks = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return chunks
