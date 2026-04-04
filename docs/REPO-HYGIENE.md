# Repo hygiene

`scripts/repo_hygiene.py` is the primary repository hygiene tool.
`scripts/repo_maintenance.py` is a compatibility wrapper that delegates to it.

## What it checks

- Unfinished markers in tracked source/config files:
  - `TODO`
  - `FIXME`
  - `STUB`
  - `TBD`
  - `XXX`
  - `WIP`
  - `UNFINISHED`
- Untracked clutter:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - metadata noise (`.DS_Store`, `Thumbs.db`)
- Known stale artifacts:
  - `egressd-starter.tar.gz`
- Unexpected embedded git repositories (outside allowed paths)

By default, scanning is first-party focused and skips `third_party/FunkyDNS`
internals. Use `--include-third-party` for full-repo scanning.

## Usage

From repo root:

```bash
# Human-readable scan
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party

# JSON scan for automation
python3 scripts/repo_hygiene.py scan --repo-root . --no-include-third-party --json

# Remove removable clutter (stray files/dirs + known stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root . --no-include-third-party

# Full scan including third_party/FunkyDNS internals
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Make targets:

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

## Baseline handling

`scan` and `clean` load marker suppressions from `.repo-hygiene-baseline.json`
by default. Override with `--baseline-file <path>`.

The baseline suppresses marker findings only. It does not suppress stray files,
stale artifacts, or embedded git repos.

For strict scheduled jobs, use:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . --fail-on-suppressed-markers
```

That flag returns a failure even if all unfinished markers were suppressed by
the baseline.

## Exit codes

- `0`: no blocking issues remain
- `1`: blocking issues found
  - `scan`: findings exist (or suppressed findings when using
    `--fail-on-suppressed-markers`)
  - `clean`: unresolved findings remain after cleanup (or suppressed findings
    when using `--fail-on-suppressed-markers`)
- `2`: invalid invocation (for example, non-git directory)
