# Repository maintenance workflow (legacy note)

`scripts/repo_maintenance.py` is a compatibility wrapper.

Use `scripts/repo_hygiene.py` directly for maintenance checks and cleanup.
Current primary documentation lives in:

- `docs/REPO-HYGIENE.md`

## Wrapper behavior

`repo_maintenance.py` delegates to `repo_hygiene.py`:

- default mode includes `third_party/FunkyDNS`
- use `--no-include-third-party` for first-party-only scheduled checks
- `--fix` maps to `repo_hygiene.py clean`
- `--baseline-file` is forwarded to the underlying scanner

## Recommended Make targets

```bash
make maintenance         # first-party scan
make maintenance-fix     # first-party scan + cleanup
make maintenance-json    # first-party JSON scan
make maintenance-all     # include third_party/FunkyDNS
make maintenance-all-json
make maintenance-baseline
```
