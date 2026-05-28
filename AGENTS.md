# AGENTS.md (skeleton repo)

You are working on the AI Harness skeleton itself, not on a target project.
The skeleton is the source of truth that gets copied into target projects via
`bootstrap/init.sh`. Your changes here propagate to all future bootstrapped
projects, and via `bootstrap/upgrade.sh` to existing ones.

Exception: `apps/dialectical-engine/` is an imported application, not part of
the AI Harness skeleton. When working under that path, follow its app-level
documentation and `apps/dialectical-engine/AGENTS.md`.

## Invariants

- Never edit anything inside `skeleton/` without considering downstream impact
  on existing bootstrapped projects.
- Templates with `.tpl` extension contain `{{handlebars}}` placeholders. They
  must remain renderable by `bootstrap/init.sh` after edits.
- Every change to `skeleton/` must bump `VERSION` and add a `CHANGELOG.md`
  entry.
- Tests in `tests/` must pass before commit.

## Workflow

- Filing a feature issue on this repo follows the same structured issue body
  schema as bootstrapped projects.
- Skill changes go through research, clarification, critique, approval, and
  slice fanout. The skeleton should dogfood its own discipline.

## Definition of done

- Files changed are summarized.
- Tests pass: `bash tests/render-templates.sh` and `bash tests/lint-templates.sh`.
- `VERSION` bumped when target-project behavior changes.
- `CHANGELOG.md` entry written.
- If the change affects target projects, `docs/upgrade-guide.md` updated.
