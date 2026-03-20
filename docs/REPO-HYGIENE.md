# Repo hygiene

`scripts/repo_hygiene.py` is the primary maintenance scanner/cleaner used by
scheduled automation and local maintenance runs.

## What it checks

- Unfinished markers in tracked source files:
  - `TODO`
  - `FIXME`
  - `STUB`
  - `TBD`
  - `XXX`
  - `WIP`
  - `UNFINISHED`
- Untracked stray paths:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`, `*.old`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts:
  - `egressd-starter.tar.gz` (tracked or untracked)
- Embedded git repositories outside allowed paths (for example accidental nested repos)

By default scans are **first-party only** and skip `third_party/FunkyDNS`.
Use `--include-third-party` when you explicitly want to scan dependency internals.

## Usage

From repo root:

```bash
# First-party text report
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party

# First-party JSON report (automation friendly)
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party --json

# Clean removable clutter (stray + stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root . --no-include-third-party

# Full scan including third_party/FunkyDNS
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Make targets:

```bash
make maintenance          # first-party scan
make maintenance-fix      # first-party clean
make maintenance-json     # first-party JSON scan
make maintenance-all      # full scan including third_party
make maintenance-all-json # full JSON scan including third_party
```

## Baseline file

By default, marker suppressions are loaded from:

- `.repo-hygiene-baseline.json`

Override with:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . --baseline-file custom-baseline.json
```

Write/update a baseline:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

## Exit codes

- `0`: no issues remain after command completion
- `1`: issues remain (unfinished markers, stale tracked artifacts, stray/stale untracked paths, or embedded git repos)
- `2`: invalid invocation (for example non-git repo root)

## Compatibility wrapper

`scripts/repo_maintenance.py` is retained for backward compatibility and
delegates directly to `repo_hygiene.py`.
