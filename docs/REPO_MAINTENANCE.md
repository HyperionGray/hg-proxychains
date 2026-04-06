# Repository maintenance workflow

Use `scripts/repo_hygiene.py` directly for maintenance checks and cleanup.

Primary checks:

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.rej`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, marker and stray scanning skip `third_party/FunkyDNS` to avoid
external dependency noise. Include it explicitly with `--include-third-party`.

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

- `clean` removes backup files, stray cache directories, and known stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `clean`.
- `scan` exits `1` when any issues are found.
- `clean` exits `0` when only removable clutter was found and deleted, and exits `1` if unfinished markers, tracked stale artifacts, embedded git repos, or cleanup failures remain.
