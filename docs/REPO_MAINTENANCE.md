# Repository maintenance workflow

This repository includes `scripts/repo_maintenance.py` as a compatibility
entry point for recurring automation checks and cleanup.

The implementation now lives in `scripts/repo_hygiene.py`; maintenance calls
are delegated there so only one scanner/cleaner logic path must be maintained.

## What it checks

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`)
- Stray backup/cache artifacts in tracked and untracked paths (`*~`, `*.bak`, `*.orig`, `*.rej`, `*.tmp`, `__pycache__`, `*.pyc`, `*.pyo`)

By default, this compatibility command includes `third_party/FunkyDNS`
(`--include-third-party`) to preserve previous behavior.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_maintenance.py

# JSON output for automation
python3 scripts/repo_maintenance.py --json

# Exclude third_party marker and stray scan
python3 scripts/repo_maintenance.py --no-include-third-party

# Remove untracked stray artifacts while scanning
python3 scripts/repo_maintenance.py --fix
```

Makefile wrappers:

```bash
make maintenance
make maintenance-fix
```

## Notes

- `--fix` only removes untracked stray artifacts.
- Unfinished markers and tracked stray files are reported but not modified automatically.
- Exit code is `1` when any issues are found, making this suitable for scheduled jobs and CI gates.
