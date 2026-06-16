---
id: synthesis
agent: claude
version: 0.2.0
memory_files_read: none
---

# Synthesis

## Trigger description (used for routing)

Both Phase A research outputs exist.

## When to use

Use to reconcile research into one canonical issue interpretation before clarification.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Raw brief
- Claude Phase A output
- Codex Phase A output
- Relevant memory entries cited by either output

## Workflow

1. Read both Phase A outputs cleanly.
2. Extract agreements, contradictions, and independent discoveries.
3. Reframe the problem if research shows the brief is pointing at the wrong layer.
4. Draft `Synthesis`, `Memory Tags`, and initial `Open Questions` sections.
5. Mark each question with recommendation and consequence.
6. Do not create vertical slices yet.

## Output format

Update issue body sections: Synthesis, Memory Tags, Open Questions, Provenance.

## Failure modes

- Research outputs conflict materially: preserve both views and ask a question.
- Phase A missing: do not synthesize; request runner retry.

## Examples

If Claude sees product risk and Codex sees migration risk, synthesis turns both into explicit questions rather than burying one.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
