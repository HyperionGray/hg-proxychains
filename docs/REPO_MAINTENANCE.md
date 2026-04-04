# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is now a compatibility wrapper.

Use `scripts/repo_hygiene.py` directly for all maintenance checks and cleanup.
Primary documentation has moved to:

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, marker scanning is first-party focused and skips
`third_party/FunkyDNS` internals. For full-repo scans, use
`--include-third-party`.

## Commands

```bash
# Human-readable summary + findings (first-party only)
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party --json

# Include third_party marker scan explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove backup files + stray cache dirs + stale artifacts while scanning
python3 scripts/repo_hygiene.py clean --repo-root . --no-include-third-party

# Strict scheduled run: fail if baseline suppressions are present
python3 scripts/repo_hygiene.py scan --repo-root . --fail-on-suppressed-markers
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
- `--fail-on-suppressed-markers` returns non-zero even when all marker findings
  were suppressed by baseline entries.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `--fix`.
- `scan` exits with `1` when any issues are found.
- `clean` exits with post-clean state (`0` when only removable clutter was found and removed; `1` if issues remain).
