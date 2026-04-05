# Repository maintenance workflow (compatibility note)

`scripts/repo_maintenance.py` remains available as a legacy-compatible wrapper
for existing automation, but it delegates directly to `scripts/repo_hygiene.py`.

Primary maintenance documentation lives in:

- `docs/REPO-HYGIENE.md`

## Preferred commands

```bash
# First-party scan
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party

# First-party cleanup
python3 scripts/repo_hygiene.py clean --repo-root . --no-include-third-party

# Optional full scan including third_party/FunkyDNS internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Makefile wrappers:

```bash
make maintenance        # first-party only
make maintenance-fix    # first-party only + cleanup
make maintenance-json   # first-party only + JSON
make maintenance-all    # include third_party
```

## Wrapper behavior

- `scripts/repo_maintenance.py --fix` maps to `repo_hygiene.py clean`.
- `scripts/repo_maintenance.py` without `--fix` maps to `repo_hygiene.py scan`.
- Third-party scanning is controlled with `--include-third-party` or
  `--no-include-third-party`.
