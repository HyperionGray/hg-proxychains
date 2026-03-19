# Repository maintenance workflow

Primary maintenance tooling is `scripts/repo_hygiene.py`. The older
`scripts/repo_maintenance.py` wrapper remains for compatibility and delegates
directly to the hygiene script.

For full details, see `docs/REPO-HYGIENE.md`.

## Common commands

```bash
# first-party scan
python3 scripts/repo_hygiene.py scan --repo-root .

# first-party clean
python3 scripts/repo_hygiene.py clean --repo-root .

# full scan including third_party/FunkyDNS
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# automation-friendly JSON report
python3 scripts/repo_hygiene.py scan --repo-root . --json
```

## Make wrappers

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```
