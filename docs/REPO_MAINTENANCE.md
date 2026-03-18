# Repository maintenance workflow

Primary maintenance tooling is `scripts/repo_hygiene.py`.
`scripts/repo_maintenance.py` remains a compatibility wrapper.

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, scans are first-party only (`--no-include-third-party` behavior).
Use `--include-third-party` when you need full dependency coverage.

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

# Generate/refresh unfinished-marker baseline
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Makefile wrappers:

```bash
make maintenance        # first-party only
make maintenance-fix    # first-party only + cleanup
make maintenance-json   # first-party only + JSON

# optional full scan including third_party/FunkyDNS internals
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Notes

- `clean` removes backup files, stray `__pycache__/` directories, and known stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `clean`.
- `scan` exits `1` when issues are found.
- `clean` exits based on post-clean state (`0` when only removable clutter was found and removed; `1` if issues remain).
