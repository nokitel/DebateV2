#!/usr/bin/env bash
set -euo pipefail
issue=${1:-}
[[ -n "$issue" ]] || { echo "Usage: down.sh <issue-id>" >&2; exit 1; }
root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root"
compose=.harness/stacks/docker-compose.issue-${issue}.yml
if [[ -f "$compose" ]] && command -v docker >/dev/null 2>&1; then
  docker compose -f "$compose" down --remove-orphans
fi
printf '{"ts":"%s","workflow":"stack-down","issue":"%s","outcome":"success"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$issue" >> .harness/metrics/stack.jsonl
