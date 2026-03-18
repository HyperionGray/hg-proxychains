# Repo hygiene

This repository includes a small maintenance utility at
`scripts/repo_hygiene.py` for scheduled cleanups and local checks.

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
- Tracked stray artifacts (reported, not auto-deleted) that match the same
  backup/cache patterns.

By default, the scanner skips `third_party/FunkyDNS/` because that path is
managed as an external dependency.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove untracked stray files/directories
python3 scripts/repo_hygiene.py clean --repo-root .
```

Or through Make targets:

```bash
make maintenance
make maintenance-fix
make repo-scan
make repo-clean
```

## Exit codes

- `0`: no unfinished markers or stray files found
- `1`: unfinished markers and/or stray files found
- `2`: invalid invocation (for example, non-git directory)

## Compatibility

`scripts/repo_maintenance.py` is still available as a compatibility wrapper and
delegates to `scripts/repo_hygiene.py`.
