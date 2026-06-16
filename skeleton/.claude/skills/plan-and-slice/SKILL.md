---
id: plan-and-slice
agent: claude
version: 0.2.0
memory_files_read: none
---

# Plan and Slice Author

## Trigger description (used for routing)

Clarification complete and Scope Lock exists.

## When to use

Use to produce implementable spec, plan, vertical slices, and verifier-facing criteria.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Issue body with Scope Lock
- Phase A/Synthesis context
- Relevant memory entries
- `ARTIFACTS.md` schemas

## Workflow

1. Write a durable PRD/spec in behavior language.
2. Document architecture/code-style decisions without brittle file paths unless necessary.
3. Split into many thin vertical slices; prefer AFK over HITL.
4. Each slice must be demoable and include schema/API/UI/tests when relevant.
5. Add dependencies so scheduler can topologically order work.
6. Write acceptance criteria that an independent verifier can test without knowing implementation.

## Output format

Fill Spec, Plan, Vertical Slices, Verification Plan, and Provenance sections. Use `ARTIFACTS.md` §4.

## Failure modes

- Cannot split safely: mark one HITL architecture review slice first.
- Acceptance criteria untestable: rewrite before output.
- Too many slices (>12): reduce scope or ask human.

## Examples

Gamification becomes slices for point events, dashboard display, streaks, migration/backfill, and final cross-slice validation.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
