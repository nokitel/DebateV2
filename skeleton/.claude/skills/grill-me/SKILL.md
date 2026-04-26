---
id: grill-me
agent: claude
version: 0.2.0
memory_files_read: none
---

# Grill Me

## Trigger description (used for routing)

Issue comment command `/grill-me`.

## When to use

Use when a human explicitly invokes `/grill-me`.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Current thread/comment
- Relevant files/artifacts named by the user

## Workflow

1. Read `ARTIFACTS.md`.
2. Ask one sharp question at a time to force hidden decisions into the open. Stop when the decision boundary is clear enough to update Scope Lock.
3. Produce an artifact/comment, not code changes unless explicitly requested.

## Output format

Command-specific structured markdown with evidence and recommendation.

## Failure modes

- Missing target: ask for the target file/issue.
- Too broad: narrow to one decision boundary.

## Examples

User runs `/grill-me @client-brief.md`; output follows the command-specific workflow.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
