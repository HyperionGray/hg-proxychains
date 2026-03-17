# Repo hygiene (legacy helper)

`scripts/repo_hygiene.py` remains available as a compatibility helper, but
the canonical maintenance workflow is documented in
[`docs/REPO_MAINTENANCE.md`](./REPO_MAINTENANCE.md) and exposed via:

```bash
make maintenance
make maintenance-fix
```

Prefer the maintenance workflow for scheduled automation and cleanup.
