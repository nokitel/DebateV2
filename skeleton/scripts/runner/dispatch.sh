#!/usr/bin/env bash
set -euo pipefail

workflow=${1:-}
[[ -n "$workflow" ]] || { echo "Usage: dispatch.sh <workflow-name>" >&2; exit 1; }
root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root"
mkdir -p .harness/metrics
started=$(date +%s)
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
issue_number=${ISSUE_NUMBER:-${GITHUB_EVENT_ISSUE_NUMBER:-}}
outcome=success
note="dispatch recorded"

case "$workflow" in
  memory-reindex) scripts/lib/memory-index.sh ;;
  fixtures-refresh) scripts/fixtures/refresh.sh --dry-run ;;
  orphan-cleanup) scripts/stack/orphan-cleanup.sh ;;
  dashboard-tick) scripts/harness status ;;
  on-quality-verifier-config)
    if [[ -f .harness/config.yml ]]; then scripts/harness verify-config; fi ;;
  on-final-validation)
    note="final validation should run cross-slice acceptance against main HEAD" ;;
  on-integrating)
    note="integration should merge origin/main into slice branch and re-run verification" ;;
  *)
    note="runner hook reached; wire model invocation for $workflow" ;;
esac
ended=$(date +%s)
duration=$((ended-started))
jq -n --arg ts "$ts" --arg workflow "$workflow" --arg outcome "$outcome" --arg issue "$issue_number" --arg note "$note" --argjson duration "$duration" \
  '{ts:$ts,workflow:$workflow,issue:$issue,outcome:$outcome,duration_seconds:$duration,note:$note}' \
  >> .harness/metrics/workflows.jsonl

echo "$workflow: $note"
