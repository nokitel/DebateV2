#!/usr/bin/env bash
set -euo pipefail

ROOT=$(pwd)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SKELETON_DIR=$(cd "$SCRIPT_DIR/../skeleton" && pwd)

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required tool: $1" >&2; exit 1; }; }
render_file() {
  local src=$1 dst=$2
  mkdir -p "$(dirname "$dst")"
  sed \
    -e "s/{{PROJECT_NAME}}/${PROJECT_NAME//\//\\/}/g" \
    -e "s/{{CANONICAL_COMMANDS}}/${CANONICAL_COMMANDS//\//\\/}/g" \
    -e "s/{{ARCHITECTURE_BOUNDARIES}}/${ARCHITECTURE_BOUNDARIES//\//\\/}/g" \
    -e "s/{{CODE_QUALITY_MODE}}/${CODE_QUALITY_MODE//\//\\/}/g" \
    -e "s/{{CODE_QUALITY_PRIMARY}}/${CODE_QUALITY_PRIMARY//\//\\/}/g" \
    "$src" > "$dst"
}

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "init.sh must run inside a git repo" >&2
  exit 1
fi
if [[ -n $(git status --porcelain) ]]; then
  echo "Refusing to bootstrap into a dirty worktree" >&2
  exit 1
fi
for t in git jq; do need "$t"; done
for optional in docker gh; do
  if ! command -v "$optional" >/dev/null 2>&1; then
    echo "Warning: $optional not found. Install before running the full harness." >&2
  fi
done

PROJECT_NAME=${PROJECT_NAME:-$(basename "$ROOT")}
CANONICAL_COMMANDS=${CANONICAL_COMMANDS:-"Fill this in: test, typecheck, lint, build commands."}
ARCHITECTURE_BOUNDARIES=${ARCHITECTURE_BOUNDARIES:-"Fill this in: module boundaries and forbidden dependencies."}
CODE_QUALITY_MODE=${CODE_QUALITY_MODE:-single}
CODE_QUALITY_PRIMARY=${CODE_QUALITY_PRIMARY:-codex}

case "$CODE_QUALITY_MODE" in single|dual) ;; *) echo "CODE_QUALITY_MODE must be single or dual" >&2; exit 1;; esac
case "$CODE_QUALITY_PRIMARY" in codex|claude) ;; *) echo "CODE_QUALITY_PRIMARY must be codex or claude" >&2; exit 1;; esac

branch="harness/init"
if ! git rev-parse --verify "$branch" >/dev/null 2>&1; then
  git checkout -b "$branch"
else
  git checkout "$branch"
fi

while IFS= read -r -d '' src; do
  rel=${src#"$SKELETON_DIR/"}
  dst="$ROOT/${rel%.tpl}"
  if [[ -e "$dst" ]]; then
    echo "Refusing to overwrite existing file: $dst" >&2
    exit 1
  fi
  if [[ "$src" == *.tpl ]]; then
    render_file "$src" "$dst"
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
  fi
  if [[ -x "$src" ]]; then chmod +x "$dst"; fi
done < <(find "$SKELETON_DIR" -type f -print0)

sha=$(git -C "$SCRIPT_DIR/.." rev-parse HEAD 2>/dev/null || echo unknown)
cat > "$ROOT/.harness-version" <<EOF
version=0.2.0
skeleton_commit=$sha
rendered_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

git add .
git commit -m "Install AI Harness skeleton v0.2" || true
cat <<EOF

AI Harness installed on branch $branch.
Next:
1. Review the diff.
2. Install the GitHub App: scripts/setup/install-app.md
3. Register a runner: scripts/setup/install-runner.md
4. Run: scripts/setup/setup-project.sh
5. Commit .harness/config.yml after setup.
EOF
