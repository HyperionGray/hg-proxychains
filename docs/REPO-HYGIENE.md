# Repo hygiene

`scripts/repo_hygiene.py` provides repository scan/cleanup checks used by local
development and automation. For the broader maintenance workflow and Make
targets, see `docs/REPO_MAINTENANCE.md`.

## Checks

- unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`)
- untracked stray artifacts (`*~`, `*.bak`, `*.tmp`, `*.orig`, `*.rej`, `.DS_Store`, `Thumbs.db`, `*.pyc`, `*.pyo`, `__pycache__/`)
- known stale artifacts (`egressd-starter.tar.gz`)
- unexpected embedded git repositories (outside allowed submodule locations)

By default, scanning is first-party only. Use `--include-third-party` to include
`third_party/FunkyDNS`.

## Usage

```bash
# scan (text)
python3 scripts/repo_hygiene.py scan --repo-root .

# scan (json)
python3 scripts/repo_hygiene.py scan --repo-root . --json

# full scan including third_party/FunkyDNS
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# clean removable clutter
python3 scripts/repo_hygiene.py clean --repo-root .

# write/update marker baseline
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

## Baseline

- default file: `.repo-hygiene-baseline.json`
- override with `--baseline-file <path>`
- only suppresses marker findings, not file/directory clutter

## Exit codes

- `0`: no issues remain
- `1`: issues found or cleanup could not remove all removable clutter
- `2`: invalid invocation (for example, non-git directory)
