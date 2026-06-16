You are the planning thread for Dialectical Engine V2.

Use the Disciplined Delivery skill for this task.

Before proposing the design, ask me exactly 5 "grill me" questions. These should be sharp, high-leverage questions that expose hidden assumptions, product risks, data-model ambiguity, security concerns, and implementation tradeoffs. Ask all 5 questions together, then wait for my answers before continuing.

Context:

We want to design and later implement a runtime skill system for Dialectical Engine subagents.

The core idea:

Subagents should use skills as temporary cognitive scaffolds. A skill does not execute code. A skill does not grant new tool permissions. A skill shapes the subagent's identity, reasoning method, search strategy, evidence standards, and constraints.

Skills are persisted in the database as JSON. When a skill is needed, the JSON is materialized into a temporary real SKILL.md, used for the current subagent task, then deleted. The JSON persists.

Important concept:

The skill's description is not merely metadata. It describes what the skill actually does.

There should also be a field that tells the subagent what it is supposed to be.

Use this field name:

subagent_identity

This field is the runtime identity/orientation for the subagent.

Example skill JSON:

{
  "name": "psychological-analysis",
  "description": "Use when the question benefits from a psychological point of view.",
  "subagent_identity": "You are a Harvard-trained psychologist and research-informed analyst. Help the user understand the psychological point of view when relevant.",
  "method": [
    "Identify the psychological mechanisms involved.",
    "Separate evidence-backed claims from interpretation.",
    "Mention uncertainty and competing explanations.",
    "Avoid diagnosing real people unless the user asks for general, non-clinical possibilities."
  ],
  "search_guidance": [
    "Prefer peer-reviewed psychology research, clinical guidelines, systematic reviews, and reputable institutions.",
    "Avoid pop-psychology unless clearly labeled as speculative."
  ],
  "constraints": [
    "Do not present speculation as diagnosis.",
    "Do not invent studies, statistics, or credentials."
  ],
  "status": "provisional",
  "version": 1,
  "quality_score": null,
  "provenance": {
    "created_by_model": "...",
    "created_by_worker_id": "...",
    "created_in_debate_id": "...",
    "created_by_job_id": "..."
  }
}

Desired runtime behavior:

1. For each subagent or deep-dive task, the subagent/coordinator determines what kind of skill would help answer well.
2. The system searches persisted skill JSON records in the database.
3. If a relevant skill exists, fetch it.
4. If no relevant skill exists, create a new skill JSON for this task.
5. Materialize the selected or newly-created JSON into a temporary real SKILL.md.
6. The subagent uses that skill immediately for the current question.
7. After the subagent answers, delete the temporary .md.
8. Persist the JSON and record provenance showing which skill was reused, created, materialized, and used.

Examples:

Financial skill:
The subagent acts as a financial expert. It searches filings, audited statements, market data, investor materials, and regulatory disclosures. It separates accounting facts, valuation assumptions, market assumptions, risk assumptions, and uncertainty.

Psychological skill:
The subagent acts as a research-informed psychologist. It explains psychological mechanisms, competing interpretations, uncertainty, and avoids fake diagnosis.

Statistical skill:
The subagent acts as a statistician. It focuses on base rates, measurement quality, sampling, confounders, effect sizes, uncertainty, and inference limits.

Legal or policy skill:
The subagent acts as a legal/policy analyst. It prioritizes jurisdiction, primary law/regulation, scope limits, implementation constraints, and institutional tradeoffs.

Critical guardrails:

- Skills are prompt/workflow-only.
- Skills cannot grant tool permissions.
- Skills cannot require arbitrary code execution.
- Skills cannot override system/developer/user safety constraints.
- Skills cannot claim fake credentials as factual authority.
- Skills can define an expert stance, but the subagent must still be honest about uncertainty.
- Created skills should be schema-validated before use.
- Newly-created skills can be used immediately, but should likely start as provisional.
- The JSON persists; temporary markdown does not.

Planning task:

After asking and receiving answers to the 5 grill-me questions, produce a PRD-lite and implementation plan for this feature.

Use the existing Dialectical Engine V2 architecture and inspect these areas first:

