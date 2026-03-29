# Repository maintenance workflow

`scripts/repo_maintenance.py` is a compatibility wrapper.

Use `scripts/repo_hygiene.py` directly for all checks and cleanup.

## What the current scanner enforces

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`)
- Untracked stray files and cache outputs (`*~`, `*.bak`, `*.orig`, `*.rej`, `*.tmp`, `__pycache__/`, `.DS_Store`, `Thumbs.db`, `*.pyc`, `*.pyo`)
- Known stale artifacts (currently `egressd-starter.tar.gz`) in both tracked and untracked sets
- Embedded git repositories (nested `.git` directories/files), excluding valid gitdir submodule pointers

By default, scans are first-party focused and skip `third_party/FunkyDNS` internals.
Use `--include-third-party` when you explicitly want full dependency-tree scanning.

## Commands

```bash
# Human-readable summary + findings
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party/FunkyDNS internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter and then report remaining blockers
python3 scripts/repo_hygiene.py clean --repo-root .
```

Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```

## Notes

- `clean` removes only removable clutter (stray artifacts and untracked stale artifacts).
- Unfinished markers, tracked stale artifacts, and embedded git repositories are reported but not auto-removed.
- Exit code is `1` when blockers remain.
