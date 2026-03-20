# Repository maintenance workflow

The maintenance entrypoint for automation is `scripts/repo_maintenance.py`,
which delegates directly to `scripts/repo_hygiene.py`.

For complete behavior details, see `docs/REPO-HYGIENE.md`.

## Common commands

```bash
# First-party scan (default)
python3 scripts/repo_maintenance.py --no-include-third-party

# First-party scan with cleanup
python3 scripts/repo_maintenance.py --no-include-third-party --fix

# First-party machine-readable output
python3 scripts/repo_maintenance.py --no-include-third-party --json

# Full scan including third_party/FunkyDNS
python3 scripts/repo_maintenance.py --include-third-party
```

Make wrappers:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```
