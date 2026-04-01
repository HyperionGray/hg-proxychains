# Repository maintenance workflow

Use `scripts/repo_hygiene.py` for all current maintenance checks and cleanup.
`scripts/repo_maintenance.py` remains a compatibility wrapper for older
invocations.

This workflow checks and reports:

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (`egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, scans are first-party focused and skip `third_party/` internals.
Use `--include-third-party` only when explicitly auditing dependency trees.

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

- `clean` removes backup files, stray cache artifacts, and known untracked stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `--fix`.
- Tracked stale artifacts are reported and require manual cleanup.
- `scan` exits `1` when any issues are found.
- `clean` exits `1` when non-removable issues remain after cleanup.
