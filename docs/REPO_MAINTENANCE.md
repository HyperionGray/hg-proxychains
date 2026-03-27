# Repository maintenance workflow

`scripts/repo_maintenance.py` is a compatibility wrapper around
`scripts/repo_hygiene.py`.

Use `scripts/repo_hygiene.py` directly for all maintenance checks and cleanup.
Detailed behavior and examples live in `docs/REPO-HYGIENE.md`.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party marker scan explicitly (compat wrapper)
python3 scripts/repo_maintenance.py --include-third-party

# Remove backup files + stray cache dirs + stale artifacts while scanning
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

## Notes

- `--fix` removes backup files, stray `__pycache__/` directories, and known stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Without `--fix`, exit code is `1` when any issues are found.
- With `--fix`, exit code reflects post-fix state (`0` when only removable clutter was found and removed; `1` if issues remain).
