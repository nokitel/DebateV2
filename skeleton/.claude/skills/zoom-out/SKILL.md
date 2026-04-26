---
id: zoom-out
agent: claude
version: 0.2.0
memory_files_read: none
---

# Zoom Out

## Trigger description (used for routing)

Issue comment command `/zoom-out`.

## When to use

Use when a human explicitly invokes `/zoom-out`.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Current thread/comment
- Relevant files/artifacts named by the user

## Workflow

1. Read `ARTIFACTS.md`.
2. Map surrounding system: callers, callees, data flow, tests, memory, ADRs, and likely blast radius. Output a concise architecture map and recommended next question.
3. Produce an artifact/comment, not code changes unless explicitly requested.

## Output format

Command-specific structured markdown with evidence and recommendation.

## Failure modes

- Missing target: ask for the target file/issue.
- Too broad: narrow to one decision boundary.

## Examples

User runs `/zoom-out @client-brief.md`; output follows the command-specific workflow.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
