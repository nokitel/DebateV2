from __future__ import annotations

import asyncio
import re

from app.adapters.subprocess_base import SubprocessStreamingAdapter

PROMPT_FLAG_PATTERN = re.compile(r"(?<!\S)(?:-p|--prompt)(?:[=\s,]|$)")


class GrokCliAdapter(SubprocessStreamingAdapter):
    model_id = "grok-4"
    role_pool = {"proposer", "opponent"}
    executable = "grok"

    async def health_check(self) -> bool:
        if not await super().health_check():
            return False
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
        except (OSError, asyncio.TimeoutError):
            if process is not None:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
            return False

        if process.returncode != 0:
            return False
        help_text = (stdout + stderr).decode(errors="replace")
        return bool(PROMPT_FLAG_PATTERN.search(help_text))

    def command(self, system: str, user: str, max_tokens: int) -> list[str]:
        prompt = f"{system}\n\n{user}\n\nMaximum tokens: {max_tokens}"
        return ["grok", "-p", prompt]
