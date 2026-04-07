# Repository maintenance workflow

`scripts/repo_hygiene.py` is the primary scanner/cleaner.
`scripts/repo_maintenance.py` remains a compatibility wrapper for legacy entry points.

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, marker and stray scanning exclude `third_party/FunkyDNS` internals.
Use `--include-third-party` when you explicitly want full dependency scanning.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Remove backup files + stray cache dirs + stale artifacts
python3 scripts/repo_hygiene.py clean --repo-root .

# Alias for clean (same behavior)
python3 scripts/repo_hygiene.py fix --repo-root .

# Include third_party marker/stray scan explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Legacy wrapper commands still supported
python3 scripts/repo_maintenance.py --no-include-third-party
python3 scripts/repo_maintenance.py --no-include-third-party --fix
```

Makefile wrappers:

```bash
make maintenance        # first-party only
make maintenance-fix    # first-party only + cleanup
make maintenance-json   # first-party only + JSON
make repo-fix           # first-party only + cleanup (native hygiene CLI alias)

# optional full scan including third_party/FunkyDNS internals
make maintenance-all
make maintenance-all-json
```

## Notes

- `clean`/`fix` remove backup files, stray cache directories, and known stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed.
- `scan` exits `1` when any issues are found.
- `clean`/`fix` exit `0` when only removable clutter was found and removed, and `1` if non-removable issues remain.
