# Repo hygiene

`scripts/repo_hygiene.py` is the low-level scanner/cleaner used by maintenance
automation. `scripts/repo_maintenance.py` is a compatibility wrapper that
delegates to it.

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
- Known stale artifacts:
  - `egressd-starter.tar.gz` (tracked or untracked)

By default, scanning skips `third_party/FunkyDNS`. Include it explicitly with
`--include-third-party`.

## Baseline behavior

`scan` and `clean` load marker suppressions from:

- `.repo-hygiene-baseline.json` (default)

Override with:

```bash
--baseline-file <path>
```

Baseline suppression only applies to unfinished-marker findings. Reports include
both active findings and the count of suppressed marker matches.

## Commands

```bash
# Human-readable scan (first-party by default)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON scan output
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Clean removable clutter (stray paths + stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .

# Regenerate baseline
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Makefile wrappers:

```bash
make maintenance          # first-party scan (wrapper)
make maintenance-fix      # first-party cleanup (wrapper)
make maintenance-json     # first-party scan JSON
make maintenance-all      # include third_party/FunkyDNS
make maintenance-all-json # include third_party/FunkyDNS JSON
make maintenance-baseline # regenerate baseline
```

## Exit codes

- `0`: no blocking issues remain
- `1`: blocking issues found
  - `scan`: unfinished markers, stray paths, or stale artifacts
  - `clean`: unfinished markers, tracked stale artifacts, or deletion failures
- `2`: invalid invocation (for example, non-git directory)
