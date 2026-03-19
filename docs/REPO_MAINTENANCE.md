# Repository maintenance workflow

`scripts/repo_maintenance.py` is a compatibility wrapper around `scripts/repo_hygiene.py`.
Use `repo_hygiene.py` directly for new automation.

## Recommended commands

```bash
# First-party scan
python3 scripts/repo_hygiene.py scan --repo-root .

# First-party scan + cleanup
python3 scripts/repo_hygiene.py clean --repo-root .

# Machine-readable output
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Deep scan including third-party internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Compatibility wrapper equivalents:

```bash
python3 scripts/repo_maintenance.py
python3 scripts/repo_maintenance.py --fix
python3 scripts/repo_maintenance.py --json
python3 scripts/repo_maintenance.py --include-third-party
```

## Notes

- `clean` removes removable clutter only (stray/untracked/stale removable paths).
- Unfinished markers and embedded git repositories are reported but never auto-edited.
- Marker baseline support is available via `--baseline-file` and `baseline` command in `repo_hygiene.py`.
