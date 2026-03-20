# Repo hygiene

`scripts/repo_hygiene.py` is the canonical maintenance scanner/cleaner used by
scheduled automation and local checks.

## What it checks

- Unfinished markers in tracked source files:
  - `TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`
- Untracked stray clutter:
  - editor/temp backups (`*~`, `*.bak`, `*.tmp`, `*.orig`, `*.rej`)
  - Python cache artifacts (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts (`egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed submodule path

By default, scans are first-party only. Use `--include-third-party` to include
`third_party/FunkyDNS` internals.

## Baseline support

Marker findings can be suppressed via a baseline file (default:
`.repo-hygiene-baseline.json`) so scheduled runs can fail only on new markers.

Commands:

```bash
# refresh baseline (typically for known third-party marker debt)
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party

# use a custom baseline file
python3 scripts/repo_hygiene.py scan --repo-root . --baseline-file .repo-hygiene-baseline.json
```

## Usage

```bash
# first-party text scan
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party

# first-party JSON scan (automation-friendly)
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party --json

# first-party clean (removes removable clutter only)
python3 scripts/repo_hygiene.py clean --repo-root . --no-include-third-party

# include third-party internals explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Make wrappers:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```

`scripts/repo_maintenance.py` remains as a compatibility wrapper and delegates
to `repo_hygiene.py`.

## Exit codes

- `0`: no issues remain after the command completes
- `1`: issues remain (`scan`) or non-removable issues remain after `clean`
- `2`: invalid invocation (for example, non-git directory)
