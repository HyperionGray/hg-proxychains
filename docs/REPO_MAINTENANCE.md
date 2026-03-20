# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is now a compatibility wrapper.

Use `scripts/repo_hygiene.py` directly for all maintenance checks and cleanup.
Primary documentation lives in `docs/REPO-HYGIENE.md`.

Default mode is first-party only (it skips `third_party/FunkyDNS` unless
`--include-third-party` is set).

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party/FunkyDNS explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove backup files + stray cache dirs + stale untracked artifacts
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

- `clean` removes backup files, stray `__pycache__/` directories, and stale
  untracked artifacts.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `clean`.
- `scan` exits `1` when any issues are found.
- `clean` exits based on post-clean state (`0` when only removable clutter was
  found and removed; `1` if issues remain).
