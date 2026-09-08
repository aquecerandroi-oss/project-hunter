# Brief T3.39b — fecha a revisão da T3.39 (risk-engine-guardian): a trava de posições da linha paper tem de olhar o caminho real, `--supersede` respeita a mesma trava, flags só com `--deprecate`, diff antes de escrever

**Owner:** backend-specialist. **Reviewer afterwards:** risk-engine-guardian (same reviewer). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only.** Base: `main` at `e10fca4`. Scope: `services/strategy-worker/hunter_strategy_worker/{deprecate,supersede}.py`, `infra/scripts/{activate_strategy_version,seed_cli,seed_dry_run}.py`, their tests, `docs/ACTIVATION.md`, `.claude/state/notes-T3.39.md`.

## Findings to close (review of 4929b99)
- **ALTA-1** `deprecate.py:62-70`: `positions.agent_id` is never written in production (`execution-worker/positions.py:168` INSERT has no `agent_id`); the real link is `positions.metadata->>'proposal_id' → orders.proposal_id → trade_proposals.agent_id → agents.strategy_version_id`. Rewrite the open-positions check on that path, count only live positions (`status <> 'closed' AND NOT is_residual`, the project's own definition — BAIXA-6), and test it by opening the position the way production does (no `agent_id`), expecting refusal.
- **ALTA-2** `supersede.py:108-131`: `--supersede` retires the origin without the paper guard and creates the successor with default `purpose`. Apply the same guard (`purpose = paper` → refuse unless `--force-paper` and exposure clean; `live` → refuse), copy `purpose` to the successor explicitly (paper line stays paper), test both; fix `docs/ACTIVATION.md:273` accordingly.
- **MÉDIA-3** `activate_strategy_version.py:279-288`: `--successor`/`--force-paper` without `--deprecate` must be a `parser.error`; test.
- **MÉDIA-4** `seed_cli.py:104-133`: print the diff **before** `commit()`; when the diff is non-empty and stdin is not a TTY require `--yes` (or `--dry-run`) — never write silently in a pipe; test.
- **MÉDIA-5** `seed_cli.py:68-79`: assert `set(_run_everything) == set(SEEDED_TABLES)` in a test.
- **BAIXA-7**: tests for the `shadow_episodes` half of the guard, `--only risk_profiles` with a changed limit requiring `--yes`, and the `strategy_version_deprecated` audit row (`params_format` included — BAIXA-11).
- **BAIXA-9**: `--only strategies` dry-run diff shows `strategy_versions` changes too.
- **BAIXA-10**: `test_seed_dry_run.py:106-119` must not depend on test order.
- **BAIXA-12**: fix the two stale statements in `notes-T3.39.md`; add the 60 s roster TTL note to ACTIVATION §7b (a deprecated version still evaluates up to one minute).

## Prove
Per-file tests with real output, `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format; append "T3.39b" to `.claude/state/notes-T3.39.md`.
