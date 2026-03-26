# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is a compatibility wrapper that delegates to
`scripts/repo_hygiene.py`.

For active maintenance guidance and current behavior, use:

- `docs/REPO-HYGIENE.md`

Quick references:

- `make maintenance` / `python3 scripts/repo_hygiene.py scan --repo-root .`
- `make maintenance-fix` / `python3 scripts/repo_hygiene.py clean --repo-root .`
- `make maintenance-all` / `python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party`
