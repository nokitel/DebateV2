# AI Harness — Build Plan (v0.2)

> A detailed, action-ready build plan synthesizing all design decisions from
> the design interview. Hand this to an AI implementer (or work through it
> yourself); every step has a *what*, a *why*, and the *acceptance criterion*
> for that step being done.
>
> **Changelog from v0.1:**
> - Added doctrines #9 (provider diversity), #10 (acceptance vs quality
>   verification are different jobs), #11 (conflict resolution is continuation
>   of implementation).
> - Added parent state `Final Validation` between `In Review` and `Done` for
>   cross-slice regression detection.
> - Added sub-issue state `Integrating` for `git merge main` with same-implementer
>   conflict resolution.
> - Split verification: `verify-slice-acceptance` (gate) +
>   `verify-code-quality` (informational, configurable single/dual mode).
> - Added `harness/config.yml` for verification mode configuration.
> - Updated fix-slice skill to receive both acceptance and code-quality reports.
> - Updated plan-critique skill Gate 3 categories: observability, UX,
>   license/dependency risk.
> - Three new workflows: `on-integrating.yml`, `on-final-validation.yml`,
>   `on-quality-verifier-config.yml`.

---

## 0. Reading guide

This document is structured so an AI implementer can execute it in order, top
to bottom, with minimal back-references. Each phase produces a working
artifact. Each phase has its own definition-of-done that, when met, gates the
next phase.

The plan is intentionally heavy on **why**, because the corpus this design
draws from is unambiguous that AI implementers without the *why* will silently
make the wrong tradeoffs. Every "why" cites which design decision it
implements.

Conventions used throughout:
- `<harness>` = the skeleton repo (e.g., `github.com/<you>/aiharness`)
- `<project>` = a target project the harness gets bootstrapped into
- `Q<n>` references the locked decision from the design interview (Q1 through Q20)
- File paths starting `/` are absolute repo paths; paths starting with no slash
  are relative to whichever repo is being discussed at that moment.

---

## 1. Locked design summary

The full table of decisions, for orientation. Every implementation step in the
plan derives from one or more of these.

| # | Decision | Lock |
|---|----------|------|
| Q1 | Scope | Reusable pattern, proven on a real project first |
| Q2 | Form | Skeleton repo → bootstrap script → à la carte skill installs |
| Q3 | Agent roles | Claude=clarify/plan/synthesize/authoritative; Codex=research+critique+implement; artifact-mediated; Gemini deferred |
| Q4 | Source of truth | GitHub Issues + Project board; structured body; Status field drives gates |
| Q5 | Trigger | Self-hosted GitHub Actions runner per teammate; `harness next` manual fallback |
| Q6 | Isolation | Per-issue Docker Compose stack (full agent freedom inside, host unreachable) |
| Q7 | Issue body | Structured sections filled in order, sub-issues per slice |
| Q8 | Clarification | Threaded parallel questions; auto-accept on Status drag past Clarifying |
| Q9 | Reviewer pattern | Phase A parallel research (Claude + Codex) + Phase B clean-slate Codex critique; Claude authoritative |
| Q10 | Slice scheduling | Topological scheduler, default concurrency=1, label-overridable, serial merge, no auto-retry |
| Q11 | Containers/secrets | Per-issue Compose; agent has full power inside; host unreachable; synthetic creds default; ephemeral GH App tokens |
| Q11b | Team scaling | Per-teammate runners v1; swappable executor shim for API-key future |
| Q12 | Skill architecture | `.claude/` and `.codex/` libraries with shared `ARTIFACTS.md` at root |
| Q13 | Memory | 4 MD files + auto-generated `index.json`; provenance frontmatter; supersedes-not-overwrites; contradictions first-class; layered retrieval (skill-scope → tags → grep); bidirectional tagging |
| Q14 | Verification | Two-tier: implementer Ralph-loop self-verify → independent verifier (Codex default, clean slate) against criteria; bounded auto-fix (max 3); compressed process log between cycles. **v0.2: split into acceptance verification (gate) + code-quality verification (informational, configurable).** |
| Q15 | Lessons | Quick pass always (retrospective comment); deep pass conditional (failures/rejection/manual); per-proposal 👍/👎 writes; never proposes skills or harness edits; quarterly prune ritual |
| Q16 | Bootstrap | Standalone skeleton repo + curl-piped `init.sh` + `.harness-version` + 3-way upgrade script |
| Q17 | Phase A research | Unconstrained process (no checklist, no caps); structured-section narrative output; synthesis does heavy work and may reframe |
| Q18 | Skills v1 | Layer 1: all runner-driven invocations. Layer 2 ad-hoc: `/zoom-out`, `/design-an-interface`, `/grill-me`, `/write-a-skill`. Deferred: `/improve-architecture`, conditional skills. Bootstrap-only: `setup-pre-commit`, `git-guardrails` |
| Q19 | Observability | GitHub-native + JSONL metrics + `harness status` CLI + pinned status issue. Dedicated dashboard deferred to v1.5 |
| Q20 | State machine | Status (single-select) is canonical state; labels are attributes only. Two-drag UX: `Clarifying → Plan Ready` (stop asking) and `Plan Ready → Ready for Work` (approve). **v0.2: parent state `Final Validation` and sub-issue state `Integrating` added.** |

---

## 2. Doctrines that override any local-feeling expedient choice

These are short rules that the implementer must internalize before writing
anything. They come from the source corpus and are the reason the harness will
compound rather than rot.

1. **Boring artifacts beat clever automation.** Markdown files, named labels,
   plain bash scripts, structured comment templates. The implementer's job is
   to make the boring scaffolding work, not to add intelligence.
2. **No silent writes.** Every memory write requires explicit human 👍. Every
   plan change after approval re-poses through a threaded question. Every
   contradicting decision must cite the contradiction. (Q13, Q15)
3. **Evidence or not done.** No PR merges, no Status moves to Done, no
   verification passes without recorded evidence. This is a corpus invariant. (Q14)
4. **Source of truth is upstream of compiled views.** If the dashboard issue is
   wrong, the runner is wrong. Do not edit the dashboard. Same for `index.json`,
   the parent-issue Status, and any rendered template. Regenerate. (Q13, Q19)
5. **Wide net for research, narrow gate for memory.** Phase A researchers may
   investigate freely; the lessons skill is biased *against* writing entries.
   These are different roles, opposite incentives. (Q15, Q17)
6. **Containers are blast-radius limits, not security boundaries against
   malicious code.** The trust model is: I trust Claude/Codex CLIs not to be
   evil; I do not trust them not to make catastrophic mistakes. The container
   prevents mistakes from reaching the host. (Q11)
7. **One canonical state field, no mixed signals.** Status field is where state
   lives. Labels are attributes. Refusing this discipline = drift. (Q20)
8. **Skills are earned by repetition or failure.** Do not ship a skill because
   it sounds useful. Ship the skills we agreed; defer everything else. (Q18)
9. **Provider diversity is the strongest verifier guarantee.** Same-provider
   clean-slate is the v0.1 fallback. When the executor shim (Q11b) lands, route
   the independent verifier to a different provider (Gemini, GPT-4-class) for
   high-risk issues. The verifier slot is the right place for provider
   diversity to land first.
10. **Acceptance verification and code-quality verification are different
    jobs.** Acceptance asks "does this satisfy the criteria" (binary, blocking).
    Code-quality asks "is this maintainable, secure, simple" (judgment,
    informational). Do not conflate them: different prompts, different agents
    optionally, different gating semantics.
11. **Conflict resolution is a continuation of implementation, not a
    verification concern.** When a slice's branch needs to take main and resolve
    conflicts, the implementer who wrote the slice resolves them — same agent,
    same context, same warm container. Spawning a clean-slate "conflict
    resolver" agent loses the context that makes good resolution possible.
    Independent verification still happens *after* resolution; just don't make
    the resolver itself independent.

---

## 3. Phase-by-phase build plan

The build is divided into 8 phases. Each phase produces a checkpointed
artifact that can be tested in isolation. Phases must be executed in order;
later phases have hard dependencies on earlier ones.

```
Phase 1 — Skeleton repo skeleton (the meta-bones, ~2-4 hours)
Phase 2 — Artifact contracts and templates (~3-5 hours)
Phase 3 — Skill libraries — Layer 1 (~10-14 hours, was 6-10 in v0.1)
Phase 4 — Skill libraries — Layer 2 ad-hoc (~2-3 hours)
Phase 5 — Container substrate and runner integration (~6-10 hours)
Phase 6 — Workflows and state machine (~8-12 hours, was 6-10 in v0.1)
Phase 7 — Bootstrap and upgrade scripts (~2-4 hours)
Phase 8 — First-issue dogfood on real project (~2-4 hours)
```

Total: ~36-56 hours of focused implementer work, plus your interaction time.
(v0.2 adds ~6 hours of skill/workflow work for the verification split,
integration state, and final-validation logic.)

---

## Phase 1 — Skeleton repo skeleton

**Goal:** create the empty repo with the right top-level shape. Nothing in it
needs to *work* yet; this phase is about getting the layout right so the next
phases have homes for their work.

### 1.1 Create the harness repo

**What:** create `github.com/<you>/aiharness` (or your preferred name). Empty,
private at first, MIT-licensed.

**Why:** Q2/Q16 lock — the harness is a standalone GitHub repo with versioned
releases. Standalone (not a submodule, not an npm package) because it must be
language-agnostic and avoid coupling to any target project's tooling.

**Acceptance:** repo exists, has a `main` branch, has an empty `README.md` with
a one-line description.

### 1.2 Lay down the directory structure

**What:** create the following empty directories (with `.gitkeep` files where
needed) and template files (`.tpl` extension means it gets rendered at
bootstrap time):

```
aiharness/
├── README.md                              # human overview of the harness itself
├── VERSION                                # current skeleton version, plain text "0.2.0"
├── CHANGELOG.md                           # versioned changelog, starts empty
├── LICENSE                                # MIT
├── docs/
│   ├── architecture.md                    # how the harness works, for humans
│   ├── state-machine.md                   # the Status diagram (Q20)
│   ├── roles.md                           # what each agent invocation does (Q12)
│   ├── memory.md                          # the memory model in detail (Q13)
│   ├── containers.md                      # the Compose stack model (Q11)
│   ├── verification.md                    # NEW v0.2: acceptance vs quality verification
│   └── upgrade-guide.md                   # for projects upgrading skeleton versions
├── skeleton/                              # everything in here gets copied into target projects
│   ├── AGENTS.md.tpl                      # canonical router for both Claude and Codex (Q12)
│   ├── ARTIFACTS.md.tpl                   # the artifact contracts: schemas, formats (Q12)
│   ├── .harness/
│   │   ├── config.yml.tpl                 # NEW v0.2: verification mode + other tunables
│   │   └── metrics/                       # JSONL files written by runner (Q19)
│   │       └── .gitkeep
│   ├── .claude/
│   │   ├── CLAUDE.md.tpl                  # Claude-specific addendum (Q12)
│   │   └── skills/                        # Layer 1 + Claude-side Layer 2 skills (Q18)
│   ├── .codex/
│   │   ├── CODEX.md.tpl                   # Codex-specific addendum (Q12)
│   │   └── skills/                        # Layer 1 + Codex-side Layer 2 skills (Q18)
│   ├── memory/
│   │   ├── README.md                      # explains the four files and the discipline (Q13)
│   │   ├── decisions/
│   │   │   └── README.md                  # explains how ADRs work
│   │   ├── mistakes.md                    # empty; explains schema in comment block
│   │   ├── glossary.md                    # empty; explains schema in comment block
│   │   ├── guardrails.md                  # empty; explains schema in comment block
│   │   ├── tags.md                        # controlled tag vocabulary, starts empty (Q13)
│   │   └── .gitignore                     # ignores index.json (it's regenerated)
│   ├── prompts/
│   │   ├── shared/
│   │   │   ├── question-format.md         # the corpus's threaded-question template
│   │   │   ├── evidence-format.md         # what "done" reports must contain
│   │   │   └── body-schema.md             # the Q7 issue body section structure
│   │   └── invocation-shim.md             # how runners inject context (Q12)
│   ├── .github/
│   │   ├── workflows/                     # all the runner workflows (Phase 6)
│   │   └── ISSUE_TEMPLATE/
│   │       ├── feature.yml                # default issue template (Q7-shaped)
│   │       └── meta.yml                   # for harness-skeleton change requests
│   ├── docker/
│   │   ├── docker-compose.harness.yml.tpl # the per-issue stack (Q11)
│   │   ├── agent.Dockerfile               # the Claude/Codex agent image
│   │   └── proxy/                         # the local reverse-proxy config (Q11)
│   ├── scripts/
│   │   ├── harness                        # the per-project CLI (Q19)
│   │   ├── lib/
│   │   │   ├── gh-status.sh               # GraphQL helper for Status field (Q20)
│   │   │   ├── tags-validate.sh           # tag controlled-vocab check (Q13)
│   │   │   └── memory-index.sh            # generates index.json (Q13)
│   │   ├── stack/
│   │   │   ├── up.sh                      # spin up per-issue stack (Q11)
│   │   │   ├── down.sh                    # tear down (Q11)
│   │   │   ├── list.sh
│   │   │   └── orphan-cleanup.sh
│   │   ├── fixtures/
│   │   │   ├── refresh.sh                 # pull and sanitize golden DB (Q11)
│   │   │   └── scrub.example.sh
│   │   └── setup/
│   │       ├── install-runner.md          # docs for self-hosted runner setup (Q5)
│   │       ├── install-app.md             # docs for GitHub App install (Q11)
│   │       └── setup-project.sh           # creates Project board + Status field (Q20)
│   └── .harness-version.tpl               # written at bootstrap with skeleton commit SHA (Q16)
├── bootstrap/
│   ├── init.sh                            # the curl-piped bootstrap (Q16)
│   └── upgrade.sh                         # the 3-way merge upgrade (Q16)
└── tests/                                 # tests for the skeleton itself, run in CI
    ├── lint-templates.sh
    ├── render-templates.sh
    └── fixtures/
```

