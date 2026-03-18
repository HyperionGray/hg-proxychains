# Repo hygiene (legacy helper)

This repository includes a small maintenance utility at
`scripts/repo_hygiene.py` for scheduled cleanups and local checks.

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

The scanner intentionally skips `third_party/FunkyDNS/` when checking
unfinished markers by default, because that path is managed as an external
dependency.

When you do want full-repo scanning (including nested third-party git state),
use `--include-third-party`.

Known upstream unfinished markers can be recorded in a baseline file so
scheduled jobs can fail only on new findings.

## Usage

From repo root:

```bash
python3 scripts/repo_hygiene.py scan --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py scan --repo-root . --json
```

Or through Make targets:

```bash
make repo-scan
make repo-clean
make repo-scan-json
```

## Exit codes

- `0`: no unfinished markers found (`clean` may still remove stray files)
- `1`: unfinished markers found and/or stray files found during `scan`
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

By default, `scan`/`clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

The baseline currently suppresses marker findings only (not stray files).

## Legacy script

`scripts/repo_maintenance.py` remains as a compatibility wrapper and delegates
to `repo_hygiene.py`.
