# Repo hygiene

Use `scripts/repo_hygiene.py` as the primary maintenance tool for scheduled checks and local cleanup.

## What it checks

- Unfinished markers in tracked source/config files (`TODO:`, `FIXME:`, `STUB:`, `TBD:`, `XXX:`, `WIP:`, `UNFINISHED:`)
- Untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Stale artifacts (`egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed submodule root (`third_party/FunkyDNS`)

By default, scans focus on first-party code and skip `third_party/FunkyDNS/`.
Pass `--include-third-party` for deep scans.

## Usage

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Remove removable clutter, then re-evaluate remaining issues
python3 scripts/repo_hygiene.py clean --repo-root .

# Deep scan including third-party internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Make target wrappers:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Baseline file

`scan` and `clean` load marker suppressions from `.repo-hygiene-baseline.json` by default.
Override with `--baseline-file <path>`.

Write/update a baseline:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

The baseline suppresses unfinished-marker findings only; it does not suppress stray/stale/artifact findings.

## Exit codes

- `0`: no issues remain after command completion
- `1`: issues remain
- `2`: invalid invocation (for example, non-git directory)

## Compatibility wrapper

`scripts/repo_maintenance.py` is retained for legacy entrypoints and delegates to `repo_hygiene.py`.
