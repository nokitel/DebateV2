---
id: lessons
agent: claude
version: 0.2.0
memory_files_read: ["memory/mistakes.md", "memory/guardrails.md", "memory/decisions/*.md", "memory/glossary.md"]
---

# Lessons

## Trigger description (used for routing)

PR merged/rejected, parent Done/Rejected, verification failure, or `/lessons-deep`.

## When to use

Use to extract earned memory without creating a junk drawer.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Issue/PR timeline
- Final diff
- Verification/fixer logs
- Existing memory files

## Workflow

Quick pass:
1. Summarize what happened and whether a lesson may exist.
2. If no durable lesson, say so.

Deep pass:
1. Identify repeated failure, surprising success, or durable decision.
2. Draft separate memory proposals with frontmatter.
3. Include Tag rationale and why each passes the bar.
4. Wait for human approval before memory mutation.

## Output format

Quick retrospective or `Lesson proposal` blocks from `ARTIFACTS.md` §10.

## Failure modes

- No evidence: no proposal.
- Existing memory already covers it: cite and skip duplicate.
- Ambiguous lesson: propose narrower version or ask.

## Examples

After two slices fail from timezone ambiguity, propose guardrail: “Any streak/date feature must define timezone in acceptance criteria.”

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
