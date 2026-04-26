---
id: phase-a-research-codex
agent: codex
version: 0.2.0
memory_files_read: ["memory/decisions/*.md", "memory/guardrails.md"]
---

# Codex Phase A Research

## Trigger description (used for routing)

Status moves to Researching. Runs in parallel with Claude Phase A and is blind to Claude output.

## When to use

Use for codebase-oriented discovery: modules, commands, tests, data models, dependencies, and integration risk.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Raw issue brief
- Fresh checkout/worktree
- Canonical commands from `AGENTS.md`
- Relevant `memory/decisions/*.md` and `memory/guardrails.md`

## Workflow

1. Read `AGENTS.md` and canonical commands.
2. Map likely files/modules by search and dependency inspection.
3. Find existing tests and fixtures.
4. Identify hidden integration risks: migrations, auth, background jobs, browser-only behavior, flaky tests.
5. Do not implement.
6. Do not read Claude Phase A output.

## Output format

Use `ARTIFACTS.md` §5 Phase A research template with file references and command evidence.

## Failure modes

- Tooling unavailable: report exact missing command.
- Tests fail on baseline: record failure as risk, do not fix.
- Huge repo: sample by architecture boundaries and state coverage partial.

## Examples

Brief: “export CSV.” Output points to dashboard route, existing export helpers, fixture data, and browser test path.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
