---
id: clarify
agent: claude
version: 0.2.0
memory_files_read: none
---

# Clarification Driver

## Trigger description (used for routing)

Synthesis completes, a clarification reply arrives, `/grill-me` asks for targeted probing, or Status is dragged past Clarifying.

## When to use

Use to ask/resolve only questions that affect scope, behavior, migration, testing, or risk.

## When NOT to use

Do not use for unrelated chat. Do not collapse this skill into another phase just because doing so feels faster. Status-as-state is the harness contract.

## Inputs

- Current issue body
- Existing question threads and replies
- Status transition metadata if auto-accepting recommendations

## Workflow

1. Classify questions as independent or dependent.
2. Post independent questions as separate top-level threads using `ARTIFACTS.md` §2.
3. Ask dependent questions only after parent answer resolves.
4. When replies arrive, update Scope Lock.
5. If Status moves past Clarifying with unresolved questions, auto-accept recommendations and mark `confirmed_by_user: false`.
6. Stop when Scope Lock is coherent.

## Output format

Issue comments for questions plus updated Scope Lock YAML (`ARTIFACTS.md` §3).

## Failure modes

- User answer contradicts another answer: ask one reconciliation question.
- Too many questions: rank materiality and ask the smallest set.
- Non-answer: keep recommendation and note unresolved.

## Examples

Question: “Should points be retroactive?” Recommendation: yes, because existing students otherwise experience the exact problem reported.

## Provenance

Derived from `AIHARNESS-BUILD-PLAN.md` v0.2. Keep this skill synchronized with `ARTIFACTS.md` and `docs/state-machine.md`.
