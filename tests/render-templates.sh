#!/usr/bin/env bash
set -euo pipefail
out=$(mktemp -d)
cp -R skeleton/. "$out/"
find "$out" -type f -name '*.tpl' | while read -r f; do
  sed     -e 's/{{PROJECT_NAME}}/Example Project/g'     -e 's/{{CANONICAL_COMMANDS}}/npm test/g'     -e 's/{{ARCHITECTURE_BOUNDARIES}}/Keep domain logic out of routes./g'     -e 's/{{CODE_QUALITY_MODE}}/single/g'     -e 's/{{CODE_QUALITY_PRIMARY}}/codex/g'     -e 's/{{ISSUE_ID}}/1/g'     -e 's#{{WORKTREE_PATH}}#/tmp/worktree#g'     "$f" > "${f%.tpl}"
  rm "$f"
done
# Ignore intentional runtime templates: Docker's Go-template format and the
# stack renderer's references to the Compose template placeholders.
if grep -R '{{' "$out" \
  | grep -v '{{\.Names}}' \
  | grep -v '{{\.Status}}' \
  | grep -v '{{\.Ports}}' \
  | grep -v 'docker-compose.harness.yml.tpl' >/tmp/aiharness-unrendered.$$; then
  echo "Unrendered placeholders remain" >&2
  cat /tmp/aiharness-unrendered.$$ >&2
  rm -f /tmp/aiharness-unrendered.$$
  exit 1
fi
rm -f /tmp/aiharness-unrendered.$$
echo "Rendered templates into $out"
