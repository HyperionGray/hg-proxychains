# Repository maintenance workflow

`scripts/repo_hygiene.py` is the primary maintenance scanner/cleaner.
`scripts/repo_maintenance.py` remains a compatibility wrapper.

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, marker scanning includes tracked files in `third_party/FunkyDNS` when that repository is present.
For day-to-day repo automation, prefer the first-party-only mode (`--no-include-third-party`)
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
- Without `--fix`, exit code is `1` when any issues are found.
- With `clean`, exit code reflects post-clean state (`0` when only removable clutter was found and removed; `1` if issues remain).
