# Brief T3.7d — the historical lane cannot be monopolized: fair share per market, and a terminal state for windows before a market's listing

**Owner:** exchange-integration-specialist. **Reviewers afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation, one at a time; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`; do not stop or recreate local stack containers.** Base: `main` at `96cb101` or later.

## Incident (VPS, 2026-09-08, `.claude/state/notes-T3.7b-diag.md`)
The 31-day backfill for the β universe left BTCUSDT and UNIUSDT at 14 days for 8 h while ETH/SOL/XRP/DOGE completed. Both live on shard 3 with MARSCOINUSDT, listed on 2026-09-01 09:45Z: its four pre-listing windows can never be filled (the exchange returns 200 with 0 rows), so `recover_registered` retries them to `attempts = 5`, marks `failed`, reopens them an hour later, and — because their `gap_end` is the newest on the shard — they take all 6 slots of every 60 s history cycle, forever. BTC's 109 gaps had `attempts = 0` after 8 h. The operator retired the 148 impossible rows by hand (`status = 'recovered'`, an admitted misnomer) to unblock β; the code must make that impossible to repeat.

## Read first
`services/market-worker/hunter_market_worker/{recovery,recovery_queries,recovery_drain,backfill,backfill_plan,backfill_priority}.py`, `docs/PIPELINE.md` §1b, `docs/DATABASE.md` (`ingestion_gaps`), `.claude/state/notes-T3.7b.md` §CONCERNS 1 and `notes-T3.7b-diag.md`, the gap status vocabulary in `packages/core/hunter_core/domain/enums.py` (and the DB CHECK if any — if the status set is constrained by a CHECK, the new value is a migration: write the brief for `database-architect` instead of editing `infra/migrations/**`).

## Deliver
1. **Terminal state for impossible windows**: when a history fetch for a window entirely before the market's first available candle on the exchange returns 0 rows (detect with the exchange's earliest-candle probe, or `onboardDate` from `exchangeInfo`, or the empty response on a window that starts before the listing — pick the cheapest reliable signal and say why), mark the gap `unrecoverable` with a reason (`before_listing`) and never reopen it. Metrics/heartbeat count them separately (`open_gaps` must exclude them; a new `unrecoverable_gaps` field). If the status needs a schema change, brief the database-architect and implement the code against the new value behind a feature check.
2. **Fair share in the history lane**: the per-cycle budget (6 chunks) is spread round-robin across markets with open historical gaps (or weighted by explicit requests from `request_backfill.py` first), never `gap_end DESC` globally — one market cannot take every slot. Keep the recent-gap lane untouched (live gaps still win).
3. **`failed` is not a loop**: after `attempts = 5`, a gap reopens at most N times (say 3) with exponential backoff, then goes `unrecoverable` with reason `exhausted` — visible, not silent.
4. Tests: a listing-date scenario (windows before listing → terminal, after listing → recovered); fairness (two markets, 12 gaps each, 6 slots → both progress); the reopen cap. `services/market-worker/tests/test_recovery*.py`, `test_backfill_priority.py`.
5. Docs: `docs/PIPELINE.md` §1b; `docs/DEPLOYMENT.md` how to read `unrecoverable_gaps`.

## Prove
Per-file test runs with real output, `ruff`/`pyright`/`check_file_size.py`; a short local proof with the fake adapter returning 0 rows before a listing date. Report in Portuguese, extended format; `.claude/state/notes-T3.7d.md`.
