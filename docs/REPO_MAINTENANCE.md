# Repository maintenance workflow (legacy note)

`scripts/repo_hygiene.py` is the primary maintenance utility.
`scripts/repo_maintenance.py` remains a compatibility wrapper that delegates to
`repo_hygiene.py`.

Primary documentation lives in `docs/REPO-HYGIENE.md`.

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, marker scanning is first-party only and skips
`third_party/FunkyDNS` internals. Use `--include-third-party` when you
explicitly want full dependency-tree visibility.

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
make maintenance-automation      # excludes known automation plan note
make maintenance-automation-fix  # automation profile + cleanup

# optional full scan including third_party/FunkyDNS internals
make maintenance-all
make maintenance-all-json
```

## Notes

- Use `clean` (not `scan`) to remove backup files, stray `__pycache__/`
  directories, and known stale artifacts.
- `--stale-artifact <path>` can be supplied repeatedly on `scan` or `clean`
  to track extra generated files for a run.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `clean`.
- `scan` exits `1` when issues are found.
- `clean` exits `0` only when removable clutter is deleted and no blocking
  issues remain; otherwise it exits `1`.
