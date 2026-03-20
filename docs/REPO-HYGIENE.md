# Repo hygiene

`scripts/repo_hygiene.py` is the primary repository hygiene tool.
`scripts/repo_maintenance.py` remains as a compatibility wrapper.

## What it checks

- Unfinished markers in tracked source files:
  - `TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`
- Common untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
  - known stale bundles (`egressd-starter.tar.gz`)

Default scans are first-party only and skip `third_party/FunkyDNS`.
Add `--include-third-party` for full-repo scanning.

## Usage

```bash
# first-party scan
python3 scripts/repo_hygiene.py scan --repo-root .

# first-party scan (JSON output)
python3 scripts/repo_hygiene.py scan --repo-root . --json

# first-party cleanup of removable clutter
python3 scripts/repo_hygiene.py clean --repo-root .

# include third-party dependency tree
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Make targets:

```bash
make maintenance          # first-party scan
make maintenance-fix      # first-party cleanup
make maintenance-all      # include third_party/FunkyDNS
make maintenance-all-json # include third_party/FunkyDNS + JSON
make maintenance-baseline # write baseline from current findings
```

## Baseline file

`scan` and `clean` load marker suppressions from:

- `.repo-hygiene-baseline.json` (default)

Override with `--baseline-file <path>`.

Generate a baseline:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Baseline matching uses `(path, marker, line)` and suppresses only marker
findings (not stray-file findings).

## Exit codes

- `0`: no blocking issues remain
- `1`: blocking issues found (`scan`) or unresolved markers remain (`clean`)
- `2`: invalid invocation (for example, non-git directory)
