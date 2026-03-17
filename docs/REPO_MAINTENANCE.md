# Repository maintenance workflow

This repository's canonical maintenance utility is `scripts/repo_hygiene.py`.
The older `scripts/repo_maintenance.py` entry point remains as a compatibility
wrapper and delegates to `repo_hygiene.py`.

## What it checks

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)

By default, `repo_hygiene.py` excludes `third_party/FunkyDNS` so external
dependency TODOs do not block first-party maintenance checks.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party marker and stray-file scan explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove stray artifacts while scanning
python3 scripts/repo_hygiene.py clean --repo-root .
```

Makefile wrappers:

```bash
make maintenance
make maintenance-fix
```

## Notes

- `clean` removes tracked stray artifacts and prints how many paths were deleted.
- Unfinished markers are reported but not modified automatically.
- Exit code is `1` when unfinished markers exist, and for `scan` also when stray files are found.
