from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator


class SubprocessStreamingAdapter:
    model_id: str
    role_pool: set[str]
    executable: str

    def command(self, system: str, user: str, max_tokens: int) -> list[str]:
        raise NotImplementedError

    def stdin_text(self, system: str, user: str, max_tokens: int) -> str | None:
        return None

    def final_output_text(self) -> str | None:
        return None

    def env(self) -> dict[str, str] | None:
        return None

    async def health_check(self) -> bool:
        return shutil.which(self.executable) is not None or os.path.isfile(self.executable)

    async def stream(self, system: str, user: str, max_tokens: int) -> AsyncIterator[str]:
        stdin_text = self.stdin_text(system, user, max_tokens)
        process = await asyncio.create_subprocess_exec(
            *self.command(system, user, max_tokens),
            stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **extra_env} if (extra_env := self.env()) else None,
        )
        if stdin_text is not None:
            assert process.stdin is not None
            process.stdin.write(stdin_text.encode())
            await process.stdin.drain()
            process.stdin.close()
        assert process.stdout is not None
        emitted_output = False
        async for raw_line in process.stdout:
            text = self.parse_stdout_line(raw_line.decode(errors="replace"))
            if text:
                emitted_output = True
                yield text
        stderr = await process.stderr.read() if process.stderr else b""
        code = await process.wait()
        if code != 0:
            raise RuntimeError(stderr.decode(errors="replace") or f"{self.executable} exited with {code}")
        if not emitted_output:
            final_text = self.final_output_text()
            if final_text:
                yield final_text
                return
            stderr_text = stderr.decode(errors="replace").strip()
            if stderr_text:
                raise RuntimeError(stderr_text)
            raise RuntimeError(f"{self.executable} produced no output")

    def parse_stdout_line(self, line: str) -> str:
        return line


def claude_stream_json_delta(line: str) -> str:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return line
    if isinstance(payload, dict):
        if payload.get("type") == "content_block_delta":
            delta = payload.get("delta", {})
            return str(delta.get("text", ""))
        if "completion" in payload:
            return str(payload["completion"])
    return ""