**Why each piece is here:**
- `skeleton/` separates "files that go into target projects" from "files about
  the harness itself" (`docs/`, `bootstrap/`, `tests/`). This separation makes
  the bootstrap script trivial: `cp -r skeleton/* <target>/`. (Q16)
- `.claude/` and `.codex/` are sibling directories so each agent's library is
  independently swappable. (Q12)
- `.harness/config.yml.tpl` is new in v0.2 — it holds project-level harness
  configuration including the verification mode (`single` / `dual`, primary
  agent). Bootstrap renders it; the workflows read it. (See §6.4.)
- `memory/decisions/` is a directory (one file per ADR) but `mistakes.md`,
  `glossary.md`, `guardrails.md` are single files. ADRs need individual
  supersession; the others are append-only logs. (Q13)
- `prompts/shared/` holds the templates referenced from inside skill files,
  so changing a question format updates everywhere. (Q12)
- `docker/` separates the Compose stack template from the per-skill content.
  Stack template renders at bootstrap; skills change without recomposing. (Q11)
- `scripts/lib/` holds reusable shell helpers. `gh-status.sh` exists because
  GitHub Projects v2 fields need GraphQL, not REST. (Q20)
- `bootstrap/` and `tests/` are skeleton-author-only — they never get copied
  into target projects.

**Acceptance:** running `tree skeleton/` produces the structure above. Every
directory has at least a README.md or .gitkeep. No `.tpl` files contain
unrendered placeholders that would break a basic file-validity check.

### 1.3 Set the skeleton's own AGENTS.md

**What:** the harness repo itself needs an `AGENTS.md` — different from the one
in `skeleton/AGENTS.md.tpl`, which is the *target project's* router. This one
governs implementers working on the harness skeleton.

**Why:** when you (or an AI) want to add a skill or fix a workflow in the
skeleton later, the meta-harness needs to follow its own discipline. The
corpus calls this "the harness for the harness" and warns it'll come up. Q16
flagged it.

Contents (concrete):

```markdown
# AGENTS.md (skeleton repo)

You are working on the AI Harness skeleton itself, not on a target project.
The skeleton is the source of truth that gets copied into target projects via
`bootstrap/init.sh`. Your changes here propagate to all future bootstrapped
projects, and (via `bootstrap/upgrade.sh`) to existing ones.

## Invariants
- Never edit anything inside `skeleton/` without considering downstream impact
  on existing bootstrapped projects.
- Templates with `.tpl` extension contain `{{handlebars}}` placeholders. They
  must remain renderable by `bootstrap/init.sh` after edits.
- Every change to `skeleton/` must bump VERSION (semver) and add a CHANGELOG
  entry.
- Tests in `tests/` must pass before commit.

## Workflow
- Filing a feature issue on this repo follows the same Q7 body schema as
  bootstrapped projects. The skeleton is bootstrapped to itself for this.
- Skill changes go through Phase A research, clarification, Phase B critique,
  approval, slice fanout. Same as any other project.

## Definition of done
- Files changed
- Tests pass (`bash tests/render-templates.sh`)
- VERSION bumped
- CHANGELOG entry written
- If the change affects target projects: an upgrade note in
  `docs/upgrade-guide.md`
```

**Acceptance:** `AGENTS.md` exists at the repo root, contains the above (or
equivalent), and refers to the skeleton sub-tree by relative path correctly.

### 1.4 Phase 1 definition of done

- [ ] Repo created
- [ ] Directory tree matches §1.2
- [ ] `VERSION` reads `0.2.0`
- [ ] `LICENSE`, `README.md`, `CHANGELOG.md` exist (CHANGELOG can be empty header)
- [ ] Root `AGENTS.md` exists
- [ ] Initial commit pushed to `main`

---

## Phase 2 — Artifact contracts and templates

**Goal:** write the documents that define every contract the runner and the
agents share. These are read by every invocation, so getting them right now
prevents drift later.

### 2.1 `skeleton/AGENTS.md.tpl`

**What:** the canonical router that goes into every target project. Read by
both Claude and Codex on every invocation.

**Why:** Q12 lock — root-level router, agent-neutral, points to ARTIFACTS.md
for schemas. The corpus is emphatic that this file should *route, not teach*.
Keep it small.

**Required sections (in order):**
1. Project purpose (templated, filled at bootstrap)
2. Canonical commands (templated)
3. Architecture boundaries (templated)
4. Safety invariants (fixed across all projects):
   - never edit `memory/` files directly during a slice; use the lessons skill
   - never write outside the worktree's directory
   - never assume host network reachable
   - any decision contradicting an existing ADR must cite it explicitly
5. Definition of done (fixed): files changed + commands run + results +
   skipped checks with reasons + remaining risks
6. Links: `ARTIFACTS.md`, `.claude/CLAUDE.md`, `.codex/CODEX.md`,
   `memory/README.md`, `prompts/shared/`, `.harness/config.yml`

**Length:** target ≤120 lines. If it grows past that, move detail into a
sub-doc and link.

**Why ≤120 lines:** the corpus warning about "root instruction files as junk
drawers" is one of the named anti-patterns. This file is read on every
invocation; bloat costs context across the whole system.

**Acceptance:** file exists, all template variables are documented in a
top-of-file comment block, file passes `tests/lint-templates.sh`.

### 2.2 `skeleton/ARTIFACTS.md.tpl`

**What:** the schema reference. This is the file every skill points at when it
needs to know "what does a slice look like, what does a question look like."

**Why:** Q12 lock — the artifact contract lives at the root, not in either
agent library, so changing the slice schema is a one-file edit. (Corpus
warning: "drift guaranteed within a month" if schemas duplicate.)

**Required sections (in order):**
1. **Issue body schema** (Q7):
   - The full structured-section template: Brief, Synthesis, Memory Tags,
     Open Questions (table), Scope Lock, Spec, Plan, Vertical Slices,
     Verification Plan, Provenance.
   - Section-fill order rules.
   - What each section contains and what's "good" vs "bad" content.
2. **Threaded question format** (Q8):
   - Top-level comment shape (context, consequence, recommendation, owner).
   - Reply rules (free-form, but agent re-asks if reply is ambiguous).
   - Auto-accept rule (Status drag past Clarifying).
3. **Scope lock format** (Q4):
   - included / excluded / deferred / migration_decisions / testing_edge_cases /
     open_questions / confirmed_by_user.
4. **Vertical slice schema** (Q4, Q14):
   - id, title, slice_type (AFK|HITL), user_value, layers_touched,
     dependencies, acceptance_criteria (declarative human terms),
     verification_strategy, evidence_required.
   - Note explicitly: implementer does NOT declare verification_commands;
     verifier generates them. (Q14)
5. **Phase A research output template** (Q17):
   - The structured-section narrative format.
   - "What I investigated and why" section.
   - Confidence + Assumptions sections.
6. **Phase B critique output template** (Q9):
   - Gaps / Risks / Improvements headings.
   - **NEW v0.2: also Observability gaps / UX gaps / License & Dependency
     risk** as additional structured categories the critique covers.
   - Clean-slate constraint stated explicitly.
7. **Verification evidence template** (Q14):
   - **v0.2 split into two distinct templates:**
     - **Acceptance verification:** per-criterion pass/fail/evidence-link/
       reasoning. This is the gating tier.
     - **Code-quality verification:** per-finding severity (critical | major |
       minor) / category (coupling | clarity | security | testing | etc.) /
       location / suggestion. Informational; does not gate merge.
   - Two distinct outputs: implementer self-verify (internal log) and
     independent verifier (canonical evidence).
8. **Memory entry frontmatter** (Q13):
   - id, created_at, created_by, source_issue, source_pr, status,
     superseded_by, tags.
   - Tag rationale comment requirement at proposal time.
9. **Slice retrospective format** (Q15):
   - Quick-pass shape (one paragraph).
   - Deep-pass per-proposal shape.
10. **Lesson proposal format** (Q15):
    - Frontmatter to be merged + tag rationale + reasoning.
11. **NEW v0.2: Cross-slice regression report (Final Validation):**
    - Structured comment shape distinguishing per-slice criterion regressions
      from emergent integration failures. Used to auto-create
      `harness:cross-slice-regression` issues.

**Length:** target 450-650 lines. This is the one file in the harness that
*should* be long; it's the schema reference.

**Acceptance:** file exists, every section has at least one concrete example
(filled-in template), `tests/lint-templates.sh` passes.

### 2.3 `skeleton/prompts/shared/`

**What:** three small files referenced by every skill that needs them.

- `question-format.md` — the threaded-question template, expanded with
  examples, including how to handle dependent vs independent questions.
- `evidence-format.md` — the "no done without evidence" template.
- `body-schema.md` — a quick-reference of the issue body sections, pointing
  back to ARTIFACTS.md for full detail.

**Why:** these are the most frequently-included sub-prompts. Centralizing them
means the corpus's "skill description is critical routing logic" stays valid:
skills can stay short by linking to these.

**Acceptance:** files exist, each ≤80 lines, each contains at least 2 worked
examples.

### 2.4 `skeleton/memory/README.md`

**What:** the memory-discipline doc. Read by every skill that touches memory.

**Why:** Q13 lock — memory writes are governed; readers must understand the
provenance/supersedes/contradiction discipline before writing.

**Required content:**
1. The four-file model (`decisions/`, `mistakes.md`, `glossary.md`,
   `guardrails.md`).
2. Frontmatter required on every entry (Q13).
3. The supersedes-not-overwrites rule with worked example.
4. The contradictions-are-first-class rule with worked example.
5. The retrieval model: per-skill scope → tag-based ID resolution via
   `index.json` → grep fallback.
6. The bidirectional tagging requirement: every proposing agent picks tags;
   `tags.md` controlled vocabulary is canonical; new tags allowed but flagged.
7. The pruning ritual (quarterly).
8. What memory is NOT for (project-map information deducible from code, etc.).

**Acceptance:** file exists, contains all 8 sections, ≤200 lines.

### 2.5 `skeleton/memory/tags.md`

**What:** the controlled vocabulary file. Starts mostly empty.

**Why:** Q13 — to prevent tag drift (`auth` vs `authentication` vs
`auth-flow`).

**Initial content:** a header block explaining the discipline, then a
placeholder list with a few starter tags that are likely universal:

```yaml
# Tags controlled vocabulary
# Every memory entry's `tags:` frontmatter must use a tag from this list,
# OR introduce a new tag (which the proposing agent must justify in its
# proposal comment via "Tag rationale: ...").
#
# This file is updated:
#   - Manually when adding a deliberate new tag
#   - During the quarterly prune ritual (merge synonyms)

tags:
  # Risk/mode (matches harness:risk-* labels)
  - fast-patch
  - planned
  - high-risk

  # Add project-specific tags as memory accumulates.
```

**Acceptance:** file exists, structure parseable as YAML, has the comment
block above.

### 2.6 `skeleton/memory/{mistakes,glossary,guardrails}.md`

**What:** three empty files with header comment blocks explaining their
schema.

**Why:** Q13. They start empty because the harness has no mistakes / glossary
terms / guardrails on a fresh project. They fill via the lessons skill.

**Each file's header:**
- One-line purpose
- Frontmatter schema reference (point to ARTIFACTS.md §8)
- Append-only invariant
- Example entry (commented out)

**Acceptance:** all three files exist, parseable as Markdown, header blocks
match the format.

