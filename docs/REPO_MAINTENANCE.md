# Repository maintenance workflow

`scripts/repo_maintenance.py` is the stable automation entrypoint. It is a thin
compatibility wrapper around `scripts/repo_hygiene.py`.

## Recommended usage

```bash
# First-party scan (default automation mode)
python3 scripts/repo_maintenance.py --no-include-third-party

# First-party cleanup (removes removable clutter)
python3 scripts/repo_maintenance.py --no-include-third-party --fix

# Full scan including third_party/FunkyDNS
python3 scripts/repo_maintenance.py --include-third-party
```

You can set a non-default baseline file:

```bash
python3 scripts/repo_maintenance.py --baseline-file custom-baseline.json
```

## Make targets

```bash
make maintenance          # first-party scan
make maintenance-fix      # first-party cleanup
make maintenance-json     # first-party JSON scan
make maintenance-all      # include third_party/FunkyDNS
make maintenance-all-json # include third_party/FunkyDNS JSON scan
make maintenance-baseline # regenerate baseline
```

## Behavior notes

- `--fix` removes untracked stray paths and stale untracked artifacts.
- Unfinished markers are reported only; they are not auto-edited.
- Baseline suppression affects unfinished markers only.
- Use `docs/REPO-HYGIENE.md` for full scanner details and JSON schema.
