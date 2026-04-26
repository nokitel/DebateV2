---
id: fix-slice
agent: codex
version: 0.2.0
memory_files_read: none
---

# Slice Fixer

## Trigger description (used for routing)

Sub-issue Status=Fixing cycle N/3.

## When to use

Use after acceptance verification fails. It may also triage code-quality reports, but acceptance is gating.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Sub-issue body
- Acceptance deficiency report
- Optional code-quality reports
- Compressed implementer log
- Cycle number

## Workflow

1. Read acceptance deficiency first; this must be fixed.
2. Triage each code-quality finding: address or dismiss with reason.
3. Read compressed implementer log to avoid repeating dead ends.
4. Implement minimal repair.
5. Run Tier 1 self-verification.
6. Comment fixes and move Status=Self-Verified, or Verification Failed at cap.

## Output format

Fix commit/PR update + comment including acceptance fixes and code-quality triage decisions.

## Failure modes

- Cycle cap reached: Status=Verification Failed.
- Deficiency impossible under current scope: ask human with exact contradiction.

## Examples

Acceptance fail: CSV includes hidden rows. Fix filter source of truth, add browser test, dismiss minor naming finding as unrelated.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
