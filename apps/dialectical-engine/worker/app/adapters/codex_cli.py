from __future__ import annotations

import asyncio
import os
import shlex
import tempfile
import uuid
from pathlib import Path

from app.adapters.subprocess_base import SubprocessStreamingAdapter


ADAPTER_DIR = Path(__file__).resolve().parent
CODEX_V2_PLANNER_SCHEMA = ADAPTER_DIR / "codex_v2_planner.schema.json"
CODEX_V2_POV_SCHEMA = ADAPTER_DIR / "codex_v2_pov.schema.json"
CODEX_V2_AGENT_RUN_SCHEMA = ADAPTER_DIR / "codex_v2_agent_run.schema.json"
CODEX_V2_SYNTHESIS_SCHEMA = ADAPTER_DIR / "codex_v2_synthesis.schema.json"


def split_command(command: str) -> list[str]:
    posix = os.name != "nt" and "\\" not in command
    parts = shlex.split(command, posix=posix)
    if not posix:
        parts = [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in {"'", '"'} else part
            for part in parts
        ]
    return parts or ["codex"]


class CodexCliAdapter(SubprocessStreamingAdapter):
    model_id = "codex-gpt-5.5"
    cli_model = "gpt-5.5"
    role_pool = {"decomposer", "proposer", "opponent", "synthesizer"}
    executable = "codex"

    def __init__(self, command: str | None = None) -> None:
        self.command_prefix = split_command(command or os.getenv("CODEX_COMMAND", "codex"))
        self.executable = self.command_prefix[0]
        self._last_message_path: Path | None = None

    async def health_check(self) -> bool:
        if not await super().health_check():
            return False
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *self.command_prefix,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=10)
        except (OSError, asyncio.TimeoutError):
            if process is not None:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
            return False
        return process.returncode == 0

    def command(self, system: str, user: str, max_tokens: int) -> list[str]:
        self._last_message_path = Path(tempfile.gettempdir()) / f"dialectical-codex-last-message-{uuid.uuid4()}.json"
        command = [
            *self.command_prefix,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--output-last-message",
            str(self._last_message_path),
            "--model",
            self.cli_model,
            "-",
        ]
        schema = output_schema_for_prompt(system, user)
        if schema is not None:
            command[5:5] = ["--output-schema", str(schema)]
        return command

    def stdin_text(self, system: str, user: str, max_tokens: int) -> str:
        return f"{system}\n\n{user}\n\nKeep the answer under {max_tokens} tokens."

    def final_output_text(self) -> str | None:
        path = self._last_message_path
        if path is None or not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8").strip() or None
        finally:
            try:
                path.unlink()
            except OSError:
                pass


def output_schema_for_prompt(system: str, user: str) -> Path | None:
    text = f"{system}\n{user}"
    if "v2_plan" in text or ('"agents"' in text and '"skills"' in text):
        return CODEX_V2_PLANNER_SCHEMA
    if "v2_pov" in text or ('"strongest_pro"' in text and '"strongest_con"' in text and '"evidence_gaps"' not in text):
        return CODEX_V2_POV_SCHEMA
    if "v2_agent_run" in text or ('"pros"' in text and '"cons"' in text and "exactly five" in text.lower()):
        return CODEX_V2_AGENT_RUN_SCHEMA
    if "v2_synthesize" in text or '"evidence_gaps"' in text:
        return CODEX_V2_SYNTHESIS_SCHEMA
    return None
