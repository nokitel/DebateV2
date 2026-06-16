from __future__ import annotations

from app.adapters.subprocess_base import SubprocessStreamingAdapter, claude_stream_json_delta


class ClaudeCliAdapter(SubprocessStreamingAdapter):
    model_id = "claude-sonnet-4-6"
    role_pool = {"decomposer", "proposer", "opponent", "synthesizer"}
    executable = "claude"

    def command(self, system: str, user: str, max_tokens: int) -> list[str]:
        prompt = f"{system}\n\n{user}"
        return ["claude", "-p", prompt, "--model", self.model_id, "--output-format", "stream-json", "--verbose"]

    def parse_stdout_line(self, line: str) -> str:
        return claude_stream_json_delta(line)
