# Dialectical Engine V2 Coding Handoff

Date: 2026-06-10

This document is the handoff for the future coding agent. It captures the approved product direction, architecture sketch, vertical slice, Kanban, and the mandatory tests-first implementation rule.

No implementation has begun as of this document. The coding agent must not write production code, migrations, scaffolding, or implementation tests until the user explicitly approves coding.

## Non-Negotiable Implementation Rule: Frozen Tests First

The implementation must follow strict test-driven development.

Before writing any production code, migrations, API changes

, UI changes, orchestration code, worker code, or database model changes, the coding agent must write the full test suite for the approved vertical slice.

The test phase is complete only when all required tests for the slice are written and reviewed as a coherent suite. After that point, the tests are frozen.

Frozen means:

- Do not delete tests to make implementation easier.
- Do not weaken assertions.
- Do not loosen schema checks.
- Do not replace real behavioral checks with superficial smoke tests.
- Do not skip, mark expected-fail, quarantine, or conditionally bypass tests.
- Do not change test expectations after implementation starts unless the user explicitly approves a requirements change.
- Do not mock away the behavior being proven.
- Do not claim completion unless the frozen tests pass.

The tests must prove behavior, persistence, routing, provenance, UI/API contracts, and reuse. They must be difficult to cheat accidentally or intentionally. A test that only checks that a function was called is not enough when the requirement is persisted, user-visible debate behavior.

Expected sequence:

1. Confirm coding approval from the user.
2. Write the full vertical-slice test suite first.
3. Run the tests and confirm they fail for the right reasons.
4. Freeze the tests.
5. Write production code.
6. Run the frozen tests until they pass.
7. Run existing regression tests.
8. Report exactly what passed and what remains risky.

## Product Goal

Dialectical Engine should become an in-depth, traceable debate orchestration system. It must not answer a user question directly. Each question launches an orchestration pipeline that classifies the question, runs default analyzers, searches or creates reusable reasoning capabilities, invokes selected Agents and Skills, and returns a provenance-rich debate artifact.

The engine must support reusable reasoning capability:

- Agents: persistent specialist AI entities, equivalent in spirit to `Agents.md` definitions.
- Skills: Codex-style procedural capabilities, equivalent in spirit to `SKILL.md` files, persisted as JSON in the database.

Both Agents and Skills are stored in the database as JSON. They are searchable, selected when relevant, created automatically when missing, saved immediately, and used in the current debate.

## Product Decisions

The grill-me session established these decisions:

1. Debate runs are branchable debate trees.
2. Agent and Skill creation is fully automatic when no suitable existing capability exists.
3. Reuse decisions use a hybrid quality gate: semantic search, metadata matching, LLM judging, duplicate detection, and quality/status signals.
4. Runtime orchestration uses a strict hierarchy: coordinator selects or creates Skills first; Skills select, create, or invoke Agents; Agents generate debate perspectives.
5. The UX is an interactive debate workspace, using the existing project UI style.

## Existing Project Context

The project already has:

- FastAPI coordinator owning SQLite state, orchestration, SSE, and REST APIs.
- Local workers that pull jobs and call model CLIs/API backends.
- Next.js UI in `web/`.
- Existing pages for `/new`, `/debate/[id]`, `/settings`, and `/admin/workers`.
- Debate tree rendering, node regeneration, generation history, streaming SSE updates, synthesis panels, model/worker badges, and token-gated actions.

The new work should extend the existing architecture and UI rather than replacing it.

## Required User Flow

1. User submits a question from the UI.
2. Coordinator creates a debate root and branch.
3. Coordinator classifies the question and determines required reasoning capabilities.
4. Coordinator searches persisted Skills first.
5. Router selects suitable Skills or creates new Skills when no suitable match exists.
6. Selected Skills search persisted Agents.
7. Skills select suitable Agents or create new Agents when missing.
8. Coordinator runs three mandatory default analyzers:
   - Statistical Analyzer
   - Scientific Analyzer
   - Psychological Analyzer
9. Analyzer outputs are persisted.
10. Selected Skills and Agents examine analyzer outputs.
11. Each Agent produces exactly 5 pros and exactly 5 cons.
12. Outputs preserve provenance.
13. Coordinator synthesizes a final debate artifact.
14. UI shows an interactive debate workspace with analyzers, Skills, Agents, outputs, provenance, branch lineage, and synthesis.

## Runtime Difference Between Agents And Skills

### Agent

An Agent is a persistent specialist participant. It has identity, role, purpose, boundaries, allowed tools/skills, reasoning style, and expected output. It is complete enough to run as a real debate participant.

