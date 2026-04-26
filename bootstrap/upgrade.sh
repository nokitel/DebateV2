#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .harness-version ]]; then
  echo "No .harness-version found; run bootstrap/init.sh first." >&2
  exit 1
fi
if [[ -n $(git status --porcelain) ]]; then
  echo "Refusing to upgrade a dirty worktree" >&2
  exit 1
fi

branch="harness/upgrade-$(date +%Y%m%d-%H%M%S)"
git checkout -b "$branch"

# Local skeleton upgrade path: copy current skeleton files into the project,
# preserving existing files by writing .new candidates for manual 3-way review.
SKELETON_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../skeleton" && pwd)
while IFS= read -r -d '' src; do
  rel=${src#"$SKELETON_DIR/"}
  dst="${rel%.tpl}"
  if [[ -e "$dst" ]]; then
    cp "$src" "$dst.new"
    echo "Wrote candidate update: $dst.new"
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "Added new skeleton file: $dst"
  fi
done < <(find "$SKELETON_DIR" -type f -print0)

echo "Review *.new files, merge manually, update .harness-version, then commit. Branch: $branch"
