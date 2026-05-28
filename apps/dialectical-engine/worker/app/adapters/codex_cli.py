from __future__ import annotations

from app.adapters.subprocess_base import SubprocessStreamingAdapter


class CodexCliAdapter(SubprocessStreamingAdapter):
    model_id = "codex-gpt-5"
    role_pool = {"decomposer", "proposer", "opponent", "synthesizer"}
    executable = "codex"

    def command(self, system: str, user: str, max_tokens: int) -> list[str]:
        prompt = f"{system}\n\n{user}\n\nKeep the answer under {max_tokens} tokens."
        return ["codex", "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", prompt]
