#!/usr/bin/env bash
set -euo pipefail
root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root"
[[ -f memory/tags.md ]] || { echo "memory/tags.md missing" >&2; exit 1; }
allowed=$(awk '/^[[:space:]]*- /{print $2}' memory/tags.md | sort -u)
fail=0
while IFS= read -r -d '' f; do
  line=$(awk '/^tags:/{sub(/^tags:[[:space:]]*/,""); print; exit}' "$f" || true)
  [[ -n "$line" ]] || continue
  while read -r tag; do
    if ! grep -qx "$tag" <<<"$allowed"; then
      echo "Unknown memory tag '$tag' in $f" >&2
      fail=1
    fi
  done < <(echo "$line" | tr -d '[],' | tr ' ' '\n' | sed '/^$/d')
done < <(find memory -type f -name '*.md' ! -name tags.md -print0 2>/dev/null)
exit $fail
