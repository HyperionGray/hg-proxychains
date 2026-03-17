# Repository maintenance workflow

This repository includes `scripts/repo_maintenance.py` to support recurring automation checks and cleanup.

## What it checks

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Unexpected embedded repositories (nested `.git` roots outside approved locations)

By default, marker scanning also includes tracked files in `third_party/FunkyDNS` when that repository is present.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_maintenance.py

# JSON output for automation
python3 scripts/repo_maintenance.py --json

# Exclude third_party marker scan
python3 scripts/repo_maintenance.py --no-include-third-party

# Allow additional embedded repos for local workflows
python3 scripts/repo_maintenance.py --allow-embedded-repo sandbox/my-local-repo

# Remove backup files + stale artifacts while scanning
python3 scripts/repo_maintenance.py --fix
```

Makefile wrappers:

```bash
# Default scheduled scan (excludes third_party marker checks)
make maintenance
make maintenance-fix
```

To include marker scanning in `third_party/FunkyDNS`, run the script directly:

```bash
python3 scripts/repo_maintenance.py --root . --include-third-party
```

## Notes

- `--fix` only removes backup files and known stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Embedded repository findings are reported only; they are never auto-removed.
- Exit code is `1` when any issues are found, making this suitable for scheduled jobs and CI gates.
