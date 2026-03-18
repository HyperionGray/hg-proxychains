# Repository maintenance workflow

`scripts/repo_hygiene.py` is the canonical maintenance utility.

- Primary documentation: `docs/REPO-HYGIENE.md`
- Preferred automation entrypoints:
  - `make maintenance`
  - `make maintenance-fix`

`scripts/repo_maintenance.py` remains as a compatibility wrapper that forwards to
`scripts/repo_hygiene.py` so existing automation jobs do not break.
