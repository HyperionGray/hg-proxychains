# Repo hygiene

`scripts/repo_hygiene.py` is the canonical repository hygiene tool used by
`make maintenance*` targets and scheduled automation.

## What it checks

- Unfinished markers in tracked files:
  - `TODO`
  - `FIXME`
  - `STUB`
  - `TBD`
  - `XXX`
  - `WIP`
  - `UNFINISHED`
- Untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts (`egressd-starter.tar.gz`) in tracked and untracked sets.
- Embedded git repositories (`.git`) outside the repository root
  (submodule gitlink files are ignored).

By default, first-party scans skip paths under `third_party/`. Use
`--include-third-party` when you explicitly want full-tree scanning.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove removable clutter (stray files + untracked stale artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json
```

Or via Make:

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

- `0`: no blocking issues remain after command completion
- `1`: blocking issues found
  - `scan`: unfinished markers, stray files, stale artifacts, or embedded git repos
  - `clean`: unfinished markers, tracked stale artifacts, or embedded git repos
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

`scan` and `clean` load unfinished-marker suppressions from
`.repo-hygiene-baseline.json` by default. Override with:

```bash
python3 scripts/repo_hygiene.py scan --baseline-file <path>
```

Generate or refresh a baseline with:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

The baseline suppresses unfinished-marker findings only.

## Compatibility wrapper

`scripts/repo_maintenance.py` is retained for legacy invocations and delegates
to `repo_hygiene.py`.
