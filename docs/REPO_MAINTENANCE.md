# Repository maintenance workflow

Primary maintenance tooling is `scripts/repo_hygiene.py`.
`scripts/repo_maintenance.py` remains as a compatibility wrapper.

## What `repo_hygiene.py` checks

- Unfinished markers in tracked source/config files:
  `TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `WIP`, `UNFINISHED`
- Stray untracked clutter:
  backup/temp files (`*~`, `*.bak`, `*.tmp`, `*.orig`, `*.rej`), cache files, and cache dirs
- Known stale artifacts:
  currently `egressd-starter.tar.gz` (tracked or untracked)

By default, scans are first-party only (`--no-include-third-party`).
Use `--include-third-party` for full scans that include `third_party/FunkyDNS`.

## Baseline support for known dependency markers

When scanning with `--include-third-party`, use a marker baseline to suppress known
dependency TODO/FIXME lines that are currently accepted:

```bash
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party --baseline-file .repo-hygiene-baseline.json
```

During `scan` and `clean`, matching baseline entries are reported as
`suppressed_unfinished_markers` instead of blocking the run.

## Commands

```bash
# Human-readable summary + findings (non-zero if issues exist)
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party --baseline-file .repo-hygiene-baseline.json

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party --baseline-file .repo-hygiene-baseline.json --json

# Remove removable clutter, then re-scan
python3 scripts/repo_hygiene.py clean --repo-root . --no-include-third-party --baseline-file .repo-hygiene-baseline.json

# Full scan including third_party/FunkyDNS
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party --baseline-file .repo-hygiene-baseline.json
```

Makefile wrappers:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Exit behavior

- `scan`: returns non-zero when any issue remains.
- `clean`: deletes removable clutter, then re-scans; returns non-zero if any issue remains after cleanup.
- `baseline`: always returns zero after writing the baseline file.
