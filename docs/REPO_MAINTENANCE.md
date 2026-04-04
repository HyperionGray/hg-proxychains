# Repository maintenance workflow

`scripts/repo_maintenance.py` is a compatibility wrapper that delegates to
`scripts/repo_hygiene.py`.

Primary documentation now lives in:

- `docs/REPO-HYGIENE.md`

## Preferred commands

```bash
# first-party scan
python3 scripts/repo_hygiene.py scan --repo-root .

# first-party cleanup
python3 scripts/repo_hygiene.py clean --repo-root .

# include third-party internals when explicitly needed
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

The legacy wrapper remains available for existing automation:

```bash
python3 scripts/repo_maintenance.py --no-include-third-party
python3 scripts/repo_maintenance.py --no-include-third-party --fix
python3 scripts/repo_maintenance.py --include-third-party --json
```
