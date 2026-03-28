## Next task plan

1. Extend `scripts/repo_hygiene.py` to optionally report nested non-submodule git worktrees separately from accidental embedded repos, so automation can classify intent.
2. Add one integration-style unit test that simulates a valid submodule gitlink plus a nested accidental repo under `third_party/` and verifies include/exclude behavior.
3. Wire a `make maintenance-strict` target that fails on any baseline-suppressed markers older than a configurable age window.

