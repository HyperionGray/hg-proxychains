# Repository maintenance workflow (legacy note)

This file is a compatibility pointer.

Primary maintenance documentation now lives in:

- `docs/REPO-HYGIENE.md`

Current policy:

- `scripts/repo_hygiene.py` is the primary scanner/cleaner
- `scripts/repo_maintenance.py` is a compatibility wrapper that delegates to
  `repo_hygiene.py`

For day-to-day usage:

```bash
make maintenance
make maintenance-fix
make maintenance-json
```
