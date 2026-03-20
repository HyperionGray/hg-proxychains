# Repository maintenance wrapper

`scripts/repo_maintenance.py` is a compatibility CLI that forwards to
`scripts/repo_hygiene.py`.

Use `repo_hygiene.py` directly for current behavior and options; see
`docs/REPO-HYGIENE.md`.

## Legacy-compatible examples

```bash
# Scan (legacy default includes third_party)
python3 scripts/repo_maintenance.py --root .

# Scan including third_party
python3 scripts/repo_maintenance.py --root . --include-third-party

# Scan first-party only
python3 scripts/repo_maintenance.py --root . --no-include-third-party

# Clean removable clutter
python3 scripts/repo_maintenance.py --root . --fix
```

`--json` is accepted for compatibility and emits a deprecation warning.
