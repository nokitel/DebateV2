#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for candidate in \
  "$ROOT/.venv313/bin/python" \
  "$ROOT/.venv/bin/python" \
  "$ROOT/.venv312/bin/python" \
  python3.13 \
  python3.12 \
  python3
do
  if [ -x "$candidate" ]; then
    exec "$candidate" "$ROOT/scripts/subscription_loop.py" "$@"
  fi
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$(command -v "$candidate")" "$ROOT/scripts/subscription_loop.py" "$@"
  fi
done

echo "No Python 3.12+ interpreter found for subscription loop helper" >&2
exit 127
