# Repository maintenance workflow

Use `scripts/repo_maintenance.py` for scheduled and operator-facing maintenance checks.
It orchestrates `repo_hygiene.py` and adds embedded git repository detection.

`scripts/repo_hygiene.py` remains the lower-level scanner and baseline writer.

## What is checked

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`)
- Stray untracked artifacts (editor backups, temp files, Python cache outputs)
- Known stale artifacts (`egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed `third_party/FunkyDNS` gitlink

Default mode is first-party only (`--no-include-third-party`).

## Commands

```bash
# First-party maintenance summary
python3 scripts/repo_maintenance.py --no-include-third-party

# First-party maintenance with auto-fix for removable clutter
python3 scripts/repo_maintenance.py --no-include-third-party --fix

# Machine-readable output
python3 scripts/repo_maintenance.py --no-include-third-party --json

# Full scan including third_party/FunkyDNS internals
python3 scripts/repo_maintenance.py --include-third-party
```

Low-level baseline management:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Notes

- `--fix` removes removable artifacts and reports any fix failures.
- Unfinished markers and embedded git repos are reported; they are not auto-fixed.
- Exit code is non-zero when blocking issues remain.
