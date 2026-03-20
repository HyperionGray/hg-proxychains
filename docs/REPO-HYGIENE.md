# Repo hygiene

`scripts/repo_hygiene.py` is the primary maintenance scanner/cleaner used by
local workflows and scheduled automation.

## What it checks

- Unfinished markers in tracked source files:
  - `TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`
- Common untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
  - known generated bundles (`egressd-starter.tar.gz`)

By default, scans are first-party-only and skip `third_party/FunkyDNS`.
Pass `--include-third-party` for full scans.

## Commands

From repo root:

```bash
# text report
python3 scripts/repo_hygiene.py scan --repo-root .

# machine-readable output
python3 scripts/repo_hygiene.py scan --repo-root . --json

# cleanup removable clutter (without rewriting source files)
python3 scripts/repo_hygiene.py clean --repo-root .

# include third-party code paths
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

### Baseline workflow

Known unfinished markers (for example from external code) can be tracked in a
baseline file so automation only fails on new findings.

```bash
# generate/update baseline
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party

# scan using baseline suppressions (default baseline path shown explicitly)
python3 scripts/repo_hygiene.py scan --repo-root . --baseline-file .repo-hygiene-baseline.json
```

The baseline suppresses marker findings only. Stray files are never suppressed.

## Make targets

```bash
make maintenance         # first-party scan
make maintenance-fix     # first-party scan + cleanup
make maintenance-json    # first-party scan in JSON
make maintenance-all     # include third_party/FunkyDNS
make maintenance-all-json
make maintenance-baseline
```

## Exit codes

- `0`: no issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers or stray untracked files
  - `clean`: unfinished markers remain after cleanup
- `2`: invalid invocation (for example, non-git directory)

`scripts/repo_maintenance.py` remains as a compatibility wrapper that delegates
to `repo_hygiene.py`.