### 2.7 `skeleton/memory/decisions/README.md`

**What:** the per-ADR-file discipline doc.

**Why:** Q13 — ADRs are one-file-per-decision (not appended) because they need
individual supersession.

**Content:**
1. File naming: `NNNN-slug.md` where NNNN is sequential.
2. Frontmatter requirements.
3. Body sections: Context, Decision, Alternatives Considered, Consequences,
   Contradicts (if any), Provenance.
4. Worked example (one fictional ADR).

**Acceptance:** file exists, ≤120 lines.

### 2.8 `skeleton/.claude/CLAUDE.md.tpl` and `skeleton/.codex/CODEX.md.tpl`

**What:** agent-specific addenda. Each is short — they're shims, not
re-statements of AGENTS.md.

**Why:** Q12 — the canonical layer is portable; agent-specific niceties
(slash commands, Skills primitive details, MCP integration) live here.

**`CLAUDE.md.tpl` content:**
1. "Read AGENTS.md and ARTIFACTS.md first."
2. List of Layer 2 ad-hoc skills available as `/commands` (Q18).
3. Claude Code Skills system note: skills in `.claude/skills/` are auto-loaded
   when their trigger description matches.
4. MCP servers expected (chrome-mcp at minimum).

**`CODEX.md.tpl` content:**
1. "Read AGENTS.md and ARTIFACTS.md first."
2. "You are typically invoked headlessly by the runner; your output is
   parsed mechanically. Do not include conversational filler."
3. Worktree assumptions.
4. Container assumptions: full filesystem access in `/workspace`; host
   unreachable; outbound internet allowed.

**Acceptance:** both files exist, each ≤80 lines, each links to AGENTS.md and
ARTIFACTS.md.

### 2.9 NEW v0.2: `skeleton/.harness/config.yml.tpl`

**What:** the per-project harness configuration file. Rendered at bootstrap
with sensible defaults; user edits to tune.

**Why:** Doctrine #10 (acceptance vs quality verification are different jobs)
and the dual-verifier option require a configuration surface. Without this,
every project would hard-code the verification mode.

**Required content:**

```yaml
# Harness configuration
# Read by workflows on every invocation. Edit to tune behavior.

verification:
  acceptance:
    # Locked in v0.1: always Codex, clean-slate, criterion-driven.
    # Acceptance verification is the gating tier; merge-blocking.
    verifier: codex

  code_quality:
    # NEW v0.2: separate informational tier.
    # Findings post as comments with severity tags; do NOT block merge.
    # Your manual code-quality review at the In Review stage is the actual gate.
    mode: single        # single | dual
    primary: codex      # codex | claude — used for single mode and as merger in dual mode
    # In dual mode: both Codex and Claude run code-quality verification.
    # Both reports go to the fixer if any acceptance failures occur.
    # Both reports are visible to the human reviewer.

scheduling:
  # Q10: topological scheduler, default concurrency=1.
  default_concurrency: 1
  fix_cycles_cap: 3      # Q14: max fix loop cycles before escalation
  conflict_resolution_cycles_cap: 3   # NEW v0.2: same cap, applied to merge-conflict resolution

memory:
  # Q13: layered retrieval; index regenerates on push to memory/
  reindex_on_push: true
  prune_ritual: quarterly   # informational; the actual ritual is manual

observability:
  # Q19: pinned status issue + JSONL metrics
  status_issue_update_interval_minutes: 15
  metrics_jsonl_dir: .harness/metrics
```

**Acceptance:** file exists, parseable as YAML, all keys documented inline,
bootstrap script can render it with project-specific defaults.

### 2.10 Phase 2 definition of done

- [ ] All §2.1–§2.9 files exist with the required content
- [ ] `tests/lint-templates.sh` passes (validates `.tpl` files have closing
      handlebars, `.md` files have valid frontmatter where required)
- [ ] `tests/render-templates.sh` can render every `.tpl` file with sample
      variables and produce valid Markdown
- [ ] `git diff` reviewed and committed to a `phase-2-artifacts` branch

---

## Phase 3 — Skill libraries — Layer 1

**Goal:** write the runner-driven skills that make the pipeline function.

Per Q12, these split between `.claude/` and `.codex/` directories. Per the
corpus, every `SKILL.md` follows the same shape (when to use, when not to use,
workflow, output format, examples, provenance). Per Q18, all ship in v1; no
manual fallbacks.

**The Layer 1 skills (v0.2 — 13 total):**

| # | Library | Skill | Purpose |
|---|---------|-------|---------|
| 1 | `.claude/skills/phase-a-research/` | Claude Phase A research | Independent investigation of brief (Q9, Q17) |
| 2 | `.codex/skills/phase-a-research/` | Codex Phase A research | Independent investigation of brief (Q9, Q17) |
| 3 | `.claude/skills/synthesis/` | Synthesis | Reconcile both Phase A outputs, possibly reframe (Q17) |
| 4 | `.claude/skills/clarify/` | Clarification driver | Post threaded questions, process answers, rewrite body sections on contradiction (Q8) |
| 5 | `.claude/skills/plan-and-slice/` | Plan author | Write Spec/Plan/Vertical Slices sections from settled scope-lock (Q4) |
| 6 | `.codex/skills/plan-critique/` | Phase B critique | Clean-slate critique of finalized pre-approval plan (Q9). v0.2: extended categories. |
| 7 | `.claude/skills/plan-finalize/` | Plan finalizer | Respond to critique, fold-and-proceed OR escalate-back (Q9, Q20) |
| 8 | `.codex/skills/implement-slice/` | Slice implementer | Implement one slice in container with Ralph loop (Q14). **v0.2: gains `mode: implement | resolve-merge-conflict` parameter.** |
| 9 | `.codex/skills/verify-slice-acceptance/` | Acceptance verifier | NEW v0.2 (split from old verify-slice). Generate Chrome MCP tests from criteria, run, evidence. **Gating tier — blocks merge on failure.** |
| 10a | `.codex/skills/verify-code-quality/` | Codex code-quality verifier | NEW v0.2. Static-analysis-flavored: coupling, dead code, leaky abstractions, test depth, dependency hygiene. **Informational — does not block.** |
| 10b | `.claude/skills/verify-code-quality/` | Claude code-quality verifier | NEW v0.2. Reasoning-flavored: architectural fit, naming, simplicity-vs-cleverness, readability, observability gaps. **Informational — does not block.** |
| 11 | `.codex/skills/fix-slice/` | Slice fixer | NEW v0.2 input shape: receives acceptance deficiency report (if any) PLUS code-quality reports from one or two verifiers per config. Triages rather than just-fixing. |
| 12 | `.claude/skills/lessons/` | Lessons | Quick + deep pass; produce retrospective + memory proposals (Q15) |

So 13 distinct Layer 1 skills total in v0.2 (was 11 in v0.1). The fixer
(invocation-numbered as 11) is conditional on verification failure and exists
in the loop.

### 3.1 Common SKILL.md template

Every Layer 1 skill follows this structure (corpus invariant; see ARTIFACTS.md
§5 / corpus Wiki 07):

```markdown
---
id: <skill-id>
agent: claude | codex
invocation: runner-driven
version: 0.2.0
inputs:
  - <named input>: <description>
outputs:
  - <named output>: <description>
memory_files_read:
  - <file>: <reason>
---

# <Skill Name>

## Trigger description (used for routing)
<one-paragraph crisp description; this is what Claude's Skills system or
the runner reads to decide whether to invoke this skill>

## When to use
<concrete situations>

## When NOT to use
<adjacent skills this is often confused with, and why this isn't them>

## Inputs
<what the runner provides to this invocation>

## Workflow
<numbered steps>

## Output format
<exact shape of what this skill produces; reference ARTIFACTS.md if applicable>

## Failure modes
<known ways this skill can fail and what to do>

## Examples
<at least one worked example>

## Provenance
<corpus references, related skills>
```

Implementer task: write this template to `skeleton/.claude/skills/_template.md`
and `skeleton/.codex/skills/_template.md` so creators of new skills (including
Q18's `/write-a-skill`) start from it.

### 3.2 Skill #1 — Claude Phase A research

**Path:** `skeleton/.claude/skills/phase-a-research/SKILL.md`

**Trigger:** "Invoked when an issue moves to Status=Researching. Produces an
independent assessment of the brief, structured by section, no checklist
constraints."

**Inputs:**
- Issue body (current state, just the Brief section filled)
- Issue number (for posting back)
- Repo read access

**Workflow:**
1. Read the brief.
2. Investigate freely — grep, read files, consult `memory/` (with tag-based
   scope inferred from brief language).
3. Form an independent assessment.
4. Produce output in the Phase A research output template (ARTIFACTS.md §5).

**Output format:** ARTIFACTS.md §5 (Phase A research output template).

**Failure modes:**
- Brief is too vague to research → output Confidence: low + list ambiguities
  prominently in the Open Ambiguities section.
- Repo read access fails → output partial assessment, label issue
  `harness:phase-a-incomplete`.

**Memory files read:**
- `memory/decisions/*.md` filtered by tags inferred from brief
- `memory/guardrails.md`
- `memory/glossary.md`
- `memory/tags.md` (for available tag vocabulary)

**Why no checklist:** Q17 lock — process unconstrained. The skill prompt
explicitly says "investigate as the angle you naturally take suggests; do not
follow a fixed checklist."

**Acceptance:** SKILL.md exists, follows template, has a worked example
(fictional issue → fictional output). Reviewer can predict the output shape
just from reading the skill.

### 3.3 Skill #2 — Codex Phase A research

**Path:** `skeleton/.codex/skills/phase-a-research/SKILL.md`

**Trigger:** "Invoked when an issue moves to Status=Researching, IN PARALLEL
with Claude's Phase A research. Produces an independent assessment, blind to
Claude's output."

**Same overall shape as 3.2** but with the agent-strength tilt: Codex's prompt
notes that Codex tends to investigate via codebase tooling (grep, find,
language-server-style queries), whereas Claude's strength is in synthesis.
This is informational, not constraining — Codex still investigates whatever
angle it chooses (Q17 lock).

**Critical instruction in the prompt:** "Do NOT read other comments on the
issue. Your output is independent; you have no access to Claude's parallel
research. The synthesis step (a separate invocation) will reconcile."

**Acceptance:** as 3.2.

### 3.4 Skill #3 — Synthesis

**Path:** `skeleton/.claude/skills/synthesis/SKILL.md`

**Trigger:** "Invoked when both Phase A research comments are posted. Produces
the canonical synthesis section in the issue body. Authoritative — may
reframe."

**Inputs:**
- Claude Phase A comment
- Codex Phase A comment
- Original brief

**Workflow (Q17 lock):**
1. Read both Phase A outputs as starting points.
2. Reconcile facts where they agree (confirmed) vs disagree (flag).
3. Investigate independently if needed — synthesis is allowed to go deeper
   than either researcher.
4. **Reframe if needed** — synthesis may decide the issue is fundamentally
   different from what the researchers framed. State this explicitly.
5. Produce the Synthesis section to be appended to the issue body.
6. Produce the initial Open Questions table (threaded questions follow,
   posted by the clarify skill).
7. Produce the initial `## Memory Tags` section recommendation.

**Output format:**
- Updated issue body Synthesis section
- Initial Open Questions table
- Memory Tags recommendation (subject to your override during clarification)

**Failure modes:**
- Researchers severely contradict on basic facts → synthesis must explicitly
  re-investigate the contradicted facts and state ground truth.
- Both researchers low-confidence → synthesis flags this prominently and
  produces more thorough Open Questions.

**Memory files read:** same as Phase A skills, plus `memory/mistakes.md`
(synthesis is the right place to catch "we tried this before").

**Acceptance:** SKILL.md follows template, has a worked example showing
synthesis reframing two Phase A outputs into a third framing.

### 3.5 Skill #4 — Clarification driver

**Path:** `skeleton/.claude/skills/clarify/SKILL.md`

**Trigger:** "Invoked when (a) synthesis completes (initial post of all
independent threaded questions), or (b) a user reply on a question thread is
detected, or (c) `/grill-me` is comment-invoked, or (d) plan-finalize escalates
back."

**Inputs:**
- Issue body (current state)
- Either: synthesis-just-completed signal, OR specific comment thread that got
  a new reply, OR escalation context.

**Workflow (Q8 lock):**
1. Determine the trigger sub-mode.
2. **Initial post mode:** read the synthesis-produced Open Questions table.
   Post each currently-independent question as a top-level comment thread
   with context/consequence/recommendation/owner. Mark dependent questions as
   deferred.
