# Repo hygiene

`scripts/repo_hygiene.py` is the canonical maintenance scanner/cleaner used by
automation and local checks.

`scripts/repo_maintenance.py` remains as a compatibility wrapper for older
invocations and delegates to `repo_hygiene.py`.

## What it checks

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`,
  `WIP`, `UNFINISHED`)
- Untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`, `*.old`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Stale artifact paths (`egressd-starter.tar.gz`) in tracked or untracked state
- Embedded git repositories outside the allowed
  `third_party/FunkyDNS/.git` dependency path

By default, scans are first-party focused and skip `third_party/FunkyDNS`.
Use `--include-third-party` when you explicitly want to include that tree.

## Commands

```bash
# text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# remove removable clutter (stray untracked + stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .

# include third-party scan
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Make wrappers:

```bash
make maintenance           # first-party scan
make maintenance-fix       # first-party clean
make maintenance-json      # first-party scan JSON
make maintenance-all       # include third_party/FunkyDNS
make maintenance-all-json  # include third_party/FunkyDNS + JSON
```

## Baseline file

`scan` and `clean` load unfinished-marker suppressions from
`.repo-hygiene-baseline.json` by default.

Override path with:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . --baseline-file path/to/baseline.json
```

Regenerate a baseline:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Baselines suppress marker findings only (not stray/stale/embedded-git findings).

## Exit codes

- `0`: no blocking issues remain
- `1`: blocking issues found
- `2`: invalid invocation (for example, non-git directory)
