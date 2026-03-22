# Repo hygiene

This repository uses `scripts/repo_hygiene.py` as the primary maintenance
scanner/cleaner for scheduled automation and local checks.

`scripts/repo_maintenance.py` remains a compatibility wrapper that delegates to
`repo_hygiene.py`.

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
- Known stale artifacts (tracked and untracked), currently:
  - `egressd-starter.tar.gz`
- Embedded git repositories outside the root repo and valid gitlinks
  (reported only; never auto-deleted)

By default, scans stay first-party and skip the `third_party/` tree.
Use `--include-third-party` for full-repo scans including nested dependencies.

Known upstream unfinished markers can be recorded in a baseline file so
scheduled jobs fail only on newly introduced markers.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable untracked clutter
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json
```

Or via Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make repo-scan
make repo-clean
make repo-scan-json
```

## Exit codes

- `0`: no blocking issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers, stray files, stale artifacts, or embedded git repos
  - `clean`: unfinished markers, stale tracked artifacts, embedded git repos, or failed deletions
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

By default, `scan`/`clean` load marker suppressions from
`.repo-hygiene-baseline.json`. Override with `--baseline-file <path>`.

The baseline currently suppresses marker findings only (not stale/stray/git
repo findings).
