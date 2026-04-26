---
id: write-a-skill
agent: claude
version: 0.2.0
memory_files_read: none
---

# Write a Skill

## Trigger description (used for routing)

Issue comment command `/write-a-skill`.

## When to use

Use when a human explicitly invokes `/write-a-skill`.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Current thread/comment
- Relevant files/artifacts named by the user

## Workflow

1. Read `ARTIFACTS.md`.
2. Turn a repeated workflow into a SKILL.md. First clarify trigger, inputs, outputs, failure modes, examples, and memory scope. Then draft using the common template.
3. Produce an artifact/comment, not code changes unless explicitly requested.

## Output format

Command-specific structured markdown with evidence and recommendation.

## Failure modes

- Missing target: ask for the target file/issue.
- Too broad: narrow to one decision boundary.

## Examples

User runs `/write-a-skill @client-brief.md`; output follows the command-specific workflow.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
