# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is now a compatibility wrapper.

Use `scripts/repo_hygiene.py` directly for all maintenance checks and cleanup.
Primary documentation has moved to:

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)

By default, marker scanning includes tracked files in `third_party/FunkyDNS` when that repository is present.
For day-to-day repo automation, prefer the first-party-only mode (`--no-include-third-party`)
to avoid noise from external dependency internals.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_maintenance.py

# JSON output for automation
python3 scripts/repo_maintenance.py --json

# Exclude third_party marker scan
python3 scripts/repo_maintenance.py --no-include-third-party

# Remove backup files + stale artifacts while scanning
python3 scripts/repo_maintenance.py --fix
```

Makefile wrappers:

```bash
make maintenance        # first-party only
make maintenance-fix    # first-party only + cleanup
make maintenance-json   # first-party only + JSON

# optional full scan including third_party/FunkyDNS internals
make maintenance-all
make maintenance-all-json
```

## Notes

- `--fix` only removes backup files and known stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Exit code is `1` when any issues are found, making this suitable for scheduled jobs and CI gates.
