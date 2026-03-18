# Repo hygiene

This repository includes `scripts/repo_hygiene.py` for scheduled checks and
local maintenance cleanup.

`scripts/repo_maintenance.py` remains available as a compatibility wrapper
for older invocations.

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
  - additional backup suffixes (`*.old`)
  - known generated bundles (`egressd-starter.tar.gz`)
- Known stale artifacts (`egressd-starter.tar.gz`) in both tracked and
  untracked state
- Unexpected embedded git repositories outside allowed submodule paths

By default, scanning is first-party only and skips `third_party/`.
Pass `--include-third-party` to include dependency paths.

Known upstream unfinished markers can be recorded in a baseline file so
scheduled jobs can fail only on new findings.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly (slowest mode)
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter (stray/untracked stale artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json

# Refresh baseline of known unfinished markers
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Or through Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make repo-scan
make repo-clean
make repo-scan-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

`scripts/repo_maintenance.py` delegates to `repo_hygiene.py` and preserves the
legacy flags (`--fix`, `--include-third-party`, `--json`).

## Exit codes

- `0`: no issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers, stray paths, stale artifacts, or embedded repos
  - `clean`: same, after removable clutter deletion is attempted
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

By default, `scan`/`clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

The baseline currently suppresses marker findings only (not stray files).
