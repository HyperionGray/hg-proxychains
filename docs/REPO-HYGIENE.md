# Repo hygiene

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
- Known stale bundle artifacts:
  - `egressd-starter.tar.gz` (tracked and untracked are both reported)

The scanner intentionally skips `third_party/FunkyDNS/` when checking
unfinished markers, because that path is managed as an external dependency.
Use `--include-third-party` when you explicitly want to scan it.

## Usage

From repo root:

```bash
python3 scripts/repo_hygiene.py scan --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root .
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
make repo-scan
make repo-clean
make maintenance
make maintenance-fix
```

## Exit codes

- `0`: no issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers, stray untracked files, or stale artifacts
  - `clean`: unfinished markers or tracked stale artifacts (removable clutter is deleted)
- `2`: invalid invocation (for example, non-git directory)
