#!/usr/bin/env bash
set -euo pipefail
if command -v docker >/dev/null 2>&1; then
  docker ps --filter label=aiharness=true --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
else
  echo "docker not installed"
fi
