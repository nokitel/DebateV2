---
id: clarify
agent: claude
invocation: runner-driven
version: 0.2.0
inputs:
  - issue_body: Current issue body or scoped artifact.
outputs:
  - comment_or_artifact: Structured output defined below.
memory_files_read:
  - memory/decisions/*.md: relevant architectural decisions
---

# Clarification Driver

## Trigger description (used for routing)

Synthesis completes, question reply appears, /grill-me invoked, or plan-finalize escalates.

## When to use

Use when this exact workflow slot is reached by the runner or explicit command.

## When NOT to use

Do not use as a generic chat prompt. Do not mutate memory directly.

## Inputs

- Issue body or slice body.
- Relevant artifacts named by the runner.
- Scoped memory files declared in frontmatter.

## Workflow

1. Read `AGENTS.md` and `ARTIFACTS.md`.
2. Read declared inputs.
3. Produce only the output this skill owns.
4. Include evidence, assumptions, and failure notes when relevant.

## Output format

Use the matching schema in `ARTIFACTS.md`.

## Failure modes

- Missing input: post a blocker comment explaining the missing artifact.
- Contradiction with memory: cite it and request clarification.

## Examples

Example: Given a brief for export-to-CSV, produce the relevant structured output without implementing adjacent features.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2.
