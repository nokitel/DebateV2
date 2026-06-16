---
id: verify-code-quality-codex
agent: codex
version: 0.2.0
memory_files_read: ["memory/guardrails.md", "memory/decisions/*.md"]
---

# Codex Code-quality Verifier

## Trigger description (used for routing)

Sub-issue Status=Verifying-Quality and config selects Codex or dual.

## When to use

Use for informational structural/static-flavored review after acceptance passed.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- PR diff
- Sub-issue body
- Relevant guardrails/decisions

## Workflow

1. Review coupling, dead code, leaky abstractions, dependency hygiene, test depth, error handling, strict static-analysis concerns.
2. Emit severity/category/file:line/suggestion per finding.
3. Do not change Status. Findings are informational.

## Output format

`### Code-quality review (Codex)` using `ARTIFACTS.md` §7.

## Failure modes

- Large binary diff: mark coverage partial.
- Tool failure: comment skipped; do not block.

## Examples

Major/coupling: route imports test fixture generator in production code; suggest moving conversion into domain utility.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
