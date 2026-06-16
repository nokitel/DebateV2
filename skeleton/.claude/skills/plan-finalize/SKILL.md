---
id: plan-finalize
agent: claude
version: 0.2.0
memory_files_read: none
---

# Plan Finalizer

## Trigger description (used for routing)

Phase B critique exists.

## When to use

Use to incorporate critique and produce final Ready for Work plan or reopen clarification.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Current issue body
- Phase B critique
- Scope Lock
- Relevant memory

## Workflow

1. Triage critique findings.
2. Fold minor and clear major fixes into plan.
3. If material critique changes scope, reopen Clarifying with specific question.
4. If plan is sound, set Status → Ready for Work.
5. Preserve provenance of changes.

## Output format

Updated issue body plus comment summarizing accepted/dismissed critique findings.

## Failure modes

- Critical unresolved issue: Status → Clarifying or Blocked.
- Critique contradicts user scope: cite and keep scope unless unsafe.

## Examples

Codex flags migration rollback missing; finalizer adds rollback acceptance criterion and migration slice note.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
