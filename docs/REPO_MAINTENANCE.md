# Repository maintenance workflow (legacy wrapper)

`scripts/repo_maintenance.py` is a compatibility shim that forwards to
`scripts/repo_hygiene.py`.

Use `repo_hygiene.py` directly for all maintenance checks and cleanup. For full
behavior, options, and exit-code semantics, see `docs/REPO-HYGIENE.md`.

## Common commands

```bash
# First-party scan (default)
python3 scripts/repo_hygiene.py scan --repo-root .

# Cleanup removable first-party clutter
python3 scripts/repo_hygiene.py clean --repo-root .

# Include third_party scans explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Makefile wrappers:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```
