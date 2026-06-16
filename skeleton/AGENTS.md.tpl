# AGENTS.md — {{PROJECT_NAME}}

<!-- Template variables: PROJECT_NAME, CANONICAL_COMMANDS, ARCHITECTURE_BOUNDARIES -->

## Project purpose

{{PROJECT_NAME}}

## Canonical commands

{{CANONICAL_COMMANDS}}

## Architecture boundaries

{{ARCHITECTURE_BOUNDARIES}}

## Safety invariants

- Never edit `memory/` files directly during a slice; use the lessons flow.
- Never write outside the worktree directory.
- Never assume the host network is reachable from a container.
- Any decision contradicting an existing ADR must cite it explicitly.
- Status is canonical state; labels are attributes only.

## Definition of done

A task is not done without:

- files changed
- commands run
- command results
- skipped checks with reasons
- remaining risks
- evidence links or logs

## Links

- `ARTIFACTS.md` — schemas and artifact contracts
- `.claude/CLAUDE.md` — Claude-specific addendum
- `.codex/CODEX.md` — Codex-specific addendum
- `memory/README.md` — memory discipline
- `prompts/shared/` — reusable prompt contracts
- `.harness/config.yml` — project harness configuration
