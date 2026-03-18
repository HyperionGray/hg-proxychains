# Repo hygiene

`scripts/repo_hygiene.py` is the primary maintenance scanner/cleaner used by
automation and local development.

## What it checks

- Unfinished markers in tracked files:
  - `TODO`
  - `FIXME`
  - `STUB`
  - `TBD`
  - `XXX`
  - `WIP`
  - `UNFINISHED`
- Common untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - common metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts:
  - `egressd-starter.tar.gz`
- Unexpected embedded git repositories (outside allowed paths)

By default, marker/stray scanning skips `third_party/FunkyDNS/` to avoid noise
from vendored dependency internals. Use `--include-third-party` for full scan
mode.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter (stray files + stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json
```

Or through Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```

## Baseline file

`scan`/`clean` can suppress known marker findings from a baseline file:

- default: `.repo-hygiene-baseline.json`
- override: `--baseline-file <path>`

Generate/update a baseline:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
make maintenance-baseline
```

Baseline suppression applies to unfinished markers only.

## Exit codes

- `0`: no blocking issues remain after command completion
- `1`: blocking issues found
  - `scan`: unfinished markers, stray files, stale artifacts, or embedded git repos
  - `clean`: unfinished markers, tracked stale artifacts, embedded git repos, or undeleted clutter
- `2`: invalid invocation (for example, non-git directory)
