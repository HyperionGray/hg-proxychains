# Repo hygiene

`scripts/repo_hygiene.py` is the primary scanner/cleaner used by scheduled
automation and local maintenance (`make maintenance` / `make maintenance-fix`).
`scripts/repo_maintenance.py` is retained as a compatibility wrapper that
delegates to `repo_hygiene.py`.

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
- Stray cache directories discovered from the filesystem (for example,
  nested `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`)
- Known stale artifacts (currently `egressd-starter.tar.gz`) reported as:
  - `stale_tracked_artifacts`
  - `stale_untracked_artifacts`
- Embedded git repositories (`.git`) outside expected locations

The scanner intentionally skips `third_party/FunkyDNS/` unfinished-marker
checks by default, because that path is managed as an external dependency.
Filesystem scanning also skips tool/environment roots such as `.venv/`, `venv/`
and `node_modules/` to avoid noise from local development environments.

When you do want full-repo scanning (including nested third-party git state),
use `--include-third-party`.

Known upstream unfinished markers can be recorded in a baseline file so
scheduled jobs can fail only on new findings.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter (stray files/dirs and stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py scan --repo-root . --json
```

JSON output for automation:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . --json
python3 scripts/repo_hygiene.py clean --repo-root . --json
```

Optional deep scan including `third_party/FunkyDNS` unfinished markers:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Or through Make targets:

```bash
make maintenance
make maintenance-fix
make repo-scan
make repo-clean
make repo-scan-json
```

## Exit codes

- `0`: no issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers, stray untracked files, stray directories,
    stale artifacts, or embedded git repositories
  - `clean`: unfinished markers, tracked stale artifacts, embedded git repos,
    or failed removals (removable clutter is deleted)
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

By default, `scan`/`clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

The baseline currently suppresses marker findings only (not stray files).

## Legacy script

`scripts/repo_maintenance.py` remains as a compatibility wrapper and delegates
to `repo_hygiene.py`.
