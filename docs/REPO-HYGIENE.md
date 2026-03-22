# Repo hygiene

`scripts/repo_hygiene.py` is the primary repository hygiene scanner/cleaner.
`scripts/repo_maintenance.py` remains as a compatibility wrapper that delegates
to it.

## What it checks

- Unfinished markers in tracked source files:
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
- Known stale artifact paths (tracked and untracked), currently:
  - `egressd-starter.tar.gz`
- Unexpected embedded git repositories (nested `.git` entries), excluding
  legitimate submodule gitlinks.

By default, first-party scanning excludes `third_party/FunkyDNS/`. Use
`--include-third-party` when you explicitly want full-repo scanning.

Known upstream unfinished markers can be recorded in a baseline file so
scheduled jobs fail only on new marker findings.

## Usage

From repo root:

```bash
# Human-readable scan
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON scan for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Remove removable clutter (stray + stale untracked paths)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json

# Optional deep scan including third_party internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Make targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```

## Exit codes

- `0`: no issues remain after the command completes
- `1`: issues found
  - `scan`: unfinished markers, stray paths, stale artifacts, or embedded git repos
  - `clean`: unfinished markers, tracked stale artifacts, or embedded git repos
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

By default, `scan`/`clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

The baseline suppresses unfinished-marker findings only.
