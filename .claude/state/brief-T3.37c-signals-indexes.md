# Brief T3.37c — índices para os totais e a paginação por cursor da tabela de sinais do Lab (pedido do T3.37a)

**Owner:** database-architect. **Reviewer afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation, one at a time; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks them); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only (`EXPLAIN` only).** Base: `main` at `67cbe22`. Scope: `infra/migrations/versions/0014_*.py`, `packages/core/hunter_core/db/models/**` (index declarations only), `apps/api/tests/integration/test_lab_signals_explain.py` (extend), `docs/DATABASE.md`.

## Source
`.claude/state/notes-T3.37.md` §T3.37a "Pedido para database-architect": with `strategy_version_id` the page query uses `ix_agent_signals_version_emitted` (20–40 ms on 6 000 rows); without it (the Lab's default "todas as versões") it is a `Seq Scan` + in-memory `Sort` — fine today only because the table fits in cache. `agent_signals` grows ~1 600 rows/day now and will grow faster with 6 versions.

## Deliver
1. Migration `0014_lab_signals_indexes`: (a) composite index on `agent_signals (strategy_version_id, cohort, emitted_at DESC, id DESC)` — check the exact cohort expression the repository filters on (`COHORT` JSONB expression? then an expression index on that expression, same text as `lab_common.py`); (b) a partial index for the default view: `(emitted_at DESC, id DESC) WHERE cohort = 'prospective'` (same expression); (c) `signal_outcomes (tracking_state)` or the composite the `totals` query needs (read `lab_signals.py` `_totals_query`). `CREATE INDEX CONCURRENTLY` is not possible inside Alembic's transaction — say which choice you made (plain index, table is small today; note the lock) and the downgrade.
2. `EXPLAIN (ANALYZE, BUFFERS)` before/after on the testcontainer with 50 000 seeded rows across 6 versions, for: page 1 all versions, page 1 with `state=closed`, totals query; paste plans; the explain test asserts an Index Scan for the default view.
3. Run the same `EXPLAIN` (no ANALYZE writes needed; `EXPLAIN` only) on the VPS read-only to show the current plan on real volume, before the migration is applied (the deploy applies it).
4. `docs/DATABASE.md`: the indexes and why.

## Prove
`uv run alembic upgrade head` / `downgrade -1` on the testcontainer; per-file tests with real output; `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format; append "T3.37c" to `.claude/state/notes-T3.37.md`.
