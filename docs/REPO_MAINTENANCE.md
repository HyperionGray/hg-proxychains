# Repository maintenance workflow

`scripts/repo_hygiene.py` is the authoritative maintenance scanner/cleaner.
`scripts/repo_maintenance.py` is a compatibility wrapper that forwards options to
`repo_hygiene.py`.

## What is checked

- unfinished markers in tracked source/config files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`)
- untracked stray files and cache output (`*~`, `*.bak`, `*.tmp`, `*.orig`, `*.rej`, `.DS_Store`, `Thumbs.db`, `*.pyc`, `*.pyo`, `__pycache__/`, etc.)
- known stale artifacts (`egressd-starter.tar.gz`)
- unexpected embedded git repositories (excluding the allowed `third_party/FunkyDNS` submodule root)

Default mode is first-party focused and excludes third-party internals.

## Commands

```bash
# first-party scan (human readable)
python3 scripts/repo_hygiene.py scan --repo-root .

# first-party scan (JSON)
python3 scripts/repo_hygiene.py scan --repo-root . --json

# include third_party/FunkyDNS internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# remove removable clutter (stray files + stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .

# refresh baseline markers file
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Compatibility wrapper examples:

```bash
python3 scripts/repo_maintenance.py --no-include-third-party
python3 scripts/repo_maintenance.py --no-include-third-party --fix
python3 scripts/repo_maintenance.py --include-third-party --json
```

## Makefile targets

```bash
make maintenance          # first-party scan
make maintenance-fix      # first-party clean
make maintenance-json     # first-party scan in JSON
make maintenance-all      # include third_party
make maintenance-all-fix  # include third_party + clean
make maintenance-all-json # include third_party + JSON
make maintenance-baseline # write baseline file (include third_party)
```

## Baseline notes

- baseline file default: `.repo-hygiene-baseline.json`
- baseline suppresses matching marker findings only
- use `--baseline-file <path>` to override location

## Exit codes

- `0`: no issues remain
- `1`: issues found (or cleanup could not remove all removable clutter)
- `2`: invalid invocation (for example, non-git directory)
