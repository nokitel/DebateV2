#!/usr/bin/env bash
set -euo pipefail
STATUSES=(Draft Researching Clarifying Critiquing "Plan Ready" "Ready for Work" "In Progress" "In Review" "Final Validation" Done "Verification Failed" Rejected Blocked Queued Implementing "Self-Verified" "Verifying-Acceptance" "Verifying-Quality" Verified Integrating Merged Fixing)
case "${1:-}" in
  options) printf '%s
' "${STATUSES[@]}" ;;
  get) echo "TODO get status for issue ${2:-}" ;;
  set) echo "TODO set issue ${2:-} to ${3:-}" ;;
  --help|-h|*) echo "Usage: gh-status.sh options|get <issue>|set <issue> <status>" ;;
esac
