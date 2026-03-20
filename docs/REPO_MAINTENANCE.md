# Repository maintenance workflow (legacy wrapper note)

`scripts/repo_maintenance.py` remains as a compatibility wrapper around
`scripts/repo_hygiene.py`.

Primary command reference lives in `docs/REPO-HYGIENE.md`.

## Common commands

```bash
# First-party scan (default recommendation)
python3 scripts/repo_maintenance.py --no-include-third-party

# First-party scan + cleanup
python3 scripts/repo_maintenance.py --no-include-third-party --fix

# Full scan including third_party/FunkyDNS internals
python3 scripts/repo_maintenance.py --include-third-party

# JSON output
python3 scripts/repo_maintenance.py --no-include-third-party --json
```

Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```
