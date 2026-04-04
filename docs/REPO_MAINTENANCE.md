# Repository maintenance workflow

`scripts/repo_maintenance.py` is a compatibility wrapper around
`scripts/repo_hygiene.py`.

Use `repo_hygiene.py` directly for full control, or use the wrapper/Make targets
for compatibility and simpler scheduled automation.

## Command mapping

Wrapper command:

```bash
python3 scripts/repo_maintenance.py [flags]
```

Delegated command:

```bash
python3 scripts/repo_hygiene.py scan --repo-root . [flags]
# or clean when --fix is provided
```

Supported wrapper flags:

- `--root <path>`: repo root (default `.`)
- `--fix`: run cleanup mode (`repo_hygiene.py clean`)
- `--json`: emit JSON report
- `--baseline-file <path>`: override baseline file path
- `--include-third-party` / `--no-include-third-party`
- `--fail-on-suppressed-markers`: fail even when only baseline-suppressed markers exist

## Make targets

```bash
make maintenance             # first-party scan
make maintenance-json        # first-party scan in JSON
make maintenance-fix         # first-party cleanup mode
make maintenance-strict      # first-party scan + fail on suppressed markers
make maintenance-strict-json # strict mode with JSON output

# optional full scan including third_party/FunkyDNS internals
make maintenance-all
make maintenance-all-json
```

## Behavior notes

- `--fix` removes backup files, stray `__pycache__/` directories, and known stale artifacts.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `--fix`.
- Baseline-suppressed markers are non-blocking by default; use
  `--fail-on-suppressed-markers` for strict automation/debt-burn runs.
