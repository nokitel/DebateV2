# CODEX.md — {{PROJECT_NAME}}

Read `AGENTS.md` and `ARTIFACTS.md` first.

You are usually invoked headlessly by the runner; output is parsed mechanically. Avoid conversational filler.

Assumptions:
- You work in an isolated worktree mounted at `/workspace`.
- Host network is unreachable.
- Outbound internet may be available for dependencies and model APIs.
- Evidence is mandatory before claiming completion.