3. **Reply mode:** read the reply, decide:
   - Reply resolves question cleanly → mark resolved in Open Questions table,
     check if any newly-independent dependent questions can now be posted.
   - Reply contradicts a previous resolution or synthesis framing → rewrite
     the affected body sections, post a comment summarizing what changed,
     re-pose any newly-dependent questions.
   - Reply is ambiguous → post a clarifying follow-up in the same thread.
4. **Escalation mode (from plan-finalize):** post a new threaded question
   with the escalation context.

**Output format:** comments on the issue + body section updates.

**Failure modes:**
- Reply is unparseable → ask for clarification in the same thread.
- A user comment is on a closed/resolved thread → ignore unless it's a
  follow-up that re-opens (heuristic: explicit "wait" or "actually" language).

**Memory files read:** `memory/glossary.md` (for domain terms during
questioning), `memory/decisions/*.md` (relevant by tags).

**Acceptance:** SKILL.md follows template, has worked examples for all three
trigger sub-modes.

### 3.6 Skill #5 — Plan and slice author

**Path:** `skeleton/.claude/skills/plan-and-slice/SKILL.md`

**Trigger:** "Invoked when Status moves from Clarifying to Plan Ready (or
synthesis completes with zero open questions). Writes Spec, Plan, and Vertical
Slices sections of the issue body."

**Inputs:** issue body (Brief, Synthesis, Scope Lock filled).

**Workflow:**
1. Read the issue body.
2. Auto-resolve any still-open threaded questions to their recommendations
   (the auto-accept Q8 mechanic). Update Open Questions table to reflect.
3. Produce the Spec section: goal, non-goals, user scenarios, constraints,
   edge cases, acceptance criteria, required tests/manual checks.
4. Produce the Plan section: implementation sequence, files, phases, commands,
   risks.
5. Produce Vertical Slices: per-slice schema (id, title, slice_type AFK|HITL,
   user_value, layers_touched, dependencies, acceptance_criteria,
   verification_strategy, evidence_required).
   - **Crucial:** acceptance_criteria are written in declarative human terms.
     Do NOT pre-write Chrome MCP scripts; the verifier generates those. (Q14)
   - Each slice's `dependencies:` must use IDs of slices in this issue;
     external dependencies (other issues) get a `blocked_by:` instead.
6. Produce Verification Plan: list of acceptance criteria across all slices
   that the verifier will check.

**Output format:** updated issue body sections.

**Failure modes:**
- Scope lock has unresolved open questions → halt; post a comment requesting
  clarify-skill re-invocation.
- Slices can't be made vertical → halt; post a comment proposing a re-scope.

**Memory files read:** `memory/decisions/*.md`.

**Acceptance:** SKILL.md follows template, has a worked example showing a
brief turning into 3-4 vertical slices with proper dependencies.

### 3.7 Skill #6 — Phase B critique (Codex) — v0.2 extended

**Path:** `skeleton/.codex/skills/plan-critique/SKILL.md`

**Trigger:** "Invoked when Status moves from Clarifying to Plan Ready, AFTER
plan-and-slice completes. Clean slate — no awareness of Phase A research
output. Reads only the finalized issue body."

**Inputs:** the finalized issue body (Brief, Synthesis, Spec, Plan, Vertical
Slices, Verification Plan).

**Workflow (Q9 lock + v0.2 extensions):**
1. Read the issue body. **Do NOT read Phase A research comments.** Do NOT read
   synthesis comments other than the body Synthesis section.
2. Produce critique with the following structured sections (v0.2 expanded):
   - **Gaps:** things missing from the plan.
   - **Risks:** assumptions or paths likely to fail.
   - **Improvements:** alternative shapes worth considering.
   - **Observability gaps:** NEW v0.2. Logging, metrics, error visibility,
     debuggability concerns.
   - **UX gaps:** NEW v0.2. User-facing behavior, error states, edge cases in
     interaction, accessibility.
   - **License & dependency risk:** NEW v0.2. New dependencies introduced,
     license compatibility, version pinning, supply-chain concerns.
3. Each finding includes: severity (minor | material), reasoning, suggested
   change.

**Output format:** comment on the issue, sectioned exactly as above.

**Failure modes:**
- Plan is fundamentally unclear → produce a "Plan Unclear" critique with
  specific ambiguities; severity material.
- Critique would be empty → still produce comment with explicit "no findings"
  per section + brief reasoning per section.

**Memory files read:** `memory/mistakes.md`, `memory/decisions/*.md` filtered
by issue Memory Tags.

**Why clean slate:** Q9 lock. Without it, Codex's critique inherits the
framing it produced in Phase A and over-defers. Clean slate forces it to
critique against the *current artifact*.

**Acceptance:** SKILL.md follows template, has a worked example showing a
critique with at least one finding in each of the six categories.

### 3.8 Skill #7 — Plan finalizer

**Path:** `skeleton/.claude/skills/plan-finalize/SKILL.md`

**Trigger:** "Invoked when Phase B critique comment is posted. Reads critique,
decides fold-and-proceed (minor findings only) OR
escalate-back-to-clarification (any material finding)."

**Inputs:** the issue body + the Phase B critique comment.

**Workflow (Q9, Q20 R2 lock):**
1. Read the critique. Categorize each finding:
   - Minor: factually correct, fold into Plan; no human input needed.
   - Material: requires a tradeoff or product decision; needs human input.
2. **If all minor:** update Plan section with folded findings. Post a
   "Plan finalized — minor findings folded" comment listing what was
   incorporated and what was rejected (with reasoning per rejection).
   Status remains Plan Ready (signal: ready for human approval).
3. **If any material:** do NOT update the Plan. Post an "Escalating critique
   findings" comment listing the material findings. Re-pose each material
   finding as a new threaded question via the clarify skill (skill #4 in
   escalation mode). Status moves back to Clarifying.

**Output format:**
- Updated Plan section (fold case) OR new threaded questions (escalate case).
- Always: a comment summarizing what was folded vs rejected vs escalated.

**Failure modes:**
- Critique is unparseable → escalate-back with the critique as a question to
  the user.

**Memory files read:** none (this is pure reasoning over the critique +
existing body).

**Acceptance:** SKILL.md follows template, has worked examples for fold case
and escalate case.

### 3.9 Skill #8 — Slice implementer (Codex) — v0.2 extended with conflict-resolution mode

**Path:** `skeleton/.codex/skills/implement-slice/SKILL.md`

**Trigger:** "Invoked when (a) a sub-issue's Status moves to Implementing
(`mode: implement`), or (b) the Integrating workflow detects merge conflicts
and re-spawns the same implementer with `mode: resolve-merge-conflict`. Runs
inside the per-issue Compose stack with the worktree mounted."

**Inputs (mode-dependent):**

