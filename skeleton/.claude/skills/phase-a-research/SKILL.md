---
id: phase-a-research-claude
agent: claude
version: 0.2.0
memory_files_read: ["memory/decisions/*.md", "memory/glossary.md", "memory/guardrails.md"]
---

# Claude Phase A Research

## Trigger description (used for routing)

Status moves to Researching. Runs in parallel with Codex Phase A and is blind to Codex output.

## When to use

Use for broad product/architecture research from the raw brief before questions are asked.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Raw issue brief
- Repository snapshot
- `memory/decisions/*.md`, `memory/glossary.md`, `memory/guardrails.md` scoped by obvious tags

## Workflow

1. Preserve the raw brief; do not pretend it is already a spec.
2. Explore product intent, user value, likely edge cases, and architectural seams.
3. Identify decisions that are actually questions.
4. Call out assumptions and confidence.
5. Write narrative findings, not a checklist.
6. Do not read Codex Phase A output.

## Output format

Use `ARTIFACTS.md` §5 Phase A research template.

## Failure modes

- Ambiguous brief: list concrete ambiguity and suggested clarifying question.
- Memory contradiction: cite decision and recommend reconcile before planning.
- Repo unavailable: produce product-only research and mark confidence low.

## Examples

Brief: “add gamification.” Output identifies retroactive points, idempotency, streak timezone, no-notifications scope, and dashboard visibility as likely questions.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
