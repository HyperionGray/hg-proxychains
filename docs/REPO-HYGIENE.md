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

By default, the scanner skips `third_party/FunkyDNS/` for unfinished markers
and stray-file cleanup, because that path is managed as an external dependency.

## Usage

From repo root:

```bash
python3 scripts/repo_hygiene.py scan --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root .

# include third-party paths explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# machine-readable output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json
```

Or through Make targets:

```bash
make repo-scan
make repo-clean
make maintenance
make maintenance-fix
```

`scripts/repo_maintenance.py` is retained as a compatibility wrapper and now
delegates to `scripts/repo_hygiene.py`.

## Exit codes

- `0`: no unfinished markers found (`clean` may still remove stray files)
- `1`: unfinished markers found and/or stray files found during `scan`
- `2`: invalid invocation (for example, non-git directory)
