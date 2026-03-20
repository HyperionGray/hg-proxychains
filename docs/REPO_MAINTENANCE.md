# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is a compatibility wrapper around
`scripts/repo_hygiene.py`.

Use `repo_hygiene.py` directly for new automation and local workflows. See
`docs/REPO-HYGIENE.md` for complete behavior details.

## Commands

```bash
# Wrapper defaults to first-party scanning
python3 scripts/repo_maintenance.py

# Include third_party internals
python3 scripts/repo_maintenance.py --include-third-party

# Remove removable clutter
python3 scripts/repo_maintenance.py --fix

# Forward JSON output
python3 scripts/repo_maintenance.py --json
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

- Wrapper flags map directly to `repo_hygiene.py` (`scan` by default, `clean` with `--fix`).
- Use `--baseline-file` if you need a non-default suppression file path.
