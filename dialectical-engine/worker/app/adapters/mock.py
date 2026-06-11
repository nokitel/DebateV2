from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator


class MockAdapter:
    role_pool = {"decomposer", "proposer", "opponent", "synthesizer"}

    def __init__(self, model_id: str = "mock-local", token_delay_seconds: float | None = None) -> None:
        self.model_id = model_id
        self.token_delay_seconds = (
            token_delay_seconds
            if token_delay_seconds is not None
            else float(os.getenv("DIALECTICAL_MOCK_TOKEN_DELAY_SECONDS", "0.01"))
        )

    async def health_check(self) -> bool:
        return True

    async def stream(self, system: str, user: str, max_tokens: int) -> AsyncIterator[str]:
        del max_tokens
        output = self.generate(system, user)
        for token in output.split(" "):
            await asyncio.sleep(self.token_delay_seconds)
            yield token + " "

    def generate(self, system: str, user: str) -> str:
        claim = self._tag(user, "claim") or self._tag(user, "topic") or "the topic"
        topic = self._tag(user, "topic") or claim
        lower = system.lower()
        if ("strict json" in lower or "json only" in lower) and "children" in lower:
            return json.dumps(
                {
                    "root_claim": topic,
                    "argument": "The topic is decomposed into initial supporting and opposing lines.",
                    "children": [
                        {"node_type": "PRO", "claim": f"The strongest reason to accept '{topic}' is its expected public benefit."},
                        {"node_type": "CON", "claim": f"The strongest reason to reject '{topic}' is the risk of costly side effects."},
                    ],
                }
            )
        if "synthes" in lower:
            return json.dumps(
                {
                    "strongest_pro": "The pro side identifies concrete benefits and a path to implementation.",
                    "strongest_con": "The con side raises transition costs, enforcement limits, and uncertainty.",
                    "verdict": "The better position depends on whether safeguards and transition support are credible.",
                }
            )
        if "opposing" in lower or "opponent" in lower:
            return f"This objection challenges '{claim}' by pointing to tradeoffs, enforcement gaps, and unintended consequences."
        return f"This support for '{claim}' argues that the claimed benefit is plausible, actionable, and measurable."

    @staticmethod
    def _tag(text: str, tag: str) -> str | None:
        match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, flags=re.DOTALL)
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else None
