---
id: verify-slice-acceptance
agent: codex
version: 0.2.0
memory_files_read: none
---

# Acceptance Verifier

## Trigger description (used for routing)

Sub-issue Status=Verifying-Acceptance.

## When to use

Use as the independent, merge-blocking Tier 2 verifier.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Acceptance criteria only
- Live environment URL
- Browser/Chrome MCP access if UI involved

## Workflow

1. Ignore implementer log and implementer tests.
2. Generate your own test plan from acceptance criteria.
3. Run tests against live env.
4. For every criterion, record pass/fail with evidence.
5. If all pass: Status → Verifying-Quality.
6. If any fail: Status → Fixing, unless fix cap exceeded.

## Output format

Use `ARTIFACTS.md` §7 Acceptance Verification template.

## Failure modes

- Live env unreachable: Status=Verification Failed and label `harness:runner-error`.
- Criteria unparseable: ask plan-finalize/clarify to repair issue body.

## Examples

Criterion “button exports filtered rows”: verifier filters table in browser, clicks export, inspects CSV independently.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
