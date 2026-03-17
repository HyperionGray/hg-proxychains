# Repository maintenance workflow

This repository includes `scripts/repo_maintenance.py` to support recurring automation checks and cleanup.

## What it checks

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray untracked Python cache directories (`__pycache__/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, marker scanning also includes tracked files in `third_party/FunkyDNS` when that repository is present.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_maintenance.py

# JSON output for automation
python3 scripts/repo_maintenance.py --json

# Exclude third_party marker scan
python3 scripts/repo_maintenance.py --no-include-third-party

# Remove backup files + stray cache dirs + stale artifacts while scanning
python3 scripts/repo_maintenance.py --fix
```

Makefile wrappers:

```bash
make maintenance
make maintenance-fix
```

## Notes

- `--fix` removes backup files, stray `__pycache__/` directories, and known stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `--fix`.
- Exit code is `1` when any issues are found, making this suitable for scheduled jobs and CI gates.
