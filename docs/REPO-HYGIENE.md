# Repo hygiene

`scripts/repo_hygiene.py` is the primary maintenance scanner/cleaner used by
scheduled automation and local checks.

`scripts/repo_maintenance.py` remains as a compatibility wrapper that forwards
to `repo_hygiene.py`.

## What it checks

- Unfinished markers in tracked source files:
  - `TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`
- Untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python caches (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts:
  - `egressd-starter.tar.gz` (tracked or untracked)
- Embedded git repositories:
  - reports nested `.git` paths outside the allowed dependency path
    `third_party/FunkyDNS/.git`

By default, unfinished-marker and stray scans skip
`third_party/FunkyDNS/` to reduce noise from external dependency internals.
Use `--include-third-party` for full-repo scanning.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter (stray artifacts + stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json
```

Useful Make targets:

```bash
make maintenance           # first-party scan
make maintenance-fix       # first-party cleanup
make maintenance-json      # first-party JSON scan
make maintenance-all       # include third_party/FunkyDNS
make maintenance-all-json  # include third_party/FunkyDNS + JSON
make maintenance-baseline  # write/update baseline for known markers
```

## Exit codes

- `0`: no issues remain after command completion
- `1`: issues remain
  - `scan`: any findings
  - `clean`: findings that remain after removable clutter is deleted
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

`scan` and `clean` suppress known marker findings via baseline entries from:

- `.repo-hygiene-baseline.json` (default)

Override with `--baseline-file <path>`.

`baseline` command writes current marker findings in baseline format:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

The baseline suppresses marker findings only; it does not suppress stray files,
stale artifacts, or embedded git path findings.
