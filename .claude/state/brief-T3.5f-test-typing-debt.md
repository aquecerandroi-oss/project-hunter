# Brief T3.5f — the pyright debt in the execution-worker tests (179 errors) and the admission adapter test

**Owner:** test-engineer. **Reviewer afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation, one at a time; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`.** Base: `main` at `04f949d`. Dispatch when no other agent is editing `services/execution-worker/**` or `apps/api/tests/unit/test_admission_adapter.py`.

## What three agents reported (2026-09-08)
`uv run pyright` on the whole repo: ~179 errors, all in `services/execution-worker/tests/**` (first seen as 160 in `test_restart_recovery.py`, T3.15b) and `apps/api/tests/unit/test_admission_adapter.py` (19). Production packages are at 0. The gate `uv run pyright <paths>` is run per task on touched files, so this debt never blocked a task — and it hides real typing mistakes in the tests that prove the wallet.

## Deliver
1. Bring every file under `services/execution-worker/tests/**` and `apps/api/tests/unit/test_admission_adapter.py` to `pyright` 0 errors **without loosening the config** and without `# type: ignore` sprays: typed builders/fixtures, `cast` only where the test intentionally feeds the wrong type (with a comment), protocol types for the fakes.
2. Keep behaviour: every touched test file runs green after (one file per invocation; list them with real output).
3. Add `services/execution-worker/tests` and `apps/api/tests` to whatever pyright scope CI runs (`.github/workflows/ci.yml` or `pyproject.toml` pyright section — read `docs/DEPLOYMENT.md` §7 first) so the debt cannot return silently.

## Prove
`uv run pyright services/execution-worker apps/api` → 0 errors; the test files' real output; `ruff check`/`format --check`. Report in Portuguese, extended format; `.claude/state/notes-T3.5f.md`.
