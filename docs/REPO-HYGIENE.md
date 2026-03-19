# Repo hygiene

`scripts/repo_hygiene.py` is the canonical maintenance tool for this repository.
`scripts/repo_maintenance.py` is retained as a compatibility wrapper.

## What it checks

- Unfinished markers in tracked source files:
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
- Known stale artifacts (`egressd-starter.tar.gz`)

By default, scanning is first-party only and skips `third_party/FunkyDNS`.
Use `--include-third-party` when you want a full scan.

## Usage

From repo root:

```bash
# Text report (non-zero exit when issues are present)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove untracked stray files/directories and stale untracked artifacts
python3 scripts/repo_hygiene.py clean --repo-root .
```

Generate/update baseline entries:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

## Baseline file

By default, `scan` and `clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

The baseline suppresses marker findings only (not stray files/artifacts).

## Make targets

```bash
make repo-scan
make repo-clean
make repo-scan-json

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
  - `scan`: unfinished markers, stray untracked files, or stale artifacts
  - `clean`: unfinished markers, tracked stale artifacts, or undeleted removable clutter
- `2`: invalid invocation (for example, non-git directory)

