# ARTIFACTS.md — AI Harness Contracts

<!-- Template variables: PROJECT_NAME -->

This file is the schema reference for {{PROJECT_NAME}}. Skills and workflows link here instead of duplicating schemas.

## 1. Issue body schema

Sections are filled in order:

1. Brief
2. Synthesis
3. Memory Tags
4. Open Questions
5. Scope Lock
6. Spec
7. Plan
8. Vertical Slices
9. Verification Plan
10. Provenance

### Example

```markdown
## Brief
Raw user request, preserved without pretending it is already a spec.

## Synthesis
Canonical interpretation after Phase A research.

## Scope Lock
included: export CSV button
excluded: scheduled exports
deferred: admin audit log
confirmed_by_user: false
```

## 2. Threaded question format

Every clarification question is a top-level thread when independent.

```markdown
### Question Q3: Should points be retroactive?

Context: Existing records already contain completed lessons.
Consequence: Users with prior work may otherwise start from zero.
Recommendation: Backfill points from existing completions.
Owner: product

Choose: retroactive or fresh start?
```

Dependent questions are posted only after their parents resolve. Dragging Status past Clarifying auto-accepts recommendations for unresolved questions.

## 3. Scope lock format

```yaml
included:
  - work we will do now
excluded:
  - work explicitly out of scope
deferred:
  - good ideas for later
migration_decisions:
  - data-shape decisions
testing_edge_cases:
  - edge cases tests/evals must cover
open_questions:
  - unresolved questions, if any
confirmed_by_user: false
```

## 4. Vertical slice schema

Implementers receive declarative acceptance criteria. They do not predefine verifier commands; the verifier generates those.

```yaml
id: S1
title: Student sees points after completing a lesson
slice_type: AFK
user_value: visible progress after one completed lesson
layers_touched: [schema, service, ui, tests]
dependencies: []
blocked_by: []
acceptance_criteria:
  - Completing a lesson awards 10 points exactly once.
  - The dashboard shows updated total points.
verification_strategy: independent browser test plus unit-level evidence
evidence_required:
  - screenshot of dashboard after completion
  - unit test output for idempotency
```

## 5. Phase A research output template

```markdown
## Phase A Research — <agent>

### What I investigated and why
Narrative, not checklist.

### Findings
Concrete observations with file/source references.

### Assumptions
What may be wrong.

### Confidence
high | medium | low, with reason.

### Open ambiguities
Questions synthesis should consider.
```

## 6. Phase B critique output template

Clean-slate critique reads the finalized issue body only.

```markdown
## Phase B Critique

### Gaps
- severity: material — missing rollback path for migration.

### Risks
- severity: minor — test fixture may not match production data shape.

### Improvements
- severity: minor — combine duplicated flow into a service.

### Observability gaps
- severity: material — no logging around failed export generation.

### UX gaps
- severity: minor — empty state unclear.

### License & Dependency risk
- severity: material — new dependency license unknown.
```

## 7. Verification evidence templates

### Acceptance verification — gating

```markdown
## Acceptance Verification

Criterion: Completing a lesson awards 10 points exactly once.
Result: pass | fail
Evidence: screenshot/log/link
Reasoning: observed behavior matched expected behavior.
```

### Code-quality verification — informational

```markdown
## Code-quality review (Codex|Claude)

Severity: major
Category: coupling
Location: app/services/gamification.ts:42
Finding: service imports route-only helpers.
Suggestion: move shared conversion into domain utility.
```

Code-quality findings do not move Status backward. Human review decides.

## 8. Memory entry frontmatter

```yaml
---
id: mem-2026-001
created_at: 2026-04-26T20:00:00Z
created_by: claude-lessons
source_issue: 12
source_pr: 34
status: active
superseded_by: null
tags: [planned, testing]
---
```

Proposals must include `Tag rationale:` in the comment requesting approval.

## 9. Slice retrospective format

Quick pass:

```markdown
Slice S1 shipped after one verification cycle. The useful learning was that dashboard state needed a real browser check, not just a unit test.
```

Deep pass proposes separate memory entries only when actionable later.

## 10. Lesson proposal format

```markdown
## Lesson proposal

<full entry frontmatter + body>

Tag rationale: `testing` because this affects verification design.
Why it passes the bar: future browser-visible features need this check.
```

## 11. Cross-slice regression report

```markdown
## Cross-slice Regression Report

### Per-slice criterion regressions
- S1 criterion failed after S2 merged: ...

### Emergent integration failures
- Dashboard and export disagree on point total.

### Originating slices
- S1, S2

### Evidence
- screenshot/log/link
```
