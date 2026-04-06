# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is now a compatibility wrapper.

Use `scripts/repo_hygiene.py` directly for all maintenance checks and cleanup.
Primary documentation has moved to:

- `docs/REPO-HYGIENE.md`

- Unfinished markers in tracked files (`TODO`, `FIXME`, `STUB`, `TBD`, `XXX`, `UNFINISHED`)
- Backup files (`*~`, `*.bak`, `*.orig`, `*.old`, `*.tmp`)
- Stray Python cache directories (`__pycache__/`)
- Known stale artifacts (default: `egressd-starter.tar.gz`)
- Embedded git repositories outside the allowed third-party submodule path

By default, marker scanning includes tracked files in `third_party/FunkyDNS` when that repository is present.
For day-to-day repo automation, prefer the first-party-only mode (`--no-include-third-party`)
to avoid noise from external dependency internals.

## Commands

```bash
# Human-readable summary + findings (exits non-zero if issues exist)
python3 scripts/repo_hygiene.py scan --repo-root .

# JSON output for automation
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party marker scan explicitly
python3 scripts/repo_maintenance.py --include-third-party

# Remove backup files + stray cache dirs + stale artifacts while scanning
python3 scripts/repo_maintenance.py --fix

# Add extra stale artifact paths at runtime (repeatable)
python3 scripts/repo_hygiene.py scan --repo-root . \
  --stale-artifact logs/stale.log \
  --stale-artifact tmp/generated.tar.gz
```

Optional repo-local stale artifact list:

```bash
# one repo-relative path per line; '#' starts a comment
cat > .repo-hygiene-stale-artifacts.txt <<'EOF'
# Generated artifacts to report and clean when untracked
logs/stale.log
tmp/generated.tar.gz
EOF
```

Makefile wrappers:

```bash
make maintenance        # first-party only
make maintenance-fix    # first-party only + cleanup
make maintenance-json   # first-party only + JSON

# optional full scan including third_party/FunkyDNS internals
make maintenance-all
make maintenance-all-json
```

## Notes

- `--fix` removes backup files, stray `__pycache__/` directories, and known stale artifacts.
- Stale artifacts are resolved from three sources:
  1) built-in defaults,
  2) `.repo-hygiene-stale-artifacts.txt` if present (override with `--stale-artifacts-file`),
  3) any `--stale-artifact PATH` arguments.
- Unfinished markers are reported but not modified automatically.
- Embedded git repositories are reported but never auto-removed by `--fix`.
- Without `--fix`, exit code is `1` when any issues are found.
- With `--fix`, exit code reflects post-fix state (`0` when only removable clutter was found and removed; `1` if issues remain).
