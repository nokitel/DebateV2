from __future__ import annotations

import shutil
import subprocess

from app.providers.base import LLMResponse, ProviderError


class CodexCliProvider:
    name = "codex"

    def __init__(self, executable: str = "codex", timeout_seconds: int = 120) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def command(
        self,
        messages: list[dict],
        *,
        model: str,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> list[str]:
        prompt = self.prompt_from_messages(messages)
        if response_format == "json":
            prompt = f"{prompt}\n\nReturn only valid JSON."
        if max_tokens is not None:
            prompt = f"{prompt}\n\nKeep the answer under {max_tokens} tokens."
        return [
            self.executable,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--model",
            model,
            prompt,
        ]

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
        if shutil.which(self.executable) is None:
            raise ProviderError(f"Codex executable not found: {self.executable}")
        command = self.command(
            messages,
            model=model,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip() or "Codex command failed"
            raise ProviderError(error[:2_000])
        return LLMResponse(
            text=completed.stdout.strip(),
            raw={"provider": self.name, "returncode": completed.returncode, "stderr": completed.stderr},
            usage=None,
        )

    @staticmethod
    def prompt_from_messages(messages: list[dict]) -> str:
        parts: list[str] = []
        for message in messages:
            role = str(message.get("role", "user")).strip() or "user"
            content = str(message.get("content", ""))
            parts.append(f"{role.upper()}:\n{content}")
        return "\n\n".join(parts)