**`mode: implement` (default, original Q14):**
- Sub-issue body (the slice's content)
- Parent issue body (for cross-slice context)
- Worktree path (mounted in container at `/workspace`)
- Memory files in scope (passed by runner per skill declaration)

**`mode: resolve-merge-conflict` (NEW v0.2):**
- Sub-issue body (unchanged)
- Worktree path with active merge conflict (markers present in conflicting
  files)
- The slice's full implementer log from the original Implementing phase
  (preserved in the worktree at `.agent/verification/<slice-id>-implementer-log.md`)
- The conflicting commits' messages from `main` (provided as context)
- The slice's acceptance criteria (re-emphasized)

**Workflow — `mode: implement` (Q14 Tier 1):**
1. Read the slice's acceptance criteria.
2. Implement. Free use of all tooling inside the container.
3. Write E2E tests (Chrome MCP-driven) against your understanding of the
   acceptance criteria. **These are YOUR tests, not the verifier's.**
4. Run the Ralph loop:
   - Run unit tests + lints + typecheck + your E2E tests.
   - On failure: read failure, fix, re-run. Repeat.
   - Maintain `.agent/verification/<slice-id>-implementer-log.md` in the
     worktree as you go: what you tried, what failed, what you discovered.
5. When all your checks pass:
   - Open a draft PR from `feature/issue-<N>-<slug>` against `main`.
   - Post comment on sub-issue: "Self-verified, awaiting independent
     verifier."
   - Move sub-issue Status to Self-Verified.

**Workflow — `mode: resolve-merge-conflict` (NEW v0.2, doctrine #11):**
1. Read the conflict markers in the worktree.
2. Read the conflicting commits' messages from main to understand what
   changed in the integrated state.
3. Read the original implementer log to remember your own reasoning.
4. Resolve conflicts preserving both intents:
   - Your original slice's behavior must still satisfy its acceptance criteria.
   - Whatever main introduced should not be lost.
   - If genuine semantic conflict (both can't be true), prefer your slice's
     intent and document the override in the log.
5. Run Tier 1 self-verification on the resolved state (same Ralph loop).
6. Append to the implementer log: what conflicts existed, how you resolved,
   what tradeoffs you made.
7. When self-verification passes: hand back to the Integrating workflow,
   which re-runs Tier 2 (acceptance + quality verification) on the integrated
   state.

**Critical:**
- The implementer-log is *your* internal narrative. The verifier does NOT see
  it. If it's not done in 3 fix cycles (per the fixer skill), this log gets
  compressed into the fixer's input.
- Don't surrender prematurely. The Ralph loop has no cap inside Tier 1; you
  loop until your checks pass or you're genuinely stuck. If genuinely stuck
  (after >10 failed self-loop iterations on the same test), post a "Stuck"
  comment and move sub-issue Status to Blocked.
- **In conflict-resolution mode, respect the conflict-resolution-cycles cap**
  (default 3, per `.harness/config.yml`). After 3 attempts at resolving the
  same conflict, escalate via Status=Verification Failed with a "merge conflict
  unresolved" comment.

**Output:** PR + sub-issue comment + Status update + implementer-log file.

**Failure modes:**
- Test infrastructure broken in container → post comment, mark Blocked.
- Container OOM → runner restarts; implementer can read the implementer-log
  to resume.
- (Conflict mode) main's changes fundamentally invalidate the slice → post
  comment requesting human decision, mark Verification Failed.

**Memory files read:** `memory/decisions/*.md`, `memory/guardrails.md`,
`memory/glossary.md`. (Note: deliberately NOT `memory/mistakes.md` —
implementer should be optimistic about the slice; mistakes-awareness is Phase
B's job.)

**Acceptance:** SKILL.md follows template, has worked examples for both
`mode: implement` and `mode: resolve-merge-conflict`. The conflict-resolution
example shows a non-trivial conflict (two slices that both touched the same
file in semantically-related ways) being resolved correctly.

### 3.10 Skill #9 — Acceptance verifier (Codex) — v0.2 split

**Path:** `skeleton/.codex/skills/verify-slice-acceptance/SKILL.md`

**Trigger:** "Invoked when sub-issue Status moves to Verifying-Acceptance.
Reads only the slice's acceptance criteria + the running env. Does NOT read
the implementer's log or tests. **This is the gating tier — failure halts
merge.**"

**Inputs:**
- Sub-issue body (acceptance criteria only)
- Live env URL (e.g., `t-001.harness.local`)
- Chrome MCP access

**Workflow (Q14 Tier 2 lock):**
1. Read acceptance criteria.
2. Generate own Chrome MCP test plan from criteria, ignoring how the
   implementer interpreted them.
3. Run tests against the live env.
4. Per criterion: pass | fail.
   - Pass: capture screenshot/log as evidence.
   - Fail: produce structured deficiency: criterion + observed behavior +
     expected behavior + reasoning.
5. Output a verification evidence comment on the sub-issue (ARTIFACTS.md §7
   acceptance template).
6. **If all pass:** Status → Verifying-Quality (next sub-state).
7. **If any fail:** Status → Fixing (cycle 1/3). Fixer skill triggers.

**Critical:** verifier's tests are NOT shared with the fixer. Only the
deficiency report is. (Q14 — fixer must independently arrive at a fix; if it
saw the verifier's tests, it would just satisfy them rather than fixing the
underlying problem.)

**Output:** structured evidence comment + Status update.

**Failure modes:**
- Live env unreachable → post comment, mark sub-issue Verification Failed
  with `harness:runner-error` label.
- Acceptance criteria unparseable → post comment requesting clarify-skill
  re-invocation on parent issue.

**Memory files read:** none (verifier is criterion-driven only).

**Acceptance:** SKILL.md follows template, has worked example showing
deficiency report with two failures and one pass.

### 3.11 Skill #10a — Codex code-quality verifier — NEW v0.2

**Path:** `skeleton/.codex/skills/verify-code-quality/SKILL.md`

**Trigger:** "Invoked when sub-issue Status moves to Verifying-Quality, IF
`.harness/config.yml` `verification.code_quality.primary == codex` OR
`mode == dual`. **Informational only — does not block merge.**"

**Inputs:**
- The PR diff (final state of all files changed in this slice)
- Sub-issue body (for slice context)
- Memory: `memory/guardrails.md`, `memory/decisions/*.md` (filtered by tags)

**Workflow:**
1. Read the diff with focus on Codex's strengths:
   - **Coupling:** are new dependencies introduced between modules that
     shouldn't depend on each other?
   - **Dead code:** is anything written that's never called?
   - **Leaky abstractions:** does the public surface expose internals?
   - **Test depth:** are tests checking real behavior or just structure?
   - **Error handling:** are failure paths handled or hand-waved?
   - **Dependency hygiene:** version pins, transitive risk, license fit.
   - **Static-analysis-flavored concerns:** anything `cargo clippy` /
     `eslint --strict` / `pyright` would flag if configured aggressively.
2. Per finding: severity (critical | major | minor) + category + file:line +
   suggestion.
3. Output as a structured comment on the sub-issue:
   `### Code-quality review (Codex)`.

**Output format:** ARTIFACTS.md §7 code-quality template.

**Critical — informational only:**
- This skill's findings do NOT change Status. After this skill runs (and the
  Claude variant if `mode: dual`), Status moves to Verified regardless of
  finding count. The human reviewer at the In Review stage decides what to do
  with the findings.
- The fixer skill receives these findings if and only if a Tier 2 acceptance
  failure occurred separately. Code-quality findings without acceptance
  failures stay informational until human review.

**Failure modes:**
- Diff is unreadable (binary files, very large) → produce a "Coverage
  partial" finding listing skipped files; continue with what's readable.
- Skill itself fails → post a "Code-quality verification skipped" comment
  with reason; do not block. (Informational means failure is also
  informational.)

**Memory files read:** `memory/guardrails.md` (so findings can cite
known-bad patterns), `memory/decisions/*.md` (so findings respect documented
choices like "we deliberately chose this coupling").

**Acceptance:** SKILL.md follows template, has worked example with three
findings of distinct severities and categories.

### 3.12 Skill #10b — Claude code-quality verifier — NEW v0.2

**Path:** `skeleton/.claude/skills/verify-code-quality/SKILL.md`

**Trigger:** "Invoked when sub-issue Status moves to Verifying-Quality, IF
`.harness/config.yml` `verification.code_quality.primary == claude` OR
`mode == dual`. **Informational only — does not block merge.**"

**Inputs:** same as Codex variant.

**Workflow:**
1. Read the diff with focus on Claude's strengths:
   - **Architectural fit:** does this slice's shape match how the rest of the
     project is organized?
   - **Naming clarity:** are new identifiers self-documenting?
   - **Simplicity vs cleverness:** is this simpler than it could be? More
     complex than it needs to be?
   - **Readability six months from now:** would a maintainer who's never seen
     this understand intent?
   - **Observability gaps:** logs, metrics, error context — would I be able
     to debug this in production?
   - **What this implies for adjacent code:** does this slice make the rest
     of the project worse by analogy?
2. Per finding: same shape as Codex variant.
3. Output as a structured comment on the sub-issue:
   `### Code-quality review (Claude)`.

**Critical:** The two code-quality verifiers (Codex and Claude) are
**deliberately tilted differently**. Codex's prompt is structural; Claude's
is architectural/readability. In `mode: dual`, this is the value — different
findings emerge that no single verifier would catch.

**Output format:** ARTIFACTS.md §7 code-quality template.

**Failure modes / Memory files read:** as Codex variant.

**Acceptance:** SKILL.md follows template; worked example shows different
findings than the Codex worked example (proving the tilt produces distinct
output).

### 3.13 Skill #11 — Slice fixer (Codex) — v0.2 updated input shape

**Path:** `skeleton/.codex/skills/fix-slice/SKILL.md`

**Trigger:** "Invoked when sub-issue Status moves to Fixing (cycle N/3 where
N≤3). Receives the verifier's deficiency report and a compressed implementer
log. Has no access to verifier's tests."

**Inputs (v0.2 expanded):**
- Sub-issue body
- Acceptance deficiency report from `verify-slice-acceptance` (mandatory if
  this skill is invoked)
- Code-quality reports from `verify-code-quality` runs (zero, one, or two
  reports depending on `.harness/config.yml`)
- Compressed implementer log (produced by Claude — see workflow)
- Cycle number (N/3)

**Workflow (Q14 fix-loop lock + v0.2 triage):**
1. Read the acceptance deficiency report. **This is the gating concern — it
   must be addressed.**
2. Read code-quality reports if present. **Triage rather than blindly fix:**
   for each code-quality finding:
   - Assess severity yourself.
   - Decide whether to address.
   - Document your decision per finding ("Addressing because X" / "Dismissing
     because Y").
3. You are NOT a tie-breaker between dual code-quality verifiers. If they
   flag different things, that's the value — both findings are real, they're
   complementary. Triage all of them together.
4. Read the compressed implementer log: "what was tried, what worked, what
   was abandoned, why." (Compression is done by a small Claude invocation
   between verifier and fixer. Implementer-log → bullet summary. The fixer
   does NOT see the full narrative.)
5. Implement changes addressing acceptance deficiencies + selected
   code-quality findings.
6. Run own Tier 1 self-verify (same Ralph loop as implementer skill).
7. When all self-checks pass: hand back to verifier (clean slate again).

**Cycle cap:** the runner enforces N≤3 (Q14 lock). On cycle 4 attempt, runner
halts the loop, marks sub-issue Verification Failed, escalates to user.

**Cycle override:** label `harness:fix-cycles=N` on the parent issue raises
the cap (Q20 — labels are attributes, this is one).

**Output:** updated PR + Status (back to Verifying-Acceptance for the next
verifier run) + per-finding decision log appended to implementer-log file.

**Failure modes:**
- Same deficiency persists across cycles → still loop until cap; the cap
  exists for exactly this case.
- Compression step fails (Claude unavailable) → fixer receives raw
  implementer log with a note; not ideal but not blocking.
- Code-quality findings contradict each other → fixer documents the
  contradiction in its decision log, picks the one that better serves the
  acceptance criteria, moves on.

**Memory files read:** `memory/guardrails.md` (in case the fix introduces a
known anti-pattern), `memory/decisions/*.md` filtered by issue tags.

**Acceptance:** SKILL.md follows template, has worked examples for cycle 1
and cycle 3 (different content depending on cycle), AND a worked example
showing dual-verifier fixer triage (two code-quality reports with overlapping
+ distinct findings).

### 3.14 Skill #12 — Lessons (quick + deep)

**Path:** `skeleton/.claude/skills/lessons/SKILL.md`

**Trigger:** "Invoked at issue/sub-issue terminal states (Done, Rejected,
Verification Failed-with-cap-hit), or via `/lessons-deep` comment. Two modes:
quick (always) and deep (conditional)."

**Inputs:**
- Parent issue body (final state)
- All sub-issue bodies (final state)
- Verifier reports (every cycle, both acceptance and code-quality)
- Implementer logs (full)
- Fixer logs (every cycle, if any)
- PR diffs
- Cross-slice regression report (if Final Validation produced one)
- Existing memory files in scope

**Workflow (Q15 lock):**

**Quick pass — always runs:**
1. Read all the inputs.
2. Produce a slice retrospective comment on the parent issue, one paragraph
   per slice that ran: what happened, what worked, what's worth knowing.
3. NO memory writes. NO proposals.

**Deep pass — runs only if:**
- Verifier caught any deficiency (any sub-issue had Fixing in its history),
  OR
- Final Validation caught a cross-slice regression, OR
- A PR was rejected by the user, OR
- User commented `/lessons-deep`.

If triggered:
1. Identify candidate memory entries by category:
   - **Mistakes:** what was tried and didn't work, with root cause.
   - **Guardrails:** "do not do X again" rules earned by failure.
   - **Decisions:** if a real architectural choice was made under pressure
     during the loop.
   - **Glossary:** if a domain term was clarified.
2. For each candidate, propose as a separate comment with:
   - The full proposed entry (frontmatter + body).
   - A "Tag rationale: ..." line explaining tag choices (Q13).
   - One-line reasoning for why this passes the bar.
3. **Bar for proposals (corpus discipline):**
   - Must be actionable in a hypothetical future issue.
   - Prefer superseding existing entries over creating new ones.
   - If you can't articulate which future issue would benefit, propose
     nothing.

**Critical NOT clauses:**
- Never propose new skills (corpus: skills earned by repetition or failure;
  one issue is not repetition).
- Never edit harness skeleton files (those go through a separate
  `harness:meta` issue).
- Never silently merge proposals (every write requires user 👍 reaction).

**Output:** retrospective comment (always) + zero or more proposal comments
(deep only).

**Failure modes:**
- No real lessons (smooth merge, deep pass triggered manually) → output
  "No lessons proposed; here is what happened" with the retrospective only.

**Memory files read:** all memory files in scope (lessons skill is the one
exception that reads broadly, because it's deciding what to write).

**Acceptance:** SKILL.md follows template, has worked example showing quick
pass output and deep pass with 2-3 proposals.

### 3.15 Phase 3 definition of done

- [ ] All 13 Layer 1 skills exist with full SKILL.md content
- [ ] Each follows the §3.1 template
- [ ] Each has at least one worked example
- [ ] The new v0.2 skills (`verify-slice-acceptance`, two `verify-code-quality`
      variants, updated `implement-slice` with mode parameter, updated
      `fix-slice` with multi-report triage) all have v0.2-specific worked
      examples
- [ ] Each declares its memory_files_read in frontmatter (so runner injection
      works)
- [ ] `_template.md` exists in both `.claude/skills/` and `.codex/skills/`
- [ ] `tests/` has a basic linter that validates each SKILL.md has the
      required sections

---

## Phase 4 — Skill libraries — Layer 2 ad-hoc

**Goal:** the four comment-triggered skills.

Per Q18: `/zoom-out`, `/design-an-interface`, `/grill-me`, `/write-a-skill`.

These are simpler than Layer 1 because they're invoked manually, in context,
and they don't have to fit a state-machine slot. They're free-form helpers.

### 4.1 `/zoom-out`

**Path:** `skeleton/.claude/skills/zoom-out/SKILL.md`

**Trigger:** comment-invoked via `/zoom-out <module-or-area>` on any issue.
Produces a map of the surrounding code: callers, callees, related concepts,
relevant ADRs.

**Workflow:**
1. Parse the area from the comment.
2. Produce a structured "map":
   - Files in the area
   - Who imports from this area (callers)
   - What this area imports from (callees)
   - Related concepts in `memory/glossary.md` and `memory/decisions/`
3. Post as a comment on the issue.

**Output format:** structured map comment (define template in skill).

**Acceptance:** SKILL.md exists with a worked example.

### 4.2 `/design-an-interface`

**Path:** `skeleton/.claude/skills/design-an-interface/SKILL.md`

**Trigger:** comment-invoked via `/design-an-interface <component>`.
Generates 2-3 distinct UI/API design options with pros/cons.

**Workflow:**
1. Parse the component description.
2. Generate 2-3 distinct designs (different paradigms, not just visual
   variants).
3. For each: sketch (text), pros, cons, when to choose this.
4. Post as a comment.

**Acceptance:** SKILL.md exists with a worked example showing 2-3 distinct
designs for a fictional component.

### 4.3 `/grill-me`

**Path:** `skeleton/.claude/skills/grill-me/SKILL.md`

**Trigger:** comment-invoked via `/grill-me <topic>`. Re-opens clarification
on a narrow topic without reverting the full plan.

**Workflow:**
1. Parse the topic from the comment.
2. Identify ambiguities specific to this topic (don't re-clarify resolved
   things outside the topic).
3. Post threaded questions on the topic, same format as the clarify skill.
4. Status DOES NOT auto-revert; this is a targeted reopener.
5. When questions resolve, the topic-specific findings get folded into the
   relevant body sections (Plan, Spec, etc.) via plan-finalize semantics.

**Acceptance:** SKILL.md exists; worked example shows targeted
re-clarification without full revert.

### 4.4 `/write-a-skill`

**Path:** `skeleton/.claude/skills/write-a-skill/SKILL.md`

**Trigger:** comment-invoked via `/write-a-skill <workflow-name>`. Helps
formalize a repeated workflow into a new SKILL.md following the §3.1
template.

**Workflow:**
1. Ask 3-5 clarifying questions about the workflow (when invoked, when not,
   what inputs, what outputs).
2. Draft the SKILL.md.
3. Post as a comment with the draft, plus a suggested file path.
4. User decides whether to add to repo (manual git operation).

**Critical:** this skill creates *project-level* skills, not harness-skeleton
skills. Skeleton skills go through a `harness:meta` issue (per Q15).

**Acceptance:** SKILL.md exists; worked example shows a fictional workflow
turning into a draft skill.

### 4.5 Phase 4 definition of done

- [ ] All 4 Layer 2 skills exist
- [ ] Each follows the §3.1 template
- [ ] Each has a worked example
- [ ] Each declares its trigger pattern as a regex/string match for the
      runner's comment dispatcher

---

## Phase 5 — Container substrate and runner integration

**Goal:** the Docker Compose template, the agent images, the reverse proxy,
and the per-issue lifecycle.

This phase is pure infrastructure — it produces the substrate the runner
workflows (Phase 6) will use.

### 5.1 The agent Dockerfile

**Path:** `skeleton/docker/agent.Dockerfile`

**What:** a single image with both Claude Code CLI and Codex CLI installed,
plus shell tooling, git, gh CLI, jq, ripgrep, the project's primary language
toolchain (rendered at bootstrap based on the project's primary-language
answer).

**Why:** Q11 lock — agents run inside the container, host unreachable. The
image is the trusted runtime.

**Required contents:**
- Base: `ubuntu:24.04` or `debian:stable-slim` (Mac-host friendly)
- `git`, `gh`, `jq`, `ripgrep`, `curl`, `bash`, `make`
- Claude Code CLI (installed via official installer)
- Codex CLI (installed via official installer)
- Chrome (headless, for Chrome MCP) — installed but not run by default
- Project-specific toolchain (rendered): `node`, `python`, `rust`, etc.
- Working dir: `/workspace`
- Non-root user `agent` for the CLI invocation

**Auth injection:** at runtime, the runner mounts:
- `~/.claude` from host → `/home/agent/.claude` (read-only)
- `~/.codex` from host → `/home/agent/.codex` (read-only)
- A short-lived GitHub App installation token via env var `GH_TOKEN`

**Acceptance:** image builds, `claude --version` and `codex --version` both
work inside a container started from it.

### 5.2 The Compose stack template

**Path:** `skeleton/docker/docker-compose.harness.yml.tpl`

**What:** the per-issue stack (Q11). Rendered per issue with the issue ID as
suffix on every service name.

**Required services:**
1. `agent-{{issue_id}}`: built from `agent.Dockerfile`. Worktree mounted at
   `/workspace`. Connected only to the internal network.
2. `app-{{issue_id}}`: the project's app server (Dockerfile rendered from
   project's existing dev image; bootstrap asks for path).
3. `db-{{issue_id}}`: the database (postgres/mysql/etc., based on bootstrap
   answer). Volume per stack, ephemeral. Seeded from `fixtures/golden.sql.gz`
   on start.
4. `redis-{{issue_id}}` (optional, based on bootstrap): same shape.

**Networking:**
- Internal Docker network per stack (`harness-{{issue_id}}`).
- Host network unreachable from any service (no `host.docker.internal`,
  no port-publishing to host of services that shouldn't be reachable).
- One published port: the app's port via the reverse proxy (see 5.3).
- Outbound internet: allowed from agent (for Claude/Codex API), allowed from
  app (might need NPM/PyPI), explicitly disabled for db.

**Critical:** the `agent` service has `--dangerously-skip-permissions` (or
Codex equivalent) set; the `db` service has explicit "no outbound" via Docker
network policies.

**Acceptance:** template renders for a sample issue, `docker compose up`
spins up all services, agent can `curl https://api.anthropic.com` but cannot
reach `host.docker.internal:5432` (your real DB).

### 5.3 Reverse proxy

**Path:** `skeleton/docker/proxy/`

**What:** a Caddy or Traefik config that maps `issue-{{N}}.harness.local` →
the corresponding stack's app service. One persistent proxy container running
on the runner host, picking up new stacks via labels.

**Why:** Q11 — you and Chrome MCP both visit issue envs by URL. URLs need to
be stable and meaningful.

**Required content:**
- Caddyfile or Traefik config that matches Compose service labels.
- Documentation of how `harness.local` resolves (entry in `/etc/hosts` or a
  wildcard DNS entry; documented in `scripts/setup/install-runner.md`).

**Acceptance:** a stack with `harness.app=true` label is reachable at
`issue-42.harness.local` from your laptop browser.

### 5.4 The fixtures dance

**Path:** `skeleton/scripts/fixtures/` plus a workflow.

**What:** the sanitized golden DB dump mechanism (Q11).

**Components:**
- `scripts/fixtures/refresh.sh` — pulls from real staging/prod, runs scrub
  script, writes `fixtures/golden.sql.gz`. Configured via
  `.harness/config.yml`.
- `scripts/fixtures/scrub.example.sh` — template scrub script that strips PII;
  user customizes per project.
- `.github/workflows/refresh-fixtures.yml` — runs weekly via cron, executes
  `refresh.sh`, commits the new `fixtures/golden.sql.gz` to a fixtures
  branch. PR opened for human review before merging (you don't auto-update
  fixtures without review).

**Acceptance:** `scripts/fixtures/refresh.sh --dry-run` prints what it would
do without doing it. Workflow file passes `gh workflow view`.

### 5.5 Stack lifecycle helpers

**Path:** `skeleton/scripts/stack/`

**What:** small bash helpers used by workflows:
- `stack/up.sh <issue-id>`: render Compose template, start the stack, wait
  for healthchecks, print the URL.
- `stack/down.sh <issue-id>`: tear down stack, remove volumes, remove
  worktree, delete branch.
- `stack/list.sh`: show all running stacks.
- `stack/orphan-cleanup.sh`: find stacks without a corresponding open
  sub-issue (or whose sub-issue has been Done/Rejected for >24h) and tear
  them down. Run nightly via cron workflow.
- **NEW v0.2:** `stack/up-final-validation.sh <parent-issue-id>` — spins a
  fresh stack on `main` HEAD specifically for the Final Validation step. No
  worktree mount; uses `main` directly. Tears down on completion.

**Why:** Q20 lock — stacks tear down on terminal Status, plus nightly orphan
cleanup. These scripts are the implementation. v0.2 adds the Final Validation
variant.

**Acceptance:** each script has `--help`, runs without error in a dry-run
mode, has at least one test in `tests/`.

### 5.6 Phase 5 definition of done

- [ ] `agent.Dockerfile` builds and contains both CLIs
- [ ] Compose template renders and stacks come up cleanly for a sample issue
- [ ] Reverse proxy resolves `issue-N.harness.local` to the right service
- [ ] Fixtures refresh script and workflow exist
- [ ] Stack lifecycle helpers exist with `--help` and dry-run modes
- [ ] `up-final-validation.sh` exists and can spin a stack on `main` HEAD
      (without a worktree) for cross-slice testing
- [ ] All scripts pass shellcheck

---

## Phase 6 — Workflows and state machine

**Goal:** the GitHub Actions workflows that wire the Status transitions to the
right runner actions.

This is where the design gets *operational*. Per Q20: Status is canonical;
labels are attributes; one workflow per Status transition. v0.2 adds two new
state transitions (Integrating, Final Validation) and the verification split.

### 6.1 The Status state machine, formally — v0.2

**Path:** `docs/state-machine.md`

**What:** a single doc with the full diagram (or table) of all Status
transitions for both parent and sub-issues.

#### Parent issue states & transitions (v0.2)

| From | To | Trigger | Workflow |
|------|----|---------|----------|
| (none) | Draft | issue created | `on-issue-create.yml` |
| Draft | Researching | auto, immediately after Draft | `on-issue-create.yml` (chained) |
| Researching | Clarifying | both Phase A research + synthesis complete | `on-synthesis-complete.yml` |
| Clarifying | (Plan Ready or skips through) | user drag past Clarifying | `on-status-change.yml` |
| Clarifying | Critiquing | auto when last open question resolved | `on-question-resolved.yml` |
| Critiquing | Plan Ready | plan-finalize completes (fold case) | `on-plan-finalize.yml` |
| Critiquing | Clarifying | plan-finalize completes (escalate case) | `on-plan-finalize.yml` |
| Plan Ready | Ready for Work | user drag (the approval gesture) | `on-status-change.yml` |
| Ready for Work | In Progress | auto, after slice fanout | `on-fanout-complete.yml` |
| In Progress | In Review | aggregate from sub-issues (any in In Review, none Implementing) | `on-subissue-status.yml` |
| In Review | **Final Validation** | **NEW v0.2: aggregate (all sub-issues Merged)** | `on-subissue-status.yml` |
| **Final Validation** | **Done** | **NEW v0.2: cross-slice verification all-pass** | `on-final-validation.yml` |
| **Final Validation** | **Verification Failed** | **NEW v0.2: cross-slice regression detected** | `on-final-validation.yml` |
| In Progress | Verification Failed | aggregate (any sub-issue Verification Failed) | `on-subissue-status.yml` |
| Verification Failed | Ready for Work | user drag (after updating guardrails) | `on-status-change.yml` |
| any | Rejected | user drag | `on-status-change.yml` |
| any | Blocked | user drag (or runner sets, on missing-secrets etc.) | various |

13 parent states (was 12 in v0.1; Final Validation is new).

#### Sub-issue (slice) states & transitions (v0.2)

| From | To | Trigger |
|------|----|---------|
| (none) | Queued | sub-issue created via fanout |
| Queued | Implementing | scheduler picks up (concurrency permits) |
| Implementing | Self-Verified | implementer skill completes successfully |
| Self-Verified | Verifying-Acceptance | auto (acceptance verifier triggered) |
| Verifying-Acceptance | **Verifying-Quality** | **v0.2: acceptance all-pass** |
| **Verifying-Quality** | **Verified** | **v0.2: code-quality verification(s) complete (always pass — informational)** |
| Verified | **Integrating** | **v0.2: auto (merge from main)** |
| **Integrating** | **In Review** | **v0.2: clean integration, acceptance + quality re-verified on integrated state** |
| **Integrating** | Implementing | **v0.2: conflicts detected, same implementer re-spawned with `mode: resolve-merge-conflict`** |
| In Review | Merged | user merges PR |
| Verifying-Acceptance | Fixing | acceptance verifier any-fail (cycle 1/3) |
| Fixing | Verifying-Acceptance | fixer self-verify passes (next cycle) |
| Fixing | Verification Failed | cycle cap hit |
| **Integrating** | **Verification Failed** | **v0.2: conflict resolution cap hit** |
| In Review | Rejected | user closes PR + drags Status to Rejected |
| any | Blocked | runner sets on stuck conditions |

11 sub-issue states (was 9 in v0.1; Verifying-Quality and Integrating are new).

**Acceptance:** doc exists, every cell of the table is implementable (no
hand-waved triggers).

### 6.2 The workflows — v0.2

**Path:** `skeleton/.github/workflows/`

One file per major trigger. Workflows are layers of orchestration; they call
into scripts and skills, not implement logic inline.

**Required workflows (v0.2 — 24 total):**

1. **`on-issue-create.yml`** — fires on `issues.opened`.
   - Sets Status = Draft.
   - Sets Status = Researching.
   - Triggers Phase A research (Claude + Codex in parallel containers).
2. **`on-phase-a-complete.yml`** — fires when both Phase A comments posted.
   Detected by a parser on `issue_comment.created` events with comment matching
   the Phase A output template.
   - Triggers synthesis.
3. **`on-synthesis-complete.yml`** — fires when synthesis comment posted.
   - Sets Status = Clarifying.
   - Triggers clarify skill in initial-post mode.
4. **`on-question-replied.yml`** — fires on `issue_comment.created` if the
   comment is a reply to an open threaded question.
   - Triggers clarify skill in reply mode.
5. **`on-status-change.yml`** — fires on Project field change. Routes:
   - Clarifying → Plan Ready: trigger plan-and-slice + Phase B critique +
     plan-finalize chain. Auto-accept open questions first.
   - Plan Ready → Ready for Work: trigger slice fanout.
   - Verification Failed → Ready for Work: re-fanout (or specific slice
     re-trigger if the user labels which slice).
   - any → Rejected: lessons skill (deep pass), tear down stacks.
6. **`on-question-resolved.yml`** — fires when last open question is resolved.
   - If Status is Clarifying, optionally auto-advance to Plan Ready
     (configurable).
7. **`on-plan-finalize.yml`** — internal trigger after plan-finalize skill
   completes.
   - Fold case: Status stays Plan Ready.
   - Escalate case: Status → Clarifying.
8. **`on-fanout-complete.yml`** — internal trigger after slice fanout creates
   sub-issues.
   - Status (parent) → In Progress.
   - First sub-issue Status → Implementing (if concurrency=1).
9. **`on-subissue-status.yml`** — fires on sub-issue Status changes.
   - Recompute parent Status based on aggregate.
10. **`on-subissue-implementing.yml`** — fires when sub-issue Status →
    Implementing.
    - Spin up Compose stack via `stack/up.sh`.
    - Trigger implement-slice skill in container in `mode: implement` (default)
      OR `mode: resolve-merge-conflict` (if invoked from the Integrating
      workflow).
11. **`on-subissue-self-verified.yml`** — fires when sub-issue Status →
    Self-Verified.
    - Trigger verify-slice-acceptance skill (same stack, fresh agent
      invocation).
12. **`on-subissue-verifying-acceptance-result.yml`** — internal trigger after
    acceptance verifier completes.
    - All-pass: Status → Verifying-Quality.
    - Any-fail with cycle < cap: Status → Fixing, trigger fixer.
    - Any-fail at cap: Status → Verification Failed.
13. **NEW v0.2: `on-quality-verifier-config.yml`** — fires when sub-issue
    Status → Verifying-Quality.
    - Reads `.harness/config.yml` `verification.code_quality` block.
    - Dispatches Codex code-quality verifier and/or Claude code-quality
      verifier per `mode` (single or dual).
    - On all dispatched verifiers complete: Status → Verified. (Code-quality
      findings do NOT change Status outcome — they are informational.)
14. **NEW v0.2: `on-integrating.yml`** — fires when sub-issue Status →
    Integrating.
    - In the slice's existing stack: `git fetch origin main && git merge
      origin/main`.
    - **No conflicts:** re-run verify-slice-acceptance + quality verifier(s)
      on integrated state.
      - All pass → Status → In Review.
      - Acceptance fail → Status → Fixing (cycle counter starts fresh, since
        this is a different cause from the original implementation).
    - **Conflicts:** Status → Implementing with input flag
      `mode: resolve-merge-conflict`. Same implementer skill, same container,
      same warm context. Cycle cap = `conflict_resolution_cycles_cap` from
      `.harness/config.yml` (default 3).
    - **Resolution cap hit:** Status → Verification Failed with "merge
      conflict unresolved" comment.
15. **`on-pr-merged.yml`** — fires on `pull_request.closed && merged`.
    - Sub-issue Status → Merged.
    - Tear down stack via `stack/down.sh`.
    - Trigger lessons quick pass.
    - Recompute parent Status (may move to In Review or Final Validation).
16. **`on-pr-rejected.yml`** — fires on `pull_request.closed && !merged`.
    - Sub-issue Status → Rejected.
    - Tear down stack.
    - Trigger lessons deep pass.
17. **NEW v0.2: `on-final-validation.yml`** — fires when parent Status → In
    Review AND all sub-issues are Merged.
    - Sets parent Status → Final Validation.
    - Spins fresh stack on `main` HEAD via `stack/up-final-validation.sh`.
    - Invokes verify-slice-acceptance skill in `mode: cross-slice` against
      the parent issue's full Verification Plan (every criterion across every
      slice).
    - **All pass:** parent Status → Done. Lessons quick pass on parent.
    - **Any fail:**
      - parent Status → Verification Failed.
      - Auto-create issue labeled `harness:cross-slice-regression` linked to
        the originating slices, with the cross-slice regression report
        embedded.
      - Lessons deep pass on parent (the cross-slice failure is exactly the
        signal lessons should learn from).
18. **`on-comment-command.yml`** — fires on `issue_comment.created` with body
    matching `/zoom-out|/design-an-interface|/grill-me|/write-a-skill|/lessons-deep`.
    - Routes to the matching Layer 2 skill.
19. **`dashboard-tick.yml`** — cron, every 15 min.
    - Reads metrics + open issues, regenerates the pinned status issue.
20. **`memory-reindex.yml`** — fires on push to memory/.
    - Regenerates `memory/index.json`.
21. **`fixtures-refresh.yml`** — cron, weekly.
    - Triggers `scripts/fixtures/refresh.sh`, opens PR.
22. **`orphan-cleanup.yml`** — cron, nightly.
    - `scripts/stack/orphan-cleanup.sh`.
23. **`memory-prune.yml`** — manual trigger only.
    - Surfaces archive candidates per Q15.
24. **`harness-meta.yml`** — fires on issues created with template `meta.yml`
    (skeleton-change-request issues). Routes them through the same
    Phase A/Phase B/etc. flow but against the harness skeleton repo itself.
    Optional in v0.2 (defer to v0.3 if Phase 8 doesn't surface a need).

**For each workflow:** include `concurrency` group declarations to prevent
double-firing, `permissions` blocks limited to needed scopes, and use the
GitHub App installation token (not `GITHUB_TOKEN`) for cross-issue
operations.

**Acceptance:** all workflow files exist and pass `gh workflow view`. None
fire on `push` to `main` directly except memory-reindex.

### 6.3 The Status helper

**Path:** `skeleton/scripts/lib/gh-status.sh`

**What:** a small bash function that does GraphQL mutations to set Status field
on issues.

**Why:** Q20 — REST API doesn't fully support Project v2 field mutations;
GraphQL does.

**Functions:**
- `gh_status_get <issue-number>` → prints current Status
- `gh_status_set <issue-number> <new-status>` → mutates
- `gh_status_options` → lists allowed Status values (used by validation)

**v0.2 update:** the option list now includes Final Validation,
Verifying-Acceptance, Verifying-Quality, and Integrating.

**Acceptance:** script exists, has unit tests in `tests/`.

### 6.4 The setup-project.sh script — v0.2 updated

**Path:** `skeleton/scripts/setup/setup-project.sh`

**What:** one-time script run during bootstrap to create the GitHub Project
board with the right Status field options.

**Why:** Q20 — the Project board's Status field options are not built-in;
they need explicit configuration matching the §6.1 state machine.

**Workflow:**
1. Ask which Project to use (existing or create new).
2. Add custom Status field with all 13 parent states (v0.2 includes Final
   Validation).
3. Add a separate Sub-issue Status field with 11 sub-issue states (v0.2
   includes Verifying-Acceptance, Verifying-Quality, Integrating).
4. Add Risk field (single-select: fast-patch | planned | high-risk).
5. Add Phase field (auto-derived from Status; informational).
6. Verify field IDs and write them to `.harness/config.yml`.

**Acceptance:** running it on a fresh repo produces a board ready for
the workflows to write to. Idempotent (running twice doesn't break).

### 6.5 Phase 6 definition of done

- [ ] `docs/state-machine.md` exists and is implementable
- [ ] All 24 workflow files exist (or 23 if `harness-meta.yml` deferred)
- [ ] `scripts/lib/gh-status.sh` exists with tests, includes v0.2 status options
- [ ] `scripts/setup/setup-project.sh` exists and is idempotent, includes v0.2
      states
- [ ] Workflows can be linted with `actionlint`

---

## Phase 7 — Bootstrap and upgrade scripts

**Goal:** the user-facing entry points to the harness.

### 7.1 `bootstrap/init.sh`

**What:** the curl-piped bootstrap script (Q16).

**Workflow:**
1. Verify target dir is a git repo with no uncommitted changes (corpus
   invariant: dirty worktree check).
2. Verify required tooling installed: `git`, `docker`, `gh`, `jq`. If
   missing, print install instructions and exit.
3. Ask 5 questions:
   - Project name
   - Primary language (offers: node, python, rust, go, other)
   - Dev port (default 3000)
   - GitHub repo slug (auto-detected if `gh repo view` works)
   - Database (offers: postgres, mysql, none)
4. **NEW v0.2: Ask 1 verification question:**
   - Code-quality verification mode (offers: single-codex [default],
     single-claude, dual)
   - Renders into `.harness/config.yml`.
5. Clone skeleton repo into a temp dir at the version pinned in the bootstrap
   script (so curl-pipe-bash is reproducible across time).
6. Render `.tpl` files with answers (use `envsubst` or a small handlebars
   shim).
7. Copy rendered files into target, refusing to overwrite existing files.
8. Write `.harness-version` with skeleton commit SHA + version + render time.
9. Initial commit on a `harness/init` branch.
10. Print next-step instructions:
    - Install GitHub App (URL)
    - Register self-hosted runner (URL + token)
    - Run `setup-project.sh` to create Project board
    - File first issue

**Critical:**
- Single bash file, no Node/Python required.
- Auditable — you can `curl ... | cat | bash`.
- Pinned version — script downloads a specific tag, not `main`.

**Acceptance:** running `bash init.sh` against a fresh repo produces a
ready-to-use harness setup. All template variables are substituted correctly,
including the new v0.2 `verification.code_quality` config.

### 7.2 `bootstrap/upgrade.sh`

**What:** the 3-way merge upgrade script (Q16).

**Workflow:**
1. Read `.harness-version` to find the skeleton commit currently installed.
2. Fetch the latest skeleton release.
3. Compute the diff between installed-version and latest-version of every
   skeleton file.
4. Apply diffs as patches to the target.
5. Surface conflicts as merge markers. User resolves manually.
6. On user commit, update `.harness-version`.

**v0.2 specific:** upgrade from v0.1.x to v0.2.x must:
- Add new Status options to existing Project boards (via `gh-status.sh`).
- Add `.harness/config.yml` with default values if missing.
- Add the new v0.2 skill files.
- Document the integration-state and final-validation flow in
  `docs/upgrade-guide.md`.

**Acceptance:** can upgrade from v0.1.0 to v0.2.0 (with a synthetic test case
in `tests/`) without losing user customizations to non-skeleton files.

### 7.3 `scripts/harness` (the per-project CLI)

**What:** the harness's own CLI, copied into target projects via bootstrap.

**Commands:**
- `harness next` — manual fallback for triggering the next ready slice (Q5).
- `harness status` — read JSONL metrics + GitHub state, print summary (Q19).
- `harness stack list | up <issue> | down <issue>` — wraps `scripts/stack/*`.
- `harness memory query <tag>` — read `index.json` and dump matching entries
  (debug helper).
- `harness reindex` — manually regenerate `memory/index.json`.
- `harness lint` — run all `tests/lint-*.sh` against the project's harness
  files.
- `harness upgrade` — calls `bootstrap/upgrade.sh`.
- **NEW v0.2: `harness verify-config`** — print effective verification config
  (mode, primary, etc.) so you can confirm what's set.

**Acceptance:** all commands have `--help`, runnable from any subdir of the
project, exit codes meaningful.

### 7.4 Phase 7 definition of done

- [ ] `init.sh` works on a fresh repo, including v0.2 verification-mode question
- [ ] `upgrade.sh` survives a synthetic v0.1 → v0.2 upgrade test
- [ ] `scripts/harness` CLI has all listed commands including
      `verify-config`
- [ ] All scripts pass shellcheck
- [ ] Documentation in `docs/upgrade-guide.md` covers v0.1 → v0.2 migration

---

## Phase 8 — First-issue dogfood on real project

**Goal:** validate end-to-end on your actual project. This is where the
abstract design meets reality and reveals what we got wrong.

### 8.1 Bootstrap into your project

1. Cleanup: ensure your real project has no uncommitted changes.
2. Run `curl -fsSL .../init.sh | bash` against the project root.
3. Review the diff on the `harness/init` branch.
4. Merge.
5. Install the GitHub App on the project repo.
6. Register the runner on your Mac. Verify `gh actions runners list` shows
   it as `online`.
7. Run `bash scripts/setup/setup-project.sh` to create the Project board.
8. Commit the `.harness/config.yml` produced by setup.
9. **Sanity-check verification config:** `harness verify-config` prints
   `mode: single, primary: codex` (or whatever you chose).

**Acceptance:** project has all skeleton files; runner is online; Project
board exists with correct Status field options for both parent and
sub-issues.

### 8.2 File the first real issue

Pick something **small and self-contained** for issue #1. The corpus warning
is explicit: *"Do not automate until friction is visible"* — your first issue
should be smooth-path, low-risk. A micro-feature, a UI tweak, a small
refactor. NOT auth, NOT db migrations, NOT the centerpiece of the project.

Bad first issues: "rewrite the auth system," "migrate the db," "add
multi-tenancy."
Good first issues: "add a 'Cancel' button to the settings modal," "fix typo
on landing page hero," "add export-to-CSV on the dashboard."

**v0.2-specific dogfood targets:** ideally pick a first issue whose work could
plausibly produce 2+ slices that touch overlapping files (so the Integrating
state actually exercises). If your first issue is naturally single-slice,
that's fine — the second issue should exercise multi-slice integration.

File it. Watch what happens. Take notes on every moment of friction.

### 8.3 Capture the friction

Create `docs/v0.2-dogfood-notes.md` in the harness skeleton repo. As you watch
issue #1 flow, write down:
- Where you waited longer than felt right
- Where the agent output looked wrong
- Where you wished you could see something but couldn't
- Where the structured comments were noisy vs informative
- What broke, with full reproduction details
- **NEW v0.2 specifically watch for:**
  - Did Final Validation catch anything? Did it false-positive?
  - Did Integrating's merge resolution work, or did it loop unproductively?
  - Were code-quality verifier comments useful or noise? Did findings overlap
    with each other (in dual mode) or each contribute distinct value?

This document becomes the input to v0.3 of the skeleton.

### 8.4 The first lesson

Whatever the issue's outcome — merged smoothly, rejected, stuck mid-loop —
the lessons skill will fire. Review its quick-pass output. If a deep pass
fired, review the proposals. If you don't 👍 anything, that's data: the
lessons skill bar is too low or too high.

The corpus invariant: **memory must be earned.** If you find yourself merging
proposals just because they're posted, you're seeding a junk drawer. Be
ruthless.

### 8.5 Phase 8 definition of done

- [ ] One real issue has flowed all the way from `Draft` to `Done` (or
      `Rejected` — that's also valid)
- [ ] `docs/v0.2-dogfood-notes.md` has at least 5 friction observations,
      including at least 1 v0.2-specific observation (Final Validation,
      Integrating, or code-quality verification)
- [ ] At least one lessons proposal was made (👍 or 👎 doesn't matter)
- [ ] You've identified the v0.3 priorities

---

## 4. Cross-cutting concerns

These are properties that span phases and must be checked throughout.

### 4.1 Idempotency

Every script that mutates state (init, upgrade, setup-project, stack/up,
stack/down, reindex) must be idempotent. Running twice should not break
anything. This is critical for the runner — workflows can re-fire on retry.

**Implementer test:** for every mutating script, write a test that runs it
twice and verifies the second run is a no-op.

### 4.2 Observability hooks

Every workflow should write a JSONL line to `.harness/metrics/` recording:
- timestamp
- workflow name
- issue/sub-issue number
- duration
- outcome (success | failure | partial)
- relevant metric (e.g., for invocations: token count if available)

**v0.2 additions to JSONL schema:**
- For `on-quality-verifier-config.yml`: which verifier(s) ran, finding count
  per severity, mode (single | dual).
- For `on-integrating.yml`: clean-merge | conflict | conflict-resolved |
  conflict-cap-hit; cycle count if conflict.
- For `on-final-validation.yml`: cross-slice criterion count, pass count,
  fail count, regression-issue-created (boolean).

This is what `harness status` reads. Without this, the dashboard issue is
empty. (Q19)

### 4.3 Error surfacing

All runner failures result in either:
- A comment on the relevant issue describing what failed and why
- A `harness:runner-error` label on the issue
- A line in `.harness/metrics/runner-errors.jsonl`

No silent failures. (Q20 implicit gap from §20.5)

### 4.4 Cost guard rails

Even though Q17 explicitly defers cost optimization, four guards are in v0.2
because they're cheap and catch runaway loops:

1. **Max concurrent stacks: 4** — hard cap regardless of label overrides.
2. **Max sub-issues per parent: 12** — hard cap to prevent fanout
   explosions.
3. **Max comments per workflow run: 20** — hard cap to prevent agent loops
   that spam comments.
4. **NEW v0.2: Max conflict-resolution cycles: 3** (configurable in
   `.harness/config.yml`, but capped at 5 even if user raises). Same Ralph-cap
   discipline as Q14, applied to the merge-resolution mode of the implementer
   skill.

Each guard surfaces via `harness:runner-error` if hit.

### 4.5 Documentation discipline

Every workflow file has a top-of-file comment:
- Trigger
- Inputs (event payload it cares about)
- Outputs (state changes it makes)
- Failure modes

Every script has a `--help` flag.

Every skill has a worked example.

This is the corpus's *"every skill must include examples"* applied uniformly.

---

## 5. Versioning and release discipline

### 5.1 Version semantics

- `0.0.x` — pre-v1, anything goes.
- `0.x.0` — v1 is `1.0.0`. Pre-1.0 minor bumps may break templates.
- `1.x.y` — semver: y is bug fix, x is feature, 1.x → 2.x is breaking.

### 5.2 Release ritual

Each release:
1. Bump VERSION
2. Update CHANGELOG.md with structured entries (added | changed | removed |
   fixed)
3. Tag the commit (`v0.2.0`)
4. Run `tests/` in CI; release blocked if any fail
5. If breaking changes for bootstrapped projects: write an upgrade note

### 5.3 v0.1 → v0.2 → v1.0 roadmap

- **v0.1.0:** baseline plan with single verification, no Integrating, no
  Final Validation. Superseded by v0.2.
- **v0.2.0 (this plan):** verification split, Integrating state, Final
  Validation state, dual-verifier config option. Phase 1-8 complete.
  Dogfooded on one real project.
- **v0.3.0:** v0.2 minus rough edges from §8.3 dogfood notes. No new
  features. May add `harness-meta.yml` workflow if Phase 8 surfaces need.
- **v0.4.0:** add `/improve-architecture` skill if §8.3 reveals it's missing.
- **v0.5.0:** swappable executor shim (Q11b). Gemini lands in the verifier
  slot specifically for `harness:risk-high` issues (doctrine #9).
- **v0.6.0:** observability dashboard (Q19's deferred B option).
- **v1.0.0:** stable. Version 2.0 features (hybrid memory upgrade, multi-
  agent swarm, etc.) live in a separate roadmap.

---

## 6. What this plan deliberately does not include

To prevent scope creep, here is what is **out** of v0.2:

- Hybrid memory layer (SQL + graph + compiled wiki). Markdown only. (Q13
  lock — Phase 5 in corpus blueprint.)
- Multi-agent swarm orchestration beyond the planner/researcher/critic
  pattern. (Q3, corpus Phase 7.)
- Gemini integration. (Q3 lock — deferred to v0.5 in the verifier slot per
  doctrine #9.)
- Observability dashboard with charts. (Q19 lock — pinned issue only,
  deferred to v0.6.)
- Embeddings or semantic retrieval. (Q13 lock — markdown grep first.)
- API-key executor for shared team runners. (Q11b — design ready, defer
  implementation to v0.5.)
- Code-quality findings that block merge. (v0.2 lock: informational only;
  blocking-by-severity is a v0.5 feature once you've seen real findings.)
- Auto task-splitting at stuck threshold (file 04's idea, deliberately
  rejected — too clever for v0.2).
- `/improve-architecture` skill. (Q18.)
- Conditional skills (`domain-model`, `ubiquitous-language`, etc.). (Q18.)
- Auto-retry on PR rejection. (Q10 — explicit anti-pattern.)
- Anything that would require a hosted service. (Everything runs on the
  developer's Mac or in their GitHub repo.)

If during build any of these feels tempting, the answer is *"no, ship v0.2
first."* The corpus warning that applies: *"Do not automate until friction
is visible."*

---

## 7. Quick action checklist (for handing to the implementer)

If you want a one-screen checklist to give an AI implementer, here it is.
Each line is a milestone. They must be done in order.

**Phase 1 — Skeleton (~3h)**
- [ ] Create `aiharness` repo
- [ ] Lay down directory structure per §1.2 (including `.harness/config.yml.tpl`)
- [ ] Write skeleton's own root `AGENTS.md`
- [ ] Tag v0.0.1

**Phase 2 — Contracts (~5h)**
- [ ] Write `AGENTS.md.tpl` (≤120 lines)
- [ ] Write `ARTIFACTS.md.tpl` with v0.2 split verification templates and
      cross-slice regression report template
- [ ] Write `prompts/shared/` files (3 files)
- [ ] Write `memory/README.md` and the four memory file headers
- [ ] Write `CLAUDE.md.tpl` and `CODEX.md.tpl`
- [ ] **NEW v0.2:** Write `.harness/config.yml.tpl` with verification block
- [ ] Tag v0.0.2

**Phase 3 — Layer 1 skills (~12h)**
- [ ] Write `_template.md` in both libraries
- [ ] Write skills #1-7 (research, synthesis, clarify, plan-and-slice,
      plan-critique with v0.2 expanded categories, plan-finalize)
- [ ] Write skill #8 with v0.2 dual-mode (`mode: implement` and
      `mode: resolve-merge-conflict`)
- [ ] Write skill #9 (verify-slice-acceptance, the gating tier)
- [ ] **NEW v0.2:** Write skills #10a (Codex code-quality) and #10b (Claude
      code-quality), with deliberately distinct prompt tilts
- [ ] Write skill #11 (fixer) with v0.2 multi-report triage input shape
- [ ] Write skill #12 (lessons)
- [ ] Tag v0.0.3

**Phase 4 — Layer 2 skills (~3h)**
- [ ] Write all 4 Layer 2 skills with worked examples
- [ ] Tag v0.0.4

**Phase 5 — Containers (~10h)**
- [ ] Write `agent.Dockerfile`
- [ ] Write `docker-compose.harness.yml.tpl`
- [ ] Write reverse proxy config
- [ ] Write fixtures dance
- [ ] Write stack lifecycle helpers, including v0.2's `up-final-validation.sh`
- [ ] Tag v0.0.5

**Phase 6 — Workflows (~10h)**
- [ ] Write state machine doc with 13 parent + 11 sub-issue states
- [ ] Write all 24 workflow files (or 23 if `harness-meta.yml` deferred)
- [ ] Specifically write the 3 NEW v0.2 workflows: `on-integrating.yml`,
      `on-final-validation.yml`, `on-quality-verifier-config.yml`
- [ ] Write `gh-status.sh` helper with v0.2 status options
- [ ] Write `setup-project.sh` with v0.2 sub-issue Status field
- [ ] Tag v0.0.6

**Phase 7 — Bootstrap (~3h)**
- [ ] Write `init.sh` with v0.2 verification-mode question
- [ ] Write `upgrade.sh` (specifically test v0.1 → v0.2 path)
- [ ] Write `harness` CLI with all subcommands including `verify-config`
- [ ] Tag v0.0.7

**Phase 8 — Dogfood (~3h)**
- [ ] Bootstrap into your project
- [ ] File first real issue
- [ ] Watch and document friction (with v0.2-specific observations)
- [ ] Tag v0.2.0

---

## 8. Appendix — every Q lock and where it's implemented

| Q | Lock | Implemented in phase / file |
|---|------|-----|
| Q1 | Reusable pattern | Whole plan; Phase 8 dogfoods on real project |
| Q2 | Skeleton repo + bootstrap + skill installs | Phases 1, 7 |
| Q3 | Claude=plan/synthesis, Codex=research/critique/implement | Phase 3 skills |
| Q4 | GitHub Issues + structured body | §2.2 (ARTIFACTS.md), Phase 6 workflows |
| Q5 | Self-hosted runner + `harness next` | Phase 5 docs, §7.3 CLI |
| Q6 | Per-issue Compose stack | Phase 5 |
| Q7 | Structured issue body sections | §2.2 |
| Q8 | Threaded parallel questions, auto-accept on Status drag | §3.5 (clarify skill) |
| Q9 | Phase A parallel + Phase B clean-slate critique | §3.2-3.4, §3.7-3.8 |
| Q10 | Topological scheduler, concurrency=1 default | Phase 6 workflow chain |
| Q11 | Container w/ host unreachable + ephemeral GH App tokens | Phase 5 |
| Q11b | Per-teammate runners, swappable executor | Phase 5 (deferred to v0.5) |
| Q12 | `.claude/`, `.codex/`, root `ARTIFACTS.md` | §1.2 layout |
| Q13 | 4 MD files + index.json + frontmatter discipline | §2.4-2.7, §6.2 (reindex workflow) |
| Q14 | Two-tier verify + bounded auto-fix + compressed log | §3.9-3.13 (v0.2 split into acceptance + quality + fixer) |
| Q15 | Quick + deep lessons; per-proposal 👍 | §3.14 |
| Q16 | Standalone repo + curl-piped bootstrap + 3-way upgrade | Phase 7 |
| Q17 | Wide-net research, narrative output, synthesis reframes | §3.2-3.4 |
| Q18 | Layer-1 + Layer-2 skills (13 + 4 in v0.2) | Phases 3, 4 |
| Q19 | GitHub-native + JSONL + status issue | Phase 6 + cross-cutting §4.2 |
| Q20 | Status-as-state, labels-as-attributes, two-drag UX | §6.1, §6.2, §6.3 (v0.2 adds Final Validation, Integrating, Verifying-Acceptance, Verifying-Quality) |

**v0.2 doctrine implementations:**
- Doctrine #9 (provider diversity): deferred to v0.5; design pre-allocates the
  verifier slot.
- Doctrine #10 (acceptance vs quality verification): §3.9-3.12 split; §2.9
  config; §6.2 workflow split.
- Doctrine #11 (conflict resolution stays with implementer): §3.9 dual-mode
  implementer skill; §6.2 `on-integrating.yml`.

---

*End of build plan v0.2. Total length: roughly 36-56 hours of focused
implementer work plus your interaction time. Hand to AI; expect questions
back; those questions are good.*
