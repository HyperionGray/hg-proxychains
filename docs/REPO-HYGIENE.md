# Repo hygiene

Use `scripts/repo_hygiene.py` as the primary scanner/cleaner.
`scripts/repo_maintenance.py` remains a compatibility wrapper that delegates to
the same implementation.

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
- Known stale artifact paths:
  - default: `egressd-starter.tar.gz`
  - optional extras via repeated `--stale-artifact PATH`

By default, first-party scanning skips `third_party/FunkyDNS/` marker/stray
noise. Use `--include-third-party` for full-repo scanning.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove untracked stray files/directories and untracked stale artifacts
python3 scripts/repo_hygiene.py clean --repo-root .

# Add extra stale artifact paths without changing code
python3 scripts/repo_hygiene.py clean --repo-root . \
  --stale-artifact dist/output.tar.gz \
  --stale-artifact logs/runtime.dump
```

Or through Make targets:

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

- `0`: no issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers, stray untracked files, stale artifacts, or embedded git repos
  - `clean`: unfinished markers, tracked stale artifacts, embedded git repos, or failed deletions
- `2`: invalid invocation (for example, non-git directory or `baseline --json`)

## Baseline file

By default, `scan`/`clean` load marker suppressions from
`.repo-hygiene-baseline.json`.

Override with `--baseline-file <path>`.
The baseline suppresses unfinished marker findings only.
