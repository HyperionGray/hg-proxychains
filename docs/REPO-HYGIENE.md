# Repo hygiene

`scripts/repo_hygiene.py` is the primary scanner/cleaner. The legacy
wrapper `scripts/repo_maintenance.py` delegates to it (`make maintenance` /
`make maintenance-fix`).

This repository includes a maintenance utility at `scripts/repo_hygiene.py`
for scheduled cleanups and local checks.

## What it checks

- Unfinished markers in tracked files:
  - `TODO`
  - `FIXME`
  - `STUB`
  - `TBD`
  - `XXX`
  - `WIP`
  - `UNFINISHED`
- Common untracked stray artifacts:
  - editor backups (`*~`, `*.bak`, `*.orig`, `*.rej`)
  - temporary files (`*.tmp`)
  - Python cache outputs (`__pycache__/`, `*.pyc`, `*.pyo`)
  - common metadata noise (`.DS_Store`, `Thumbs.db`)
  - known generated bundles (`egressd-starter.tar.gz`)

The scanner intentionally skips `third_party/FunkyDNS/` when checking
unfinished markers by default, because that path is managed as an external
dependency.

When you do want full-repo scanning (including nested third-party git state),
use `--include-third-party`.

Known upstream unfinished markers can be recorded in a baseline file so
scheduled jobs can fail only on new findings.

## Usage

From repo root:

```bash
# Text report
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON report for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third-party dependency tree explicitly
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Remove untracked stray files/directories
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py scan --repo-root . --json
```

JSON output for automation:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . --json
python3 scripts/repo_hygiene.py clean --repo-root . --json
```

Optional deep scan including `third_party/FunkyDNS` unfinished markers:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party
```

Track additional stale artifacts for one-off cleanup runs:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . \
  --stale-artifact dist/build.tar.gz \
  --stale-artifact tmp/cache.db
```

`--stale-artifact` is repeatable and works for both `scan` and `clean`.

Exclude paths from all hygiene checks:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . \
  --exclude-path "third_party/FunkyDNS/archive/**" \
  --exclude-path "docs/generated/**"
```

`--exclude-path` uses shell-style globs against repository-relative paths.

Or through Make targets:

```bash
make maintenance
make maintenance-fix
make repo-scan
make repo-clean
make repo-scan-json
```

`scripts/repo_maintenance.py` is retained as a compatibility wrapper and now
delegates to `scripts/repo_hygiene.py`.

## Optional config file

`repo_hygiene.py` optionally loads `.repo-hygiene.json` from the repo root.
This allows scheduled jobs to keep shared defaults without repeating long
CLI flags.

Supported keys:

- `include_third_party` (boolean)
- `baseline_file` (string)
- `stale_artifacts` (array of paths)
- `exclude_paths` (array of glob patterns)

Example:

```json
{
  "include_third_party": false,
  "baseline_file": ".repo-hygiene-baseline.json",
  "stale_artifacts": [
    "dist/build.tar.gz"
  ],
  "exclude_paths": [
    "third_party/FunkyDNS/archive/**"
  ]
}
```

Notes:

- CLI flags override config values where both are provided.
- `--stale-artifact` and `--exclude-path` append to configured lists.
- Use `--no-config` to ignore `.repo-hygiene.json` for a run.

## Exit codes

- `0`: no issues remain after the command completes
- `1`: blocking issues found
  - `scan`: unfinished markers, stray untracked files, or stale artifacts
  - `clean`: unfinished markers or tracked stale artifacts (removable clutter is deleted)
- `2`: invalid invocation (for example, non-git directory)

## Baseline file

By default, `scan`/`clean` load marker suppressions from:

- `.repo-hygiene-baseline.json`

Override with `--baseline-file <path>`.

The baseline currently suppresses marker findings only (not stray files).

## Legacy script

`scripts/repo_maintenance.py` remains as a compatibility wrapper and delegates
to `repo_hygiene.py`.
