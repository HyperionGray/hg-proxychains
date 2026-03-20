# Repo hygiene

`scripts/repo_hygiene.py` is the primary maintenance scanner/cleaner.

`scripts/repo_maintenance.py` remains as a compatibility wrapper for legacy
automation entry points.

## What it checks

- Unfinished markers in tracked source files:
  - `TODO`
  - `FIXME`
  - `STUB`
  - `TBD`
  - `XXX`
  - `WIP`
  - `UNFINISHED`
- Common untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.old`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts:
  - `egressd-starter.tar.gz`

By default, scans are first-party focused and skip marker/stray checks under
`third_party/FunkyDNS/`. Use `--include-third-party` for full scans.

## Commands

From repo root:

```bash
# Human-readable scan
python3 scripts/repo_hygiene.py scan --repo-root .

# Machine-readable scan
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Delete removable clutter (backup files, cache dirs, untracked stale artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .

# Include third-party internals explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Regenerate baseline entries (typically with third-party enabled)
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Make targets:

```bash
make maintenance          # first-party scan
make maintenance-fix      # first-party clean
make maintenance-json     # first-party scan JSON
make maintenance-all      # include third_party/FunkyDNS
make maintenance-all-json # include third_party/FunkyDNS + JSON
make maintenance-baseline # refresh baseline file
make quickstart-check     # maintenance + unit tests
```

## Baseline behavior

`scan` and `clean` load marker suppressions from `.repo-hygiene-baseline.json`
by default. Override with `--baseline-file <path>`.

Baseline suppressions only apply to unfinished-marker findings.

## Exit codes

- `0`: no issues remain after command completion
- `1`: blocking issues found
  - `scan`: unfinished markers, stray artifacts, or stale artifacts present
  - `clean`: unresolved findings remain after cleanup
- `2`: invalid invocation (for example, non-git directory)
