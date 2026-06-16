#!/usr/bin/env bash
set -euo pipefail
exec "$(dirname "$0")/up.sh" final-validation "${1:-$(pwd)}"
