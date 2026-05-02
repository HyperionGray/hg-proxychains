#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
submodule_path="third_party/FunkyDNS"
submodule_name="FunkyDNS"

cd "$repo_root"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required to fetch private dependency P4X-ng/FunkyDNS." >&2
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "bootstrap-third-party.sh must run from inside a git repository." >&2
  exit 1
fi

funkydns_ref="$(git ls-files --stage "$submodule_path" 2>/dev/null | awk '{print $2}')"

if [ -z "$funkydns_ref" ]; then
  echo "No gitlink entry found for $submodule_path; nothing to bootstrap." >&2
  exit 1
fi

gh_token="$(gh auth token)"
auth_url="https://x-access-token:${gh_token}@github.com/P4X-ng/FunkyDNS.git"
public_url="https://github.com/P4X-ng/FunkyDNS.git"

if [ ! -e "$submodule_path/.git" ]; then
  rm -rf "$submodule_path"
  git -c "submodule.${submodule_name}.url=${auth_url}" submodule update --init --recursive "$submodule_path"
else
  git -C "$submodule_path" remote set-url origin "$auth_url"
fi

if ! git -C "$submodule_path" cat-file -e "${funkydns_ref}^{commit}" 2>/dev/null; then
  git -C "$submodule_path" fetch origin "$funkydns_ref"
fi
git -C "$submodule_path" checkout "$funkydns_ref"
git -C "$submodule_path" remote set-url origin "$public_url"

echo "third_party/FunkyDNS checked out at $funkydns_ref"
