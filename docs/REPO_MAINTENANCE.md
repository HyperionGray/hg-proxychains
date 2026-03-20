# Repository maintenance workflow (compatibility note)

`scripts/repo_maintenance.py` is a compatibility wrapper that forwards to
`scripts/repo_hygiene.py`.

For direct usage and behavior details, see:

- `docs/REPO-HYGIENE.md`

## Wrapper commands

```bash
# first-party scan (default includes third-party unless disabled)
python3 scripts/repo_maintenance.py --root .

# first-party-only scan
python3 scripts/repo_maintenance.py --root . --no-include-third-party

# cleanup mode (delegates to repo_hygiene clean)
python3 scripts/repo_maintenance.py --root . --fix --no-include-third-party

# custom baseline file path
python3 scripts/repo_maintenance.py --root . --baseline-file .repo-hygiene-baseline.json
```

Notes:

- `--json` on the wrapper is accepted for compatibility and prints a warning.
- New automation should call `scripts/repo_hygiene.py` directly.
