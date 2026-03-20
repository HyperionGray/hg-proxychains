# Repository maintenance workflow (legacy wrapper)

`scripts/repo_maintenance.py` is retained for compatibility with older
automation callers. It delegates to `scripts/repo_hygiene.py`.

Primary maintenance documentation now lives in:

- `docs/REPO-HYGIENE.md`

## Preferred commands

Use `repo_hygiene.py` directly for new automation:

```bash
python3 scripts/repo_hygiene.py scan --repo-root .
python3 scripts/repo_hygiene.py clean --repo-root .
python3 scripts/repo_hygiene.py scan --repo-root . --json
```

Makefile wrappers:

```bash
make maintenance
make maintenance-fix
make maintenance-json
make maintenance-all
make maintenance-all-json
```

## Compatibility wrapper notes

`repo_maintenance.py` accepts legacy flags and maps them to hygiene commands:

```bash
# legacy scan (delegates to repo_hygiene.py scan)
python3 scripts/repo_maintenance.py --root .

# legacy cleanup (delegates to repo_hygiene.py clean)
python3 scripts/repo_maintenance.py --root . --fix
```

The wrapper defaults to `--include-third-party`; pass
`--no-include-third-party` for first-party-only scans.
