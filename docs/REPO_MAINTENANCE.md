# Repository maintenance

Use `scripts/repo_hygiene.py` for direct maintenance checks.
`scripts/repo_maintenance.py` is a compatibility wrapper for older invocations.

## Common commands

```bash
# first-party scan
python3 scripts/repo_hygiene.py scan --repo-root .

# first-party cleanup
python3 scripts/repo_hygiene.py clean --repo-root .

# first-party JSON scan
python3 scripts/repo_hygiene.py scan --repo-root . --json

# include third-party dependency tree
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# write a baseline from current findings
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

## Makefile shortcuts

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Notes

- `clean` removes untracked clutter only; it does not edit source markers.
- Marker findings can be suppressed via `.repo-hygiene-baseline.json`.
- For baseline details, see `docs/REPO-HYGIENE.md`.
