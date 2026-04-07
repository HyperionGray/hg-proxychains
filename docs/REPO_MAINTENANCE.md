# Repository maintenance workflow

Use `scripts/repo_hygiene.py` directly for maintenance checks and cleanup.
The legacy `scripts/repo_maintenance.py` interface remains available as a
compatibility wrapper for older automation.

Primary maintenance reference:

- `docs/REPO-HYGIENE.md`

## Quick commands

```bash
# Human-readable summary + findings (non-zero when issues exist)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Remove removable clutter and re-evaluate hygiene status
python3 scripts/repo_hygiene.py clean --repo-root .

# Optional path exclusions for focused scans (repeatable)
python3 scripts/repo_hygiene.py scan --repo-root . \
  --exclude-path docs \
  --exclude-path "*.tmp"
```

Make wrappers:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```
