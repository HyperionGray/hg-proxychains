# Repository maintenance workflow (compatibility note)

Primary maintenance documentation now lives in `docs/REPO-HYGIENE.md`.

Use `scripts/repo_hygiene.py` directly for current behavior and automation.
`scripts/repo_maintenance.py` is retained as a compatibility wrapper for older
entry points.

## Current command mapping

```bash
# Preferred direct usage
python3 scripts/repo_hygiene.py scan --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Legacy compatibility wrapper
python3 scripts/repo_maintenance.py
python3 scripts/repo_maintenance.py --fix
python3 scripts/repo_maintenance.py --include-third-party
```

## Behavior summary

- Default scope is first-party paths (third-party scanning is opt-in via
  `--include-third-party`).
- `scan` reports unfinished markers, stray untracked clutter, stale artifacts,
  and unexpected embedded git repositories.
- `clean` removes removable untracked clutter and stale untracked artifacts,
  then exits non-zero if blocking issues remain.
- Embedded git repositories and tracked stale artifacts are reported, never
  auto-removed.

## Automation next task

- clean up this directory
- Keep stale artifact rules in `scripts/repo_hygiene.py` synchronized with new
  generated bundle names as they are introduced.
