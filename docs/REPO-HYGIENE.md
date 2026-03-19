# Repo hygiene

`scripts/repo_hygiene.py` is the primary maintenance scanner/cleaner used by
scheduled automation and local checks.

## What it checks

- Unfinished markers in tracked files:
  - `TODO`
  - `FIXME`
  - `STUB`
  - `TBD`
  - `XXX`
  - `WIP`
  - `UNFINISHED`
- Common untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts:
  - `egressd-starter.tar.gz`
- Embedded git repositories:
  - any nested `.git` path outside explicitly allowed locations

By default, scanning is first-party only. `third_party/FunkyDNS` is excluded
unless `--include-third-party` is set.

## Usage

From repo root:

```bash
# text scan
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON scan (for automation)
python3 scripts/repo_hygiene.py scan --repo-root . --json

# include third-party dependency tree
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# remove removable clutter and rescan
python3 scripts/repo_hygiene.py clean --repo-root .

# regenerate marker baseline (optional, typically for known upstream markers)
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Make target wrappers:

```bash
make maintenance           # first-party scan
make maintenance-fix       # first-party clean
make maintenance-json      # first-party scan JSON
make maintenance-all       # include third_party/FunkyDNS
make maintenance-all-json  # include third_party/FunkyDNS + JSON
make maintenance-baseline  # write baseline including third_party/FunkyDNS
```

## Baseline file

`scan` and `clean` suppress known unfinished marker findings from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

## Exit codes

- `0`: no issues remain after command completion
- `1`: blocking issues remain
  - `scan`: unfinished markers, stray untracked paths, stale artifacts, or embedded git repos
  - `clean`: issues remain after removable clutter is deleted
- `2`: invalid invocation (for example, non-git directory)

## Compatibility wrapper

`scripts/repo_maintenance.py` remains for legacy callers and delegates directly
to `scripts/repo_hygiene.py`.
