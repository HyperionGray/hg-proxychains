# Repository maintenance workflow

The canonical maintenance implementation is `scripts/repo_hygiene.py`.
`scripts/repo_maintenance.py` is a compatibility wrapper that forwards the same
behavior and flags.

## Recommended commands

```bash
# First-party scan
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party

# First-party clean
python3 scripts/repo_hygiene.py clean --repo-root . --no-include-third-party

# Full scan (including third_party/FunkyDNS)
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

If you need compatibility entry points:

```bash
python3 scripts/repo_maintenance.py --root . --no-include-third-party
python3 scripts/repo_maintenance.py --root . --fix --no-include-third-party
```

## Make targets

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```

## Behavior

- `clean` removes removable clutter:
  - untracked stray paths
  - stale untracked artifacts
- `clean` does **not** remove:
  - unfinished markers
  - stale tracked artifacts
  - embedded git repos
- marker suppressions are loaded from `.repo-hygiene-baseline.json` by default
  and can be changed with `--baseline-file`.
