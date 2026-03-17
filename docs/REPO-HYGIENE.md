# Repo hygiene

`scripts/repo_hygiene.py` is retained as a legacy scanner. For scheduled automation and current maintenance policy, prefer `scripts/repo_maintenance.py` (`make maintenance` / `make maintenance-fix`).

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

The scanner intentionally skips `third_party/FunkyDNS/` when checking
unfinished markers, because that path is managed as an external dependency.

## Usage

From repo root:

```bash
python3 scripts/repo_hygiene.py scan --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root .
```

Or through Make targets:

```bash
make repo-scan
make repo-clean
```

## Exit codes

- `0`: no unfinished markers found (`clean` may still remove stray files)
- `1`: unfinished markers found and/or stray files found during `scan`
- `2`: invalid invocation (for example, non-git directory)
