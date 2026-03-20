# Repo hygiene

Use `scripts/repo_hygiene.py` as the canonical maintenance tool for this repo.
It scans for unfinished markers and removable clutter, and can optionally clean
the removable items.

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
  - common metadata noise (`.DS_Store`, `Thumbs.db`)
  - known generated bundles (`egressd-starter.tar.gz`)

By default, scans are first-party only. `third_party/FunkyDNS` is excluded
unless you pass `--include-third-party`.

## Commands

From repo root:

```bash
# first-party scan (text)
python3 scripts/repo_hygiene.py scan --repo-root .

# first-party scan (JSON)
python3 scripts/repo_hygiene.py scan --repo-root . --json

# remove first-party removable clutter
python3 scripts/repo_hygiene.py clean --repo-root .

# full scan, including third_party/FunkyDNS
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# generate/update baseline entries for current unfinished markers
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

## Baseline behavior

`scan` and `clean` load marker suppressions from `.repo-hygiene-baseline.json`
by default.

- Override with `--baseline-file <path>`.
- Baseline suppressions apply to unfinished-marker findings only.
- Stray file findings are never baseline-suppressed.

## Makefile targets

```bash
make maintenance          # first-party scan
make maintenance-fix      # first-party cleanup
make maintenance-json     # first-party scan (JSON)
make maintenance-all      # include third_party/FunkyDNS
make maintenance-all-json # include third_party/FunkyDNS (JSON)
make maintenance-baseline # write baseline (include third_party/FunkyDNS)
```

## Legacy wrapper

`scripts/repo_maintenance.py` remains for compatibility and delegates to
`repo_hygiene.py`.
