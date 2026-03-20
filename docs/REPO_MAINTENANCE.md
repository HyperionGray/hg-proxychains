# Repository maintenance workflow

Primary tooling is `scripts/repo_hygiene.py`.

For detailed behavior and all options, see `docs/REPO-HYGIENE.md`.

## Common commands

```bash
# first-party scan
python3 scripts/repo_hygiene.py scan --repo-root .

# first-party cleanup
python3 scripts/repo_hygiene.py clean --repo-root .

# machine-readable report
python3 scripts/repo_hygiene.py scan --repo-root . --json

# include third_party/FunkyDNS internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# refresh baseline from current marker set
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Makefile shortcuts:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Legacy wrapper

`scripts/repo_maintenance.py` is a compatibility wrapper that forwards old
flags to `repo_hygiene.py`.
