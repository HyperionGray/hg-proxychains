# Repository maintenance workflow

`scripts/repo_maintenance.py` remains a compatibility wrapper around
`scripts/repo_hygiene.py`.

Use `scripts/repo_hygiene.py` directly for new automation and local maintenance
flows.

Primary reference:

- `docs/REPO-HYGIENE.md`

## Quick commands

```bash
# Human-readable first-party scan
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Cleanup removable clutter and re-evaluate
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

- Default scope is first-party only (third-party paths are skipped unless
  `--include-third-party` is set).
- `clean` removes removable clutter only (stray files/dirs, stale untracked
  artifacts); unfinished markers and embedded git repos are reported, not
  modified.