Agents answer as a specialist perspective. They produce argument outputs, including exactly 5 pros and 5 cons when invoked for debate generation.

### Skill

A Skill is a reusable procedure. It defines when to trigger, what context to inspect, what workflow to follow, what output format to produce, and what constraints to obey.

Skills are database-backed equivalents of `SKILL.md` behavior. They are not loose prompts on disk. They are persisted as JSON and loaded into runtime when selected.

Skills guide the coordinator and workers. Under the strict hierarchy, Skills select, create, or invoke Agents.

## Agent JSON Contract

Persisted Agents should include at least:

```json
{
  "id": "uuid",
  "kind": "agent",
  "name": "Scientific Skeptic",
  "version": 1,
  "status": "active-or-provisional",
  "description": "Evaluates claims through empirical evidence and methodological rigor.",
  "domain_tags": ["science", "evidence", "methodology"],
  "role": "Debate participant",
  "purpose": "Challenge weak empirical claims and surface evidence quality.",
  "instructions": {
    "operating_principles": [],
    "reasoning_style": "methodical, evidence-weighted, skeptical",
    "boundaries": [],
    "allowed_tools": [],
    "allowed_skills": []
  },
  "input_contract": {
    "required": ["question", "analyzer_outputs"],
    "optional": ["prior_branch_outputs", "skill_context"]
  },
  "output_contract": {
    "pros_count": 5,
    "cons_count": 5,
    "requires_summary": true,
    "requires_confidence": true
  },
  "quality": {
    "created_by": "system",
    "creation_reason": "No suitable existing agent found.",
    "reuse_count": 0,
    "last_used_at": null,
    "quality_score": null
  },
  "provenance": {
    "created_in_debate_id": "uuid",
    "created_by_model": "model-id",
    "created_by_worker_id": "worker-id",
    "creation_prompt_id": "uuid"
  }
}
```

## Skill JSON Contract

Persisted Skills should include at least:

```json
{
  "id": "uuid",
  "kind": "skill",
  "name": "Policy Tradeoff Debate Skill",
  "version": 1,
  "status": "active-or-provisional",
  "description": "Structures policy questions into stakeholder, evidence, risk, and implementation tradeoffs.",
  "trigger": {
    "question_types": ["policy", "governance", "public tradeoff"],
    "domain_tags": ["policy", "tradeoffs"],
    "activation_rules": []
  },
  "workflow": {
    "context_to_inspect": [
      "question",
      "classification",
      "statistical_analyzer_output",
      "scientific_analyzer_output",
      "psychological_analyzer_output"
    ],
    "steps": [
      "Identify required perspectives",
      "Search for matching Agents",
      "Create missing Agents",
      "Invoke Agents",
      "Enforce 5 pros and 5 cons per Agent",
      "Compare tensions",
      "Return structured debate contribution"
    ]
  },
  "constraints": {
    "must_use_default_analyzers": true,
    "must_preserve_provenance": true,
    "must_require_exactly_5_pros_5_cons": true
  },
  "output_contract": {
    "format": "structured_json",
    "sections": ["selected_agents", "agent_outputs", "skill_findings"]
  },
  "quality": {
    "created_by": "system",
    "creation_reason": "No suitable skill found.",
    "reuse_count": 0,
    "quality_score": null
  },
  "provenance": {
    "created_in_debate_id": "uuid",
    "created_by_model": "model-id",
    "created_by_worker_id": "worker-id",
    "creation_prompt_id": "uuid"
  }
}
```

## Architecture Sketch

### Web UI

Use the existing Next.js app in `web/`.

The existing debate page should evolve into an interactive debate workspace. It should display:

- Branchable debate tree.
- Analyzer outputs.
- Selected and created Skills.
- Selected and created Agents.
- Each Agent or Skill contribution.
- Exactly 5 pros and exactly 5 cons for every Agent debate output.
- Provenance badges for analyzer, Agent, Skill, model, worker, prompt, and generation.
- Final synthesis.
- Branch/rerun/regenerate controls where supported.
- History and lineage for generated artifacts.

The UI style should match the current restrained operational design: panels, badges, tree views, history sections, synthesis panels, and token-gated controls.

### Coordinator

The FastAPI coordinator owns:

- Debate creation.
- Branch lineage.
- Question classification.
- Capability search and routing.
- Skill creation.
- Agent creation.
- Analyzer scheduling.
- Agent invocation scheduling.
- Synthesis scheduling.
- Persistence.
- SSE updates.
- API responses for the UI.

The coordinator must not answer directly.

### Workers

Workers remain execution units. They should not own product orchestration. They receive structured jobs and return structured outputs plus runtime metadata.

Worker job types may include:

