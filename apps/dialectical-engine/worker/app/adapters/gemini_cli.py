from __future__ import annotations

import asyncio
import os

from app.adapters.subprocess_base import SubprocessStreamingAdapter


GOOGLE_ACCOUNT_AUTH_ENV = {"GOOGLE_GENAI_USE_GCA": "true"}


class GeminiCliAdapter(SubprocessStreamingAdapter):
    model_id = "gemini-2.5-pro"
    role_pool = {"decomposer", "proposer", "opponent", "synthesizer"}
    executable = "gemini"

    def env(self) -> dict[str, str]:
        return GOOGLE_ACCOUNT_AUTH_ENV

    async def health_check(self) -> bool:
        if not await super().health_check():
            return False
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                "gemini",
                "-p",
                "Respond with exactly OK.",
                "--output-format",
                "text",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **GOOGLE_ACCOUNT_AUTH_ENV},
            )
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except (OSError, asyncio.TimeoutError):
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            return False
        return process.returncode == 0 and bool(stdout.strip())

    def command(self, system: str, user: str, max_tokens: int) -> list[str]:
        prompt = f"{system}\n\n{user}\n\nMaximum tokens: {max_tokens}"
        return ["gemini", "-p", prompt]
