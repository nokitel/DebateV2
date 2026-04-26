#!/usr/bin/env bash
set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "init.sh must run inside a git repo" >&2
  exit 1
fi
if [[ -n $(git status --porcelain) ]]; then
  echo "Refusing to bootstrap into a dirty worktree" >&2
  exit 1
fi

echo "TODO: render skeleton templates and create harness/init branch"
