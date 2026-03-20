# Repo hygiene

`scripts/repo_hygiene.py` is the primary repository hygiene tool for this repo.
It supports marker scanning, stale artifact detection, cleanup, baseline
management, and JSON output for automation.

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
- Known stale artifacts if they are tracked (currently `egressd-starter.tar.gz`)

By default, scans focus on first-party code and skip the `third_party/FunkyDNS`
dependency internals. Use `--include-third-party` for a full-repo scan.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# Text report including third-party dependency internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json
python3 scripts/repo_hygiene.py clean --repo-root . --json

# Remove removable untracked clutter
python3 scripts/repo_hygiene.py clean --repo-root .

# Write/update marker baseline
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

The baseline file defaults to `.repo-hygiene-baseline.json` and can be
overridden with `--baseline-file <path>`. Baseline entries suppress known marker
findings only.

## Make targets

```bash
make repo-scan
make repo-clean
make repo-scan-json

make maintenance
make maintenance-fix
make maintenance-json

make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Exit codes

- `0`: no issues remain after command completion
- `1`: blocking issues remain
  - `scan`: unfinished markers, stray untracked paths, or stale artifacts
  - `clean`: unfinished markers, tracked stale artifacts, or failed cleanup
- `2`: invalid invocation (for example, non-git directory)

## Compatibility wrapper

`scripts/repo_maintenance.py` remains available for legacy entrypoints and
delegates to `scripts/repo_hygiene.py`.
