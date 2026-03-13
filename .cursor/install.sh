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

# Match the private dependency checkout to the gitlink pinned in this repo.
funkydns_ref="$(git ls-files --stage third_party/FunkyDNS 2>/dev/null | awk '{print $2}')"

if [ ! -d third_party/FunkyDNS/.git ]; then
  rm -rf third_party/FunkyDNS
  if ! command -v gh >/dev/null 2>&1; then
    echo "GitHub CLI is required to clone private dependency P4X-ng/FunkyDNS." >&2
    exit 1
  fi

  gh_token="$(gh auth token)"
  git clone "https://x-access-token:${gh_token}@github.com/P4X-ng/FunkyDNS.git" third_party/FunkyDNS
  git -C third_party/FunkyDNS remote set-url origin https://github.com/P4X-ng/FunkyDNS.git
fi

if [ -n "${funkydns_ref}" ]; then
  git -C third_party/FunkyDNS fetch origin "${funkydns_ref}" >/dev/null 2>&1 || true
  git -C third_party/FunkyDNS checkout "${funkydns_ref}"
fi
