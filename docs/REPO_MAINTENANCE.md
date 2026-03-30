# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is now a compatibility wrapper.

Use `scripts/repo_hygiene.py` directly for all maintenance checks and cleanup.
Primary documentation has moved to:

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, marker scanning excludes `third_party/FunkyDNS` unless
`--include-third-party` is explicitly set.
For day-to-day repo automation, prefer the default first-party-only mode
to avoid noise from external dependency internals.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party marker scan explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove backup files + stray cache dirs + stale artifacts while scanning
python3 scripts/repo_hygiene.py clean --repo-root .
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

- `clean` removes backup files, stray `__pycache__/` directories, and known stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `clean`.
- `scan` exits with code `1` when issues are found.
- `clean` exits with code `0` only when all remaining issues were removable clutter.
