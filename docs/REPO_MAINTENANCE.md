# Repository maintenance workflow

For the full scanner behavior, see `docs/REPO-HYGIENE.md`.

`scripts/repo_maintenance.py` remains as a compatibility wrapper for legacy
automation invocations. It delegates to `scripts/repo_hygiene.py`.

## Recommended commands

```bash
# First-party scan (default maintenance mode)
make maintenance

# First-party scan + cleanup of removable clutter
make maintenance-fix

# Machine-readable first-party report
make maintenance-json

# Full scan including third_party/FunkyDNS internals
make maintenance-all
make maintenance-all-json

# Refresh baseline from current marker findings
make maintenance-baseline
```

Direct wrapper usage:

```bash
python3 scripts/repo_maintenance.py --no-include-third-party
python3 scripts/repo_maintenance.py --no-include-third-party --fix
python3 scripts/repo_maintenance.py --include-third-party
```

## Notes

- Cleanup removes removable clutter only (stray artifacts + stale untracked files).
- Marker findings and tracked stale artifacts are reported but never auto-edited.
- Embedded git repositories outside allowed paths are reported, not removed.
