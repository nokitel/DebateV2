#!/usr/bin/env bash
set -euo pipefail
root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$root"
mkdir -p memory
out=memory/index.json
tmp=$(mktemp)
printf '[\n' > "$tmp"
first=1
while IFS= read -r -d '' f; do
  rel=${f#./}
  id=$(awk '/^id:/{print $2; exit}' "$f" 2>/dev/null || true)
  tags=$(awk '/^tags:/{sub(/^tags:[[:space:]]*/,""); print; exit}' "$f" 2>/dev/null || true)
  status=$(awk '/^status:/{print $2; exit}' "$f" 2>/dev/null || true)
  title=$(grep -m1 '^# ' "$f" | sed 's/^# //')
  [[ -n "$id$title$tags$status" ]] || continue
  [[ $first -eq 1 ]] || printf ',\n' >> "$tmp"
  first=0
  jq -n --arg file "$rel" --arg id "$id" --arg title "$title" --arg tags "$tags" --arg status "$status" \
    '{file:$file,id:$id,title:$title,tags:$tags,status:$status}' >> "$tmp"
done < <(find ./memory -type f \( -name '*.md' ! -name README.md ! -name tags.md \) -print0 2>/dev/null)
printf '\n]\n' >> "$tmp"
mv "$tmp" "$out"
echo "Indexed memory into $out"
