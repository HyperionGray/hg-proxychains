# Repository maintenance workflow

The primary maintenance utility is `scripts/repo_hygiene.py`.

`scripts/repo_maintenance.py` is a compatibility wrapper for legacy automation
that now delegates to `repo_hygiene.py` with equivalent options.

See `docs/REPO-HYGIENE.md` for full behavior details.

## Common commands

```bash
# First-party scan (text)
python3 scripts/repo_hygiene.py scan --repo-root .

# First-party scan (JSON)
python3 scripts/repo_hygiene.py scan --repo-root . --json

# Include third_party/FunkyDNS in marker/stray scans
python3 scripts/repo_hygiene.py scan --repo-root . --include-third-party

# Cleanup removable clutter (stray + stale untracked artifacts)
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root . --json

# Refresh baseline from current marker findings
python3 scripts/repo_hygiene.py baseline --repo-root . --include-third-party
```

Legacy wrapper examples:

```bash
python3 scripts/repo_maintenance.py --no-include-third-party
python3 scripts/repo_maintenance.py --no-include-third-party --fix
python3 scripts/repo_maintenance.py --include-third-party --json
```

Makefile targets:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
make maintenance-baseline
```

## Notes

- Cleanup removes only removable clutter; markers and tracked stale artifacts are reported.
- Embedded git repositories are reported but never auto-removed.
- `clean` exit status reflects post-clean state.
