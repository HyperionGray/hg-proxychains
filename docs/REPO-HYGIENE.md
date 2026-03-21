# Repo hygiene

Use `scripts/repo_hygiene.py` for scheduled maintenance checks and cleanup.
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
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts by exact path:
  - `egressd-starter.tar.gz`
- Embedded git repositories (nested `.git` directories/files that are not valid
  gitlinks).

By default, first-party scanning skips `third_party/FunkyDNS/`. Use
`--include-third-party` for full-tree scanning.

Known upstream unfinished markers can be recorded in a baseline file so
scheduled jobs fail only on newly introduced markers.

## Usage

```bash
# Human-readable scan
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON scan output
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party/FunkyDNS in scans
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter (stray + stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json
```

Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Exit codes

- `0`: no issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers, stray untracked paths, stale artifacts, or embedded git repos
  - `clean`: unfinished markers, stale tracked artifacts, embedded git repos, or failed cleanup operations
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

By default, `scan`/`clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

The baseline currently suppresses unfinished-marker findings only.
