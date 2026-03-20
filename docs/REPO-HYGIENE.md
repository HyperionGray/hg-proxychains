# Repo hygiene

`scripts/repo_hygiene.py` is the primary repository hygiene tool for local and automation checks.

## What it checks

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`)
- Untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts (`egressd-starter.tar.gz`) as tracked and untracked findings
- Unexpected embedded git repositories (outside the allowed `third_party/FunkyDNS` submodule path)

By default, scans are first-party focused and skip `third_party/` internals. Use
`--include-third-party` when you want full dependency-tree visibility.

## Commands

From the repo root:

```bash
# text scan (first-party default)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON scan for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# clean removable clutter (stray + stale untracked)
python3 scripts/repo_hygiene.py clean --repo-root .

# include third-party internals explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Make targets:

```bash
make maintenance          # first-party scan
make maintenance-fix      # first-party clean
make maintenance-json     # first-party scan in JSON
make maintenance-all      # include third_party
make maintenance-all-json # include third_party + JSON
make maintenance-baseline # refresh baseline file
```

## Baseline support

`scan` and `clean` load marker suppressions from `.repo-hygiene-baseline.json` by default.
Override with `--baseline-file <path>`.

Write or refresh baseline entries:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Baseline suppression applies only to unfinished-marker findings.

## Exit codes

- `0`: no issues remain after command completion
- `1`: one or more issues remain
- `2`: invalid invocation (for example, non-git directory)

## Compatibility wrapper

`scripts/repo_maintenance.py` remains for legacy entry points and forwards to
`repo_hygiene.py`.
