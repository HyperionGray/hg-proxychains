# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is a compatibility wrapper that delegates to
`scripts/repo_hygiene.py`.

For current behavior, options, and examples, use:

- `docs/REPO-HYGIENE.md`

Recommended entry points:

```bash
make maintenance
make maintenance-fix
make maintenance-json
```

Compatibility wrapper examples:

```bash
python3 scripts/repo_maintenance.py
python3 scripts/repo_maintenance.py --fix
python3 scripts/repo_maintenance.py --include-third-party
```
