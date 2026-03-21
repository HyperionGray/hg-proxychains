# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is a compatibility wrapper that delegates to
`scripts/repo_hygiene.py`.

Use `scripts/repo_hygiene.py` directly for current maintenance workflows.
Canonical details live in:

- `docs/REPO-HYGIENE.md`

Quick command references:

```bash
python3 scripts/repo_hygiene.py scan --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py scan --repo-root . --json
```

Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```
