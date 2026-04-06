# Repo hygiene

This repository includes a maintenance utility at
`scripts/repo_hygiene.py` for scheduled cleanups and local checks.
`scripts/repo_maintenance.py` remains a compatibility wrapper.

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
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove untracked stray files/directories and stale untracked artifacts
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Add extra stale artifact paths for this run (repeatable flag)
python3 scripts/repo_hygiene.py scan --repo-root . \
  --stale-artifact-path dist/output.bin \
  --stale-artifact-path build/cache.tar
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

`scripts/repo_maintenance.py` is retained as a compatibility wrapper and now
delegates to `scripts/repo_hygiene.py`.

## Exit codes

- `0`: no issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers, stray untracked files, stale artifacts, or embedded git repos
  - `clean`: unfinished markers, tracked stale artifacts, embedded git repos, or partial cleanup failure
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

By default, `scan`/`clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

The baseline currently suppresses marker findings only (not stray files).

## Runtime stale-artifact overrides

If a branch temporarily introduces generated outputs that should be treated as
stale cleanup targets, pass one or more `--stale-artifact-path` flags. The
paths are interpreted relative to `--repo-root`.

This extends (does not replace) the built-in stale artifact list.
