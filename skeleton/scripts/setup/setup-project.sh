#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in --help|-h) echo "Usage: setup-project.sh [--dry-run]"; exit 0;; esac
mode=${1:-}
statuses=(Draft Researching Clarifying Critiquing "Plan Ready" "Ready for Work" "In Progress" "In Review" "Final Validation" Done "Verification Failed" Rejected Blocked)
substatuses=(Queued Implementing "Self-Verified" "Verifying-Acceptance" "Verifying-Quality" Verified Integrating "In Review" Merged Fixing "Verification Failed" Rejected Blocked)
if [[ "$mode" == "--dry-run" ]]; then
  printf 'Parent statuses:\n'; printf -- '- %s\n' "${statuses[@]}"
  printf 'Sub-issue statuses:\n'; printf -- '- %s\n' "${substatuses[@]}"
  exit 0
fi
mkdir -p .harness
if [[ ! -f .harness/config.yml ]]; then
  cp .harness/config.yml.tpl .harness/config.yml 2>/dev/null || true
fi
cat <<EOF
Project setup helper is ready, but GitHub Project v2 mutation is intentionally explicit.
Use --dry-run to inspect statuses. Then wire field IDs into .harness/config.yml.
EOF
