---
id: verify-code-quality-claude
agent: claude
version: 0.2.0
memory_files_read: ["memory/guardrails.md", "memory/decisions/*.md"]
---

# Claude Code-quality Verifier

## Trigger description (used for routing)

Sub-issue Status=Verifying-Quality and config selects Claude or dual.

## When to use

Use for informational architecture/readability review after acceptance passed.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- PR diff
- Sub-issue body
- Relevant guardrails/decisions

## Workflow

1. Review architectural fit, naming clarity, simplicity, maintainability, observability, and adjacent-code implications.
2. Emit severity/category/file:line/suggestion per finding.
3. Do not block merge and do not change Status.

## Output format

`### Code-quality review (Claude)` using `ARTIFACTS.md` §7.

## Failure modes

- Diff too large: sample intentionally and state coverage partial.
- Skill failure: skipped comment only.

## Examples

Minor/readability: “progressMagic” obscures domain meaning; use “pointTotalDelta”.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
