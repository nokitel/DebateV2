#!/usr/bin/env bash
set -euo pipefail
out=$(mktemp -d)
cp -R skeleton/. "$out/"
find "$out" -type f -name '*.tpl' | while read -r f; do
  sed     -e 's/{{PROJECT_NAME}}/Example Project/g'     -e 's/{{CANONICAL_COMMANDS}}/npm test/g'     -e 's/{{ARCHITECTURE_BOUNDARIES}}/Keep domain logic out of routes./g'     -e 's/{{CODE_QUALITY_MODE}}/single/g'     -e 's/{{CODE_QUALITY_PRIMARY}}/codex/g'     -e 's/{{ISSUE_ID}}/1/g'     -e 's#{{WORKTREE_PATH}}#/tmp/worktree#g'     "$f" > "${f%.tpl}"
  rm "$f"
done
if grep -R '{{' "$out" >/dev/null; then
  echo "Unrendered placeholders remain" >&2
  grep -R '{{' "$out" >&2
  exit 1
fi
echo "Rendered templates into $out"
