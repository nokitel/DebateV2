#!/usr/bin/env bash
set -euo pipefail
fail=0
while IFS= read -r -d '' f; do
  # simple guard: no accidental placeholder style mixing
  if grep -q '{{[^}]*$' "$f"; then
    echo "Unclosed placeholder in $f" >&2
    fail=1
  fi
done < <(find skeleton -type f -name '*.tpl' -print0)
while IFS= read -r -d '' f; do
  for section in "Trigger description" "When to use" "Workflow" "Output format" "Examples"; do
    if ! grep -q "$section" "$f"; then
      echo "Missing section '$section' in $f" >&2
      fail=1
    fi
  done
done < <(find skeleton/.claude/skills skeleton/.codex/skills -name 'SKILL.md' -print0 2>/dev/null || true)
exit $fail
