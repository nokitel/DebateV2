#!/usr/bin/env bash
set -euo pipefail
issue=${1:-}
worktree=${2:-$(pwd)}
[[ -n "$issue" ]] || { echo "Usage: up.sh <issue-id> [worktree-path]" >&2; exit 1; }
root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root"
mkdir -p .harness/stacks
compose=.harness/stacks/docker-compose.issue-${issue}.yml
sed -e "s/{{ISSUE_ID}}/$issue/g" -e "s#{{WORKTREE_PATH}}#$worktree#g" docker/docker-compose.harness.yml.tpl > "$compose"
if command -v docker >/dev/null 2>&1; then
  docker compose -f "$compose" up -d --build
else
  echo "docker not installed; rendered $compose only" >&2
fi
printf '{"ts":"%s","workflow":"stack-up","issue":"%s","outcome":"success"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$issue" >> .harness/metrics/stack.jsonl
