from __future__ import annotations

import os

import httpx

from app.adapters import (
    ClaudeCliAdapter,
    CodexCliAdapter,
    GeminiApiAdapter,
    GeminiCliAdapter,
    GrokCliAdapter,
    LMStudioAdapter,
    MockAdapter,
    ModelClient,
    OllamaAdapter,
    XaiApiAdapter,
)
from app.config import WorkerConfig


async def discover_ollama_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get("http://localhost:11434/api/tags")
            response.raise_for_status()
            return [model["name"] for model in response.json().get("models", []) if model.get("name")]
    except Exception:
        return []


def configured_lm_studio_models() -> list[str]:
    raw = os.getenv("DIALECTICAL_LMSTUDIO_MODELS", "google_gemma-4-e4b-it")
    models: list[str] = []
    seen: set[str] = set()
    for candidate in raw.split(","):
        model = candidate.strip()
        if model and model not in seen:
            models.append(model)
            seen.add(model)
    return models


async def detect_adapters(config: WorkerConfig) -> dict[str, ModelClient]:
    candidates: list[ModelClient] = []
    allowed_models = set(config.allowed_models or [])
    if config.enable_mock:
        for model_id in config.mock_models or ["mock-local"]:
            candidates.append(MockAdapter(model_id))
    if config.enable_real_adapters:
        candidates.extend(
            [
                ClaudeCliAdapter(),
                CodexCliAdapter(),
                GeminiApiAdapter(),
                GeminiCliAdapter(),
                GrokCliAdapter(),
                XaiApiAdapter(),
            ]
        )
        candidates.extend(LMStudioAdapter(model_name) for model_name in configured_lm_studio_models())
        for model_name in await discover_ollama_models():
            candidates.append(OllamaAdapter(model_name))

    adapters: dict[str, ModelClient] = {}
    for adapter in candidates:
        if allowed_models and adapter.model_id not in allowed_models:
            continue
        if adapter.model_id in adapters:
            continue
        try:
            healthy = await adapter.health_check()
        except Exception:
            healthy = False
        if healthy:
            adapters[adapter.model_id] = adapter
    return adapters
