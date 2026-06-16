#!/usr/bin/env bash
set -euo pipefail
if command -v docker >/dev/null 2>&1; then
  docker ps -aq --filter label=aiharness=true --filter status=exited | xargs -r docker rm
fi
