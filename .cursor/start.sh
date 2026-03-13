#!/usr/bin/env bash
set -euo pipefail

if command -v docker >/dev/null 2>&1 && command -v service >/dev/null 2>&1; then
  sudo service docker start >/dev/null 2>&1 || true
fi
