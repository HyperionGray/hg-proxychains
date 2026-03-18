# Repository maintenance workflow

`scripts/repo_maintenance.py` is a compatibility wrapper that delegates to
`scripts/repo_hygiene.py`.

Use the wrapper when you want stable high-level flags (`--fix`, `--json`,
`--include-third-party`) while preserving the same hygiene engine.

## Wrapper behavior

- default mode: first-party scan (`--no-include-third-party`)
- `--include-third-party`: include nested `third_party/FunkyDNS` internals
- `--fix`: run cleanup mode (`clean`)
- `--json`: emit JSON report from the delegated hygiene command
- `--baseline-file`: pass a custom marker-baseline path

## Commands

```bash
# First-party scan
python3 scripts/repo_maintenance.py --no-include-third-party

# First-party scan + cleanup
python3 scripts/repo_maintenance.py --no-include-third-party --fix

# First-party scan JSON
python3 scripts/repo_maintenance.py --no-include-third-party --json

# Full repo scan including third_party/FunkyDNS internals
python3 scripts/repo_maintenance.py --include-third-party
python3 scripts/repo_maintenance.py --include-third-party --json
```

Make wrappers:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

For scanner details and exit-code behavior, see `docs/REPO-HYGIENE.md`.