- coordinator/app/services/dialectical_v2.py
- coordinator/app/models/entities.py
- coordinator/tests/test_dialectical_v2.py
- coordinator/app/services/orchestrator.py
- any existing skill, agent, capability, provenance, or V2 job code

Your output should cover:

1. Product Goal
   - What user/developer problem this solves.
   - What "good" looks like.
   - What should explicitly stay out of scope.

2. Current Architecture Read
   - How V2 currently creates POV jobs and synthesis.
   - How existing SkillDefinition, AgentDefinition, AgentRun, CapabilityMatch, and provenance records work.
   - Which existing code paths are active vs dormant.

3. Proposed Data Model
   - Final skill JSON schema.
   - Required fields.
   - Optional fields.
   - Versioning.
   - Status lifecycle: provisional, active, rejected, maybe deprecated.
   - Quality/reuse fields.
   - Provenance fields.
   - Whether we need migrations.

4. Skill Retrieval Flow
   - How a subagent declares or infers the skill it needs.
   - Whether retrieval happens in coordinator code, via a planner job, or inside a subagent prompt.
   - Matching strategy: exact tags, descriptions, question type, POV/lens, hybrid scoring, embeddings, or another approach.
   - How to avoid irrelevant skills.
   - How to handle multiple relevant skills.

5. Skill Creation Flow
   - What job type or function creates a missing skill.
   - Prompt contract for creating skill JSON.
   - Validation rules.
   - Whether created skills are immediately usable.
   - How to prevent low-quality or unsafe generated skills from polluting future runs.

6. Runtime Materialization
   - Where temporary SKILL.md files should be written.
   - Proposed path format, for example: runtime/skills/{debate_id}/{job_id}/{skill_id}/SKILL.md
   - How JSON renders into Markdown.
   - How the subagent is instructed to use the materialized skill.
   - Cleanup after success.
   - Cleanup after failure or crash.
   - Whether the markdown file is necessary for the real worker implementation or whether the rendered markdown can be injected directly into prompts while still preserving the "real skill" abstraction.

7. Subagent Execution Model
   - How selected skills modify the subagent's prompt.
   - How subagent_identity is injected.
   - How description, method, search_guidance, and constraints shape behavior.
   - How POV-specific deep dives receive different skills.
   - How this interacts with existing v2_pov, v2_agent_run, and v2_synthesize.

8. Provenance and Auditability
   - Record whether a skill was reused or created.
   - Record skill ID, version/hash, job ID, debate ID, POV/subagent ID, worker/model ID.
   - Record materialization path if useful, while accepting that the file is deleted.
   - Surface skill usage in API/UI so users can see which skills shaped which output.

9. Guardrails and Safety
   - Prevent skills from granting tools.
   - Prevent executable instructions.
   - Prevent hidden behavior.
   - Prevent fake expertise or fabricated source claims.
   - Prevent prompt injection from DB skill content.
   - Define validation and sanitization boundaries.

10. Testing Plan
   Include tests for:
   - Relevant existing skill is retrieved.
   - Missing skill triggers creation.
   - Created skill is schema-validated.
   - Created skill is materialized and used immediately.
   - Temporary SKILL.md is deleted after completion.
   - JSON persists.
   - Provenance records created vs reused.
   - Bad skill JSON is rejected.
   - Skill does not expand tool permissions.
   - Different POV subagents receive different relevant skills.
   - Synthesis can report which skills shaped upstream outputs.

11. Implementation Slices
   Break the work into small vertical slices. For each slice include:
   - Goal.
   - Files likely touched.
   - Tests to write first.
   - Implementation notes.
   - Acceptance criteria.

12. Risks and Open Questions
   - Retrieval quality.
   - Skill proliferation.
   - Immediate use of newly-generated skills.
   - Trust and review lifecycle.
   - Prompt-injection risks.
   - UI/API complexity.
   - Whether temp markdown should be truly file-backed or prompt-injected.

Important delivery style:

- Do not implement yet.
- Do not write code yet.
- First ask exactly 5 grill-me questions and wait.
- After my answers, produce the PRD-lite and implementation plan.
- Stay close to the existing codebase patterns.
- Favor small, testable slices.
