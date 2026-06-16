#!/usr/bin/env bash
set -euo pipefail
[[ ${1:-} == --dry-run ]] && { echo "dry-run: would refresh sanitized fixtures"; exit 0; }
echo "TODO: refresh fixtures"
