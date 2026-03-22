# Repository maintenance workflow

`scripts/repo_maintenance.py` is a compatibility wrapper that maps legacy flags
to `scripts/repo_hygiene.py`.

For current behavior and policy, use the primary doc:

- `docs/REPO-HYGIENE.md`

## Legacy wrapper examples

```bash
# Scan (first-party by default)
python3 scripts/repo_maintenance.py

# Scan including third_party internals
python3 scripts/repo_maintenance.py --include-third-party

# Clean removable clutter
python3 scripts/repo_maintenance.py --fix
```

Equivalent Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```