- Analyzer execution.
- Skill creation.
- Agent creation.
- Agent argument generation.
- Skill-mediated critique or structuring.
- Final synthesis.

### Database

Minimum conceptual entities:

- `debates`
- `debate_branches`
- `debate_nodes`
- `agents`
- `skills`
- `analyzer_runs`
- `capability_matches`
- `generation_jobs`
- `generation_outputs`
- `provenance_records`
- `syntheses`

Important links:

- Debate has many branches.
- Branch has many analyzer runs.
- Branch has selected Skills.
- Skill selection links to matched or created Skill.
- Skill invocation links to selected or created Agents.
- Agent output links to analyzer outputs, Skill invocation, worker, model, prompt, and debate branch.
- Synthesis links to all upstream outputs.

### Capability Router

The router decides when to reuse or create capabilities.

Skill routing order:

1. Search Skills by metadata and semantic relevance.
2. Judge candidate fit.
3. Reject duplicate or low-quality candidates.
4. Select existing Skill if suitable.
5. Create and persist a new Skill if none is suitable.
6. Use the Skill immediately.

Agent routing order:

1. Selected Skill determines needed Agent roles.
2. Search Agents by metadata and semantic relevance.
3. Judge candidate fit.
4. Reject duplicate or low-quality candidates.
5. Select existing Agent if suitable.
6. Create and persist a new Agent if none is suitable.
7. Use the Agent immediately.

### Duplicate And Quality Control

Automatic creation must be guarded.

Before creating a Skill or Agent:

- Search by semantic similarity.
- Search by name, domain tags, and purpose.
- Run an LLM duplicate judge against top candidates.
- Check status and quality metadata.
- Prefer reusable general capabilities over narrow duplicates.

After creation:

- Persist the JSON definition.
- Store creation reason.
- Store creation provenance.
- Track reuse count.
- Mark status as active or provisional.

Recommendation: new generated Agents and Skills are immediately usable but marked `provisional` until reused successfully or reviewed.

## Vertical Slice

The smallest useful end-to-end version must prove:

1. Question intake through the existing UI.
2. Debate and root branch persistence.
3. Three mandatory analyzer runs.
4. Skill lookup.
5. Automatic Skill creation if no match exists.
6. Agent lookup through the selected Skill.
7. Automatic Agent creation if no match exists.
8. Agent execution with exactly 5 pros and 5 cons.
9. Persistence of all outputs.
10. Provenance for every generated artifact.
11. Final synthesis.
12. UI inspection of analyzers, Skills, Agents, Agent outputs, provenance, and synthesis.
13. A second similar question reuses at least one previously persisted Skill or Agent.

### Included

- Database persistence.
- JSON Agent and Skill definitions.
- Automatic creation.
- Default analyzer execution.
- Provenance.
- UI inspection.
- SSE or refresh-based state visibility.
- Reuse proof.

### Excluded

- Manual Agent/Skill library management.
- Rating/review UI.
- Complex branch comparison.
- Multi-user collaboration.
- Advanced quality scoring.
- Marketplace/admin workflows.

## Frozen Test Suite Requirements

The coding agent must write tests first for all of the following before implementation.

### Persistence Tests

- Can persist and retrieve an Agent JSON definition.
- Can persist and retrieve a Skill JSON definition.
- Agent JSON preserves role, purpose, boundaries, reasoning style, allowed skills/tools, output contract, and provenance.
- Skill JSON preserves trigger rules, workflow, constraints, output contract, and provenance.
- Debate branch lineage is persisted.
- Analyzer outputs are linked to debate and branch.
- Agent outputs are linked to debate, branch, Skill, Agent, analyzer inputs, model, worker, prompt, and job.

### Router Tests

- Existing relevant Skill is selected.
- New Skill is created when no suitable Skill exists.
- Existing relevant Agent is selected.
- New Agent is created when no suitable Agent exists.
- Duplicate creation is avoided when a similar Agent or Skill already exists.
- Low-quality or rejected capabilities are not selected.
- Created capabilities are persisted and used in the same debate.

### Analyzer Tests

- Every debate runs Statistical, Scientific, and Psychological analyzers.
- Analyzer outputs are structured.
- Missing analyzer output fails the debate pipeline or leaves a clear failed state.
- Downstream Agent execution receives analyzer outputs.

### Agent Output Contract Tests

- Agent output with exactly 5 pros and exactly 5 cons is accepted.
- Agent output with fewer or more than 5 pros is rejected.
- Agent output with fewer or more than 5 cons is rejected.
- Agent output without provenance is rejected.
- Agent output is persisted with source Agent and Skill links.

### Orchestration Tests

