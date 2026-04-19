# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is now a compatibility wrapper.

Use `scripts/repo_hygiene.py` directly for all maintenance checks and cleanup.
Primary documentation has moved to `docs/REPO-HYGIENE.md`.

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Unexpected embedded repositories (nested `.git` roots outside approved locations)

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

# Allow additional embedded repos for local workflows
python3 scripts/repo_maintenance.py --allow-embedded-repo sandbox/my-local-repo

# Remove backup files + stale artifacts while scanning
python3 scripts/repo_maintenance.py --fix
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

To include marker scanning in `third_party/FunkyDNS`, run the script directly:

```bash
python3 scripts/repo_maintenance.py --root . --include-third-party
```

## Notes

- Use `clean` (not `scan`) to remove backup files, stray `__pycache__/`
  directories, and known stale artifacts.
- `--stale-artifact <path>` can be supplied repeatedly on `scan` or `clean`
  to track extra generated files for a run.
- Unfinished markers are reported but not modified automatically.
- Embedded repository findings are reported only; they are never auto-removed.
- Exit code is `1` when any issues are found, making this suitable for scheduled jobs and CI gates.
