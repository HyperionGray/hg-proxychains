# Repo hygiene

`scripts/repo_hygiene.py` is the low-level hygiene scanner used by
`scripts/repo_maintenance.py`.

For scheduled automation, prefer `scripts/repo_maintenance.py`
(`make maintenance` / `make maintenance-fix`).

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

By default, scans are first-party only and skip `third_party/FunkyDNS/`.
Use `--include-third-party` for full-repo scans.

Known upstream unfinished markers can be recorded in a baseline file so
scheduled jobs can fail only on new findings.

## Usage

From repo root:

```bash
# Text report (first-party only)
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party

# JSON report
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable untracked clutter
python3 scripts/repo_hygiene.py clean --repo-root .
```

Or through Make targets:

```bash
make maintenance
make maintenance-fix
make repo-scan
make repo-clean
make repo-scan-json
```

Write/refresh a marker baseline:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

## Exit codes

- `0`: no issues remain after the command completes
- `1`: blocking issues found
- `scan`: unfinished markers, stray untracked files, or stale artifacts
- `clean`: unfinished markers or tracked stale artifacts (removable clutter is deleted)
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

By default, `scan`/`clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

The baseline currently suppresses marker findings only (not stray files).

## Higher-level maintenance command

`scripts/repo_maintenance.py` composes `repo_hygiene.py` and additionally checks
for unexpected embedded git repositories.