- A new question does not produce a direct answer.
- A new question creates a debate pipeline run.
- The pipeline order is classification, Skill lookup/create, Agent lookup/create, analyzers, Agent execution, synthesis.
- Newly created Skill is used in the same run.
- Newly created Agent is used in the same run.
- Final synthesis references upstream Agent outputs and analyzer findings.

### Reuse Tests

- First question creates at least one new Skill or Agent when the database is empty.
- Second similar question reuses at least one existing Skill or Agent.
- Reuse increments reuse metadata or records a reuse event.

### API Contract Tests

- Debate detail API returns analyzer outputs.
- Debate detail API returns selected/created Skills.
- Debate detail API returns selected/created Agents.
- Debate detail API returns Agent outputs with 5 pros and 5 cons.
- Debate detail API returns provenance.
- Debate detail API returns branch lineage.

### SSE Tests

- SSE emits analyzer started/completed events.
- SSE emits Skill selected/created events.
- SSE emits Agent selected/created events.
- SSE emits Agent output completed events.
- SSE emits synthesis completed event.
- Reconnecting clients can recover enough event history to render current state.

### UI Tests

- `/new` starts the full orchestration mode, not direct single-shot answering.
- `/debate/[id]` displays analyzer panels.
- `/debate/[id]` displays selected/created Skills.
- `/debate/[id]` displays selected/created Agents.
- `/debate/[id]` displays exactly 5 pros and 5 cons per Agent output.
- `/debate/[id]` displays model and worker provenance.
- `/debate/[id]` displays prompt or prompt reference provenance.
- `/debate/[id]` displays synthesis.
- Existing regenerate/history/token-gated behavior is not broken.

### Regression Tests

- Existing worker registration tests still pass.
- Existing adapter tests still pass.
- Existing config tests still pass.
- Existing settings/admin worker UI contracts remain intact.
- Existing markdown export either remains compatible or is intentionally extended to include new artifacts.

## Kanban

### Backlog

- Finalize Agent JSON contract.
- Finalize Skill JSON contract.
- Decide lifecycle statuses: active, provisional, deprecated, rejected, archived.
- Decide whether default analyzers later become system Skills.
- Decide exact UI layout: tabs, split inspector, or stacked panels.

### Ready

- Write frozen persistence tests.
- Write frozen router tests.
- Write frozen analyzer tests.
- Write frozen Agent output contract tests.
- Write frozen orchestration tests.
- Write frozen reuse tests.
- Write frozen API contract tests.
- Write frozen SSE tests.
- Write frozen UI tests.
- Write frozen regression tests.

### Implementation Tasks

These tasks must not start until the frozen tests are written.

- Add Agent persistence.
- Add Skill persistence.
- Add debate branch/provenance records.
- Add default analyzer output storage.
- Build question classification step.
- Build Skill search.
- Build Skill relevance judge.
- Build automatic Skill creation.
- Build Agent search.
- Build Agent relevance judge.
- Build automatic Agent creation.
- Build default analyzer execution.
- Build Agent argument execution.
- Enforce exactly 5 pros and 5 cons.
- Build final synthesis.
- Capture provenance for every artifact.
- Extend debate detail API.
- Extend SSE events.
- Extend `/debate/[id]` UI workspace.
- Update `/new` flow to run the full pipeline.
- Extend markdown export if required.

### Verification

- First question creates a debate, branch, analyzers, at least one Skill, at least one Agent, Agent output, provenance, and synthesis.
- Every Agent output has exactly 5 pros and exactly 5 cons.
- Provenance exists for every analyzer, Skill, Agent, and synthesis output.
- UI displays analyzer, Skill, Agent, pros/cons, provenance, and synthesis artifacts.
- Second similar question reuses at least one prior Skill or Agent.
- Regeneration or branching preserves lineage.
- Existing worker status, settings, admin, and history flows still function.
- Frozen tests pass without weakening or bypassing them.

## Recommended Build Order After Tests Are Frozen

1. Data contracts and persistence.
2. Coordinator orchestration skeleton.
3. Analyzer runs.
4. Skill lookup and creation.
5. Agent lookup and creation.
6. Agent 5-pro/5-con generation.
7. Synthesis.
8. Debate detail API shape.
9. SSE event expansion.
10. UI workspace panels.
11. Reuse proof.
12. Export/provenance polish.

## Completion Standard

The vertical slice is complete only when:

- The frozen tests pass.
- Existing regression tests pass.
- The UI demonstrates the full pipeline.
- The system creates and immediately uses missing Skills and Agents.
- The system reuses a persisted Skill or Agent on a similar second question.
- Every generated artifact has provenance.
- The coding agent can report the exact commands run and the results.

