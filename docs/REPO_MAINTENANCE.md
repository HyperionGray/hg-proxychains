# Repository maintenance workflow (legacy note)

Use `scripts/repo_hygiene.py` directly for current maintenance automation.
This file exists only to preserve historical references.

Current primary documentation:

- `docs/REPO-HYGIENE.md`

Compatibility wrapper:

- `scripts/repo_maintenance.py` (delegates to `repo_hygiene.py`)

Canonical targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```
