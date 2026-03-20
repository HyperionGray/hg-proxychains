# Repo hygiene

`scripts/repo_hygiene.py` is the canonical maintenance scanner/cleaner.
`scripts/repo_maintenance.py` is a thin compatibility wrapper that forwards to
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
- Known stale generated artifacts:
  - `egressd-starter.tar.gz`

By default, scanning skips `third_party/FunkyDNS/` marker and stray checks.
Use `--include-third-party` when you explicitly want full-tree coverage.

## Baseline-aware marker reporting

Marker findings are filtered through `.repo-hygiene-baseline.json` by default.
The scan summary reports how many markers were suppressed by the baseline so
automation can track delta behavior cleanly.

Use a custom baseline path with:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . --baseline-file path/to/baseline.json
```

Regenerate a baseline with:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

## Usage

From repo root:

```bash
# Text report (first-party defaults)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report (includes stale artifact buckets + suppression counts)
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter, then report post-clean state
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json
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
  - `scan`: unfinished markers, stray untracked files, or stale artifacts
  - `clean`: unresolved unfinished markers or tracked stale artifacts after cleanup
- `2`: invalid invocation (for example, non-git directory)
