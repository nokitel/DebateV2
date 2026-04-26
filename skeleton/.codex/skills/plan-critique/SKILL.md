---
id: plan-critique
agent: codex
version: 0.2.0
memory_files_read: ["memory/mistakes.md", "memory/guardrails.md", "memory/decisions/*.md"]
---

# Phase B Plan Critique

## Trigger description (used for routing)

Parent issue Status=Plan Ready.

## When to use

Use for clean-slate critique of finalized issue body. This is deliberately not collaborative memory of Phase A.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Final issue body only
- `memory/mistakes.md`, `memory/guardrails.md`, relevant decisions
- Repository snapshot if needed for feasibility checks

## Workflow

1. Read issue body as if you did not participate earlier.
2. Check gaps, risks, improvements, observability, UX, license/dependency risk.
3. Pay special attention to acceptance criteria testability and slice boundaries.
4. Classify every finding: critical, major, minor.
5. Do not rewrite the plan; produce critique only.

## Output format

Use `ARTIFACTS.md` §6 Phase B critique template.

## Failure modes

- Plan missing: mark critical blocker.
- Repo unavailable: critique artifact quality only and state coverage partial.

## Examples

Finding: major/observability — export failures have no user-visible error or log context, making support impossible.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
