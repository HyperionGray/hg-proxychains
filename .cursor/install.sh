#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$repo_root"

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  docker.io \
  docker-compose-v2 \
  python3-venv

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r egressd/requirements.txt

scripts/bootstrap-third-party.sh
