# Repository maintenance workflow

Use `scripts/repo_hygiene.py` directly for current maintenance checks and cleanup.
`scripts/repo_maintenance.py` is a compatibility wrapper for older automation.

## Recommended commands

```bash
# First-party hygiene scan
python3 scripts/repo_hygiene.py scan --repo-root .

# First-party scan with cleanup
python3 scripts/repo_hygiene.py clean --repo-root .

# First-party JSON output
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Full scan including third_party/FunkyDNS internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Compatibility wrapper equivalents:

```bash
python3 scripts/repo_maintenance.py --no-include-third-party
python3 scripts/repo_maintenance.py --no-include-third-party --fix
python3 scripts/repo_maintenance.py --include-third-party --json
```

## Makefile integration

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Behavior notes

- `clean` removes only removable clutter (stray files and stale untracked artifacts).
- Unfinished marker findings are reported, never auto-edited.
- Baseline suppressions are loaded from `.repo-hygiene-baseline.json` by default.
- Use `make maintenance-baseline` to refresh baseline entries when needed.

