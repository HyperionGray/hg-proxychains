# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is now a compatibility wrapper.

Use `scripts/repo_hygiene.py` directly for all maintenance checks and cleanup.
Primary documentation has moved to:

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, scans are first-party-only and skip `third_party/FunkyDNS` internals.
Use `--include-third-party` when you intentionally want to include dependency internals.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party marker scan explicitly
python3 scripts/repo_maintenance.py --include-third-party

# Remove backup files + stray cache dirs + stale artifacts while scanning
python3 scripts/repo_maintenance.py --fix

# Register additional generated artifacts to treat as stale for this run
python3 scripts/repo_maintenance.py --fix --stale-artifact dist/output.tar.gz
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

- `--fix` removes backup files, stray `__pycache__/` directories, and known stale artifacts.
- `--stale-artifact <path>` can be repeated to include additional generated artifacts for one run.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `--fix`.
- Without `--fix`, exit code is `1` when any issues are found.
- With `--fix`, exit code reflects post-fix state (`0` when only removable clutter was found and removed; `1` if issues remain).
