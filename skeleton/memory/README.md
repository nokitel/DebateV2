# Memory Discipline

## Four-file model

- `decisions/` — one ADR per durable decision.
- `mistakes.md` — append-only earned mistakes.
- `glossary.md` — domain language.
- `guardrails.md` — earned rules that prevent repeated failures.

## Frontmatter

Every entry uses the schema in `ARTIFACTS.md` §8.

## Supersedes, do not overwrite

If a decision changes, create a new entry and set `superseded_by` on the old one.

## Contradictions are first-class

If new work contradicts memory, cite the contradiction and ask before proceeding.

## Retrieval

Use skill scope first, then `index.json` tag resolution, then grep fallback.

## Tags

`tags.md` is canonical. New tags require proposal rationale.

## Pruning

Quarterly, merge synonyms, archive stale entries, and remove duplicate guardrails.

## Not for

Do not store project-map facts that can be deduced from code. Do not store secrets.
