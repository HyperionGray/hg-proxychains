# Repo hygiene

`scripts/repo_hygiene.py` is the canonical scanner/cleaner used by scheduled
automation and local maintenance checks.

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
- Known stale artifacts:
  - `egressd-starter.tar.gz`
- Embedded git repositories outside the allowed submodule root:
  - `third_party/FunkyDNS` is allowed
  - any other nested `.git` location is reported

By default, unfinished-marker and stray scanning are first-party focused and
skip `third_party/FunkyDNS` internals. Use `--include-third-party` for full
scans.

## Baseline support

Known marker findings can be suppressed with a baseline file:

- default path: `.repo-hygiene-baseline.json`
- override: `--baseline-file <path>`

Baseline suppression applies to unfinished markers only.

## Usage

From repo root:

```bash
# Human-readable report
python3 scripts/repo_hygiene.py scan --repo-root .

# Machine-readable report
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party/FunkyDNS internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter (stray/stale untracked paths)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json

# Refresh marker baseline
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Or through Make targets:

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

- `0`: no blocking issues remain after command completion
- `1`: blocking issues found
  - `scan`: unfinished markers, stray paths, stale artifacts, or embedded git repos
  - `clean`: unfinished markers, stale tracked artifacts, embedded git repos,
    or removable clutter that could not be deleted
- `2`: invalid invocation (for example, non-git directory)
