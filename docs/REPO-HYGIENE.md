# Repo hygiene

`scripts/repo_hygiene.py` is the primary scanner/cleaner for scheduled and local
repository maintenance checks.

`scripts/repo_maintenance.py` remains as a compatibility wrapper and delegates to
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
- Known stale artifacts (currently `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed root/third-party locations

By default, scans focus on first-party code and skip
`third_party/FunkyDNS/` internals. Use `--include-third-party` for full-repo
coverage when needed.

Known upstream unfinished markers can be suppressed with a baseline file so
automation only fails on newly introduced markers.

## Usage

From repository root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter (stray untracked paths + stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json

# Write/refresh a marker baseline file
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Equivalent Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
make repo-scan
make repo-clean
make repo-scan-json
```

## Exit codes

- `0`: no issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers, stray untracked paths, stale artifacts, or embedded git repos
  - `clean`: unfinished markers, tracked stale artifacts, embedded git repos, or incomplete cleanup
- `2`: invalid invocation (for example, non-git directory or unsupported flag combinations)

## Baseline file

By default, `scan`/`clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

Baseline entries suppress unfinished marker findings only (not stray files,
stale artifacts, or embedded git repos).
