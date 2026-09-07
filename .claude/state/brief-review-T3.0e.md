# Brief review-T3.0e — adversarial review of the spot universe exit band (commit `abf8e80`)

**Owner:** Sexta-feira on Hermes, acting as `code-reviewer` **and** `risk-engine-guardian` (read both role cards in `.claude/agents/` first). **Read-only: edit nothing except `.claude/state/review-T3.0e.md`. Do not commit, do not push.** Operational rule: never a background shell; foreground commands with a timeout <= 5 min; do not run testcontainers suites (read the tests instead); do not touch `.env*`. Base: `main` at `49281c9`.

## Why it matters
The spot universe is the gate of what the paper wallet may trade. D12 (`.claude/state/decisions-delegated-2026-09-07.md`) fixed the rule: **admission unchanged** (>= 50 M USDT/24h, inclusive, `TRADING`, quote USDT, outside the blocklist, readable ticker); a pair already admitted leaves only below 40 M for 3 consecutive refreshes (durable streak); losing `TRADING`/quote/blocklist exits immediately. A pair below 50 M must never enter by any path.

## Read
`.claude/state/brief-T3.0e-spot-universe-hysteresis.md`, `.claude/state/notes-T3.0e.md`, `docs/PIPELINE.md` §1d, then the diff: `git show abf8e80 --stat` and `git diff 999640a..abf8e80 -- services/market-worker packages/core/hunter_core/observability.py docs/PIPELINE.md`. Files: `services/market-worker/hunter_market_worker/{spot_universe,spot_band,universe_repo,heartbeat,persist,backfill,durable}.py` and the tests `services/market-worker/tests/{test_spot_band,test_spot_universe,test_heartbeat,test_persistence_contracts,test_backfill_consumer}.py`.

## Questions (each answer with file:line, the concrete failure scenario, and the proposed fix)
1. Did admission change by a single comma? Compare the entry condition before/after line by line. Can a pair with < 50 M enter through streak restoration, an unreadable ticker, reordering, or the band code path?
2. `monitor_by_floor` in `universe_repo.py` now resets `is_monitored` in bulk before reapplying ranks: is there a window where a symbol is visibly `is_monitored = false` to another reader (shard, API, scanner) mid-transaction, or any read outside the transaction? Is the perpetual path really untouched (cite the only caller)?
3. The streak in Redis `mkt:{ex}:spot:band_state`: what happens on `FLUSHALL` or a Redis swap — does the pair exit immediately, need 3 new readings, or re-enter wrongly? Two processes both believing they are shard 0? Does the key follow the grammar of `hunter_core.redis.keys`?
4. `removed_reasons` on the universe event: additive for old consumers? Perpetual event id unchanged?
5. `market_spot_dropped_events_total`: did the spot loop stop incrementing the shared counter? Cite both lines.
6. `market_type` in logs: `backfill.py` hardcodes `"perpetual"` — true today, or a lie once spot has backfill?
7. Tests: the restart proof creates a new adapter but reuses the same fake Redis — does it prove durability, or only that the key exists?
8. File sizes and budgets.

## Output
`.claude/state/review-T3.0e.md` in Portuguese: sections "Bloqueantes", "Antes do deploy", "Depois"; end with two lines: "Bloqueia o deploy da VPS: sim/não" and "A admissão mudou: sim/não". Final chat message: the two lines plus a three-line summary. Before writing STATUS, run `git status -sb` and confirm the only change is the review file.
