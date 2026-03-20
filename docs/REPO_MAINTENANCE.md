# Repository maintenance workflow

Primary maintenance tooling is `scripts/repo_hygiene.py`. The
`scripts/repo_maintenance.py` entry point is a compatibility wrapper that
forwards to it.

## Default scope

For day-to-day scheduled automation, prefer first-party-only scans:

- `--no-include-third-party` (default behavior in Make targets)

Use full-repo scans only when intentionally reviewing dependency internals:

- `--include-third-party`

## Commands

```bash
# first-party text scan
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party

# first-party JSON scan
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party --json

# first-party cleanup
python3 scripts/repo_hygiene.py clean --repo-root . --no-include-third-party

# optional full scan including third_party/FunkyDNS internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Compatibility wrapper examples:

```bash
python3 scripts/repo_maintenance.py --no-include-third-party
python3 scripts/repo_maintenance.py --no-include-third-party --fix
python3 scripts/repo_maintenance.py --include-third-party --json
```

## Makefile wrappers

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```

## Notes

- `clean`/`--fix` removes only removable clutter (stray files/dirs, stale untracked artifacts).
- Unfinished markers are reported but not auto-modified.
- Embedded git repositories are reported but never auto-removed.
- Exit code is non-zero while unresolved issues remain.
