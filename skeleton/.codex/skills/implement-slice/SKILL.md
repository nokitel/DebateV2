---
id: implement-slice
agent: codex
version: 0.2.0
memory_files_read: ["memory/decisions/*.md", "memory/guardrails.md", "memory/glossary.md"]
---

# Slice Implementer

## Trigger description (used for routing)

Sub-issue Status=Implementing. Mode is `implement` or `resolve-merge-conflict`.

## When to use

Use to implement a single vertical slice in an isolated worktree/container.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Sub-issue body
- Parent issue body
- Worktree path mounted at `/workspace`
- Mode flag
- In conflict mode: conflict markers, original implementer log, main commit messages

## Workflow

Mode `implement`:
1. Read acceptance criteria.
2. Implement the smallest slice that satisfies them.
3. Write your own unit/integration/browser tests.
4. Run Ralph loop: test → fix → retest until checks pass or genuinely stuck.
5. Maintain `.agent/verification/<slice-id>-implementer-log.md`.
6. Open draft PR and comment “Self-verified, awaiting independent verifier.”

Mode `resolve-merge-conflict`:
1. Read conflict markers and main commit messages.
2. Preserve both intents where possible.
3. Preserve this slice’s acceptance criteria.
4. Re-run Tier 1 self-verification.
5. Append conflict resolution rationale to implementer log.

## Output format

PR + sub-issue comment + Status=Self-Verified + implementer log.

## Failure modes

- >10 failed loops on same test: comment Stuck and Status=Blocked.
- Conflict cap hit: Status=Verification Failed with merge-conflict-unresolved reason.
- Test infra broken: comment exact failure and Status=Blocked.

## Examples

Conflict example: main adds dashboard totals while slice adds point events. Resolve by keeping shared service as source of truth, not duplicating total logic.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
