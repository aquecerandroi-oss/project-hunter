# Fix brief — T1.3 part A2: sampling, gap recovery, funding watermarks, universe ranking

You are fixing an existing, working implementation. Baseline **verified by the orchestrator right before dispatch**: `uv run pytest services/market-worker -q -p no:cacheprovider` → **83 passed in 77s**. Every item below is an accepted finding with a concrete failure scenario, reconciled from `code-reviewer`, `exchange-integration-specialist`, `database-architect` (two passes, measured against a real Postgres) and an adversarial second opinion from the original implementer (Astra/GPT-6).

Do not redesign. Make the minimal correct change and prove each one with a test that **fails before your change and passes after** — run it before, keep the failure output, then fix.

A second agent (**A1**) is working **in parallel** on `persist.py`, `persist_rows.py`, `queues.py`, `main.py`, a new `partitions.py`, `packages/core/hunter_core/db/session.py` and their tests. Touching those files will collide and both diffs will be thrown away.

## Files you may touch (nothing else)
- `services/market-worker/hunter_market_worker/recovery.py`
- `services/market-worker/hunter_market_worker/sampling.py`
- `services/market-worker/hunter_market_worker/funding.py`
- `services/market-worker/hunter_market_worker/universe.py`
- `services/market-worker/tests/test_recovery.py`, `test_recovery_contracts.py`, `test_universe.py`, `test_funding.py`
- `services/market-worker/tests/test_persist.py` — **only** the two snapshot tests (`testsnapshot_loop_writes_one_row_with_nulls_when_hot_state_missing` at lines 89-102 and `testsnapshot_loop_reads_hot_state_when_present`) and the open-interest test `testoi_poll_loop_writes_history_and_hot_state`. Leave every other test in that file alone; if one of them fails, it is A1's work in flight.
- New test files you create under `services/market-worker/tests/` (suggested: `test_sampling.py`)

**Forbidden (A1 or another task owns them right now):** `services/market-worker/hunter_market_worker/{persist,persist_rows,queues,main,partitions,heartbeat,ingest,hot_state,streaming,supervision,publication,config,wire}.py`, `services/market-worker/tests/{test_persistence_contracts,conftest,fakes,builders,db_helpers,test_contracts,test_hot_state,test_ingest_coalesce,test_ingest_integration,test_supervision,test_heartbeat,test_config,test_role_registration}.py`, `services/market-worker/README.md`, all of `packages/core` (including `observability.py`), `packages/exchange-adapters/**`, `apps/**`, `infra/**`, `docs/**`, `.env`.

**Already done for you by the orchestrator — use it, do not re-create it:**
- Every new Prometheus metric you need is already declared in `packages/core/hunter_core/observability.py`. Import them; **do not edit that file**:
  `market_snapshot_stale_fields_total` (label `field`), `market_snapshot_skipped_no_data_total`, `market_sampling_bucket_skipped_total` (label `loop`), `market_ingestion_gaps` (labels `exchange`, `status`).
- `hunter_market_worker.persist_rows.oi_bucket(ts)` already exists (5-minute UTC grid, idempotent). Import it; do not duplicate the `.replace(minute=...)` arithmetic.

**No Alembic migration.** If a fix would need a schema change, report it as NOT FIXED with the exact DDL you would need.
**Never `git commit` / `git push` / `git add` / `git checkout` / `git stash`.**

## Hard rules (CLAUDE.md)
`Decimal` for every monetary/quantity value; **UTC** everywhere persisted, `time.monotonic()` only for watchdogs and internal age; **no file over 350 lines** (`uv run python infra/scripts/check_file_size.py`; `universe.py` is already at 314 — keep it under budget, extract a helper module only if you must and say so); `structlog` via `get_logger`, never `print`; no local state on disk; **no fake data** — absence becomes `stale`/`degraded`/`unavailable`, never a stale value republished as fresh; every meaningful mutation observable.

---

## H5 — the minute snapshot copies `mark_price` without checking `mark_ts`
`sampling.py:104-121`. The snapshot stamps `snapshot_ts = align_open_time(utcnow(), M1)` and copies `mark_price`, `funding_rate`, `open_interest`… straight out of the Redis hash without consulting the per-field `*_ts` written by `hot_state.py`.

**Scenario:** the mark-price stream dies while the OI poll keeps writing and keeps the shared 600 s TTL alive. The same stale `mark_price` is written into `market_snapshots` minute after minute as if it were a fresh observation, and nothing in the row distinguishes "unchanged" from "not updated". The scanner and the indicators of M2 read it as a live series.

**Fix:** read `mark_ts`, `oi_ts` and `funding_ts` from the hash and, per field, write `None` when that field's own timestamp is older than `settings.market_stale_after_s` relative to `snapshot_ts`. Ownership: `mark_ts` → `mark_price`, `index_price`; `oi_ts` → `open_interest`, `open_interest_value`; `funding_ts` → `funding_rate`. A missing `*_ts` means the field was never written → `None`. Increment `market_snapshot_stale_fields_total.labels(field=...)` for each dropped field so the omission is observable. `write_snapshots` therefore needs `settings` (it does not take it today) — thread it from `snapshot_loop`, which already has it. Read `hot_state.py` first to confirm the exact hash field names before you code; do not guess.

**Test:** a hash with a fresh `oi_ts` and a `mark_ts` older than the threshold produces a snapshot row with `mark_price=None`, `open_interest` intact, and a bumped counter.

---

## D9 — an all-NULL snapshot row is written when there is no hot state at all
`sampling.py:98-121`, and `tests/test_persist.py:89-102` currently asserts this as intended behaviour. Because the insert is `ON CONFLICT (market_id, ts) DO NOTHING`, that empty row is **permanent**: the real observation that arrives 20 s later can never replace it.

**Scenario:** the worker starts, the universe refresh runs before the WebSocket has delivered anything, and the first minute of every market is a row of NULLs that the M2 scanner reads as "market observed, no price".

**ORCHESTRATOR DECISION:** skip the market entirely when both the ticker hash and the derivatives hash are empty; count it in `market_snapshot_skipped_no_data_total`. Absence of a row means "not observed" — that is the honest encoding, and the orchestrator is adding the corresponding note to `docs/DATABASE.md` §4 (**do not edit that file yourself**).

**Fix:** implement the skip and **rewrite the test at `test_persist.py:89-102`** so it asserts the new contract (no row, counter bumped) instead of the old one. Keep writing the row when at least one of the two hashes has data (with the H5 staleness rules applied to the individual fields).

---

## D1 — `spread_pct` is a FRACTION and stays a fraction (the old M4 finding is WRONG)
`sampling.py:51-57`. An earlier brief said `_spread_pct` should be multiplied by 100 to match `hunter_core.domain.market.NormalizedTicker.spread_pct`. The second database review overturned it: `docs/DATABASE.md:12` and `packages/core/hunter_core/db/models/_common.py:23` define `NUMERIC(9,6)` percentage columns as a **fraction** (0.012 = 1.2%), so `(ask - bid) / mid` is already correct and the domain helpers are the divergent ones.

**ORCHESTRATOR DECISION: do NOT change `_spread_pct`.** Fixing the domain helpers is follow-up **T1.1c**, outside T1.3.
**Fix required from you:** only a regression test that pins the convention — bid 99 / ask 101 → the persisted `spread_pct` is `Decimal("0.02")`, not `2` — so the next reviewer cannot "fix" it back.

---

## M5 (= LOW-10) — the sampling loops drift and skip buckets
`sampling.py:69-70` and `:146-147`. Both loops `await asyncio.sleep(interval)` and only then do the work, so the real period is `interval + work_time` and neither is aligned to the UTC grid the tables are keyed on.

**Scenario:** an OI round over 200 markets takes two minutes; each market is then polled roughly every seven minutes. Two of the 5-minute UTC buckets have no reading at all, and aligning the sample to a bucket afterwards does not bring back the ones that were skipped. The snapshot loop drifts the same way against the minute grid.

**Fix:** sleep until the **next aligned UTC boundary** instead of a fixed duration — compute the delay from `utcnow()` to the next multiple of the interval and sleep that. When the boundary that just passed was missed because the previous round overran, increment `market_sampling_bucket_skipped_total.labels(loop=<"snapshot"|"open_interest">)` and log a warning. Keep `time.monotonic()` out of this: the grid is wall-clock UTC.

**Test:** with an injectable clock/sleep, a round whose work takes longer than the interval schedules the next run at the following boundary (not `interval` seconds after the work ended) and counts one skip.

---

## D8 — the open-interest bucket is derived per reading instead of per cycle
`sampling.py:179-190` (and the same rule, already extracted into `oi_bucket()`, on the persistence side).

**Scenario:** the sequential poll of 200 markets straddles a 5-minute boundary. The first 120 markets land in bucket N, the rest in bucket N+1, and the next cycle shifts the split. Every market ends up with an irregular grid, and a "5-minute" series that sometimes has two readings for one market and sometimes none.

**Fix:** compute the bucket **once per cycle** — `cycle_bucket = oi_bucket(utcnow())` taken at the start of the round — and attribute every reading of that round to it. The queued item keeps carrying that bucket (the DB column stores the grid slot, never the exact observation time, per `docs/DATABASE.md` §4), while the hot-state write and the `market.derivatives` publication keep the **original** reading with its real timestamp. `oi_bucket()` is idempotent, so the persistence side re-applying it is a no-op.

**Test:** two readings polled either side of a boundary within one cycle persist under the same `ts`; a second cycle produces the next bucket.

---

## HIGH-2 — gap detection costs 1005 statements and 202 transactions per pass
`recovery.py:145-171`. `check_gaps` runs three per-market queries (`_last_open_time`, `_persisted`, the open-gap `SELECT`) inside one long transaction, then one transaction per market for the gap list.

**Measured by the database-architect:** 1005 statements / 202 transactions per pass; **60.6 s** with 200 markets on a 60 s cycle; 601 statements inside a single transaction holding `ACCESS SHARE` on `candles` for ~40 s of every minute, which is what blocks `create_partitions.py`.

**Fix:** replace the per-market queries with set-based ones over the whole monitored universe — `market_id = ANY(:ids)` with `GROUP BY market_id` for the watermarks, one query for the persisted open times in the window, one query for the open/failed gaps — and keep detection (`register_missing`) running every cycle for every market. Keep the transaction short: read, compute in Python, write the new gaps.
**Test:** with N markets, one `check_gaps` pass issues a number of statements that does **not** grow with N for the detection phase (count with a SQLAlchemy event listener); the gaps registered are identical to the ones the current implementation registers for the same fixture.

---

## M3 — one slow cycle destroys the one-minute cadence and holds a row lock open across a REST call
`recovery.py:152-171` and `recover_registered` at `:109-137`. Gaps are processed strictly sequentially, and `adapter.fetch_candles` at `:114` is awaited **inside** the open `role_session` transaction that holds `SELECT ... FOR UPDATE` on the gap row.

**Scenario:** 200 markets need backfill and each REST call takes one second — the calls alone exceed three minutes, so new holes stop being detected at the contracted one-minute cadence, and a single stuck call blocks every market behind it while holding a Postgres transaction and a row lock open for its whole duration.

**Fix:**
1. Bound the work per cycle: process at most `MAX_GAPS_PER_CYCLE = 50` gaps per pass. The remaining gaps are picked up next cycle — that is exactly why they are durable rows.
2. Wrap each `adapter.fetch_candles` in `asyncio.wait_for(..., timeout=20)`; the existing `except Exception` in `recover_registered` already turns that into an incremented `attempts`.
3. Move the fetch **out of** the transaction: fetch first, then open the `role_session`, re-read the gap `FOR UPDATE` (re-checking `status == 'open'`), and write candles + status transition in one transaction. The atomicity the current `begin_nested` provides (candles and the `recovered` transition commit together, proven by an existing rollback test) must be preserved.

**Tests:** with 120 open gaps one cycle processes 50 and returns; a `fetch_candles` that hangs raises `TimeoutError` inside the per-gap handler, increments `attempts` and does not kill the loop; the transaction is **not** open while `fetch_candles` runs (assert from a fake adapter that no session is in a transaction / no connection is checked out); the existing rollback test still passes.

---

## D5 — gap detection races the persistence queue and manufactures phantom gaps
`recovery.py:144`: `end = align_open_time(now, M1) - MINUTE`. The persistence queue tolerates up to `max_age = 60 s` of lag by design.

**Scenario:** the `drain_loop` is 15 s behind. The final candle for minute T is in the queue, not yet in Postgres. `check_gaps` at T+70 s registers a gap for T, fires a REST backfill for it, and does so for **all 200 markets at once** — against a database that is already the bottleneck. Positive feedback: the slower persistence gets, the more backfills recovery piles on.

**Fix:** `end = align_open_time(now, M1) - 2 * MINUTE` (a grace of at least the queue's `max_age`). Name the constant and comment why it equals the queue tolerance.
**Test:** a final candle enqueued but not flushed, `check_gaps` with `now = T + 70 s` → zero gaps registered and zero `fetch_candles` calls.

---

## D6 + MEDIUM-5 — `failed` gaps suppress detection forever and keep the alarm stuck
`recovery.py:79-91` (`register_missing` subtracts `covered` computed from gaps with status `open` **and** `failed`) and `recovery.py:64-74` (`_count_open_gaps` counts `open` and `failed`, so `heartbeat.open_gaps` never returns to zero).

**Scenario A:** Binance is briefly missing a range of history; five attempts fail; the gap becomes `failed`. Those minutes are subtracted from `missing` on every later cycle, so when the exchange restores the history nothing ever asks for it again — permanent data loss with no signal.
**Scenario B:** one permanently failed gap pins `open_gaps > 0` forever; the operator's "gaps outstanding" alarm never clears and stops meaning anything.
Also in the same function: `expected_times` materializes up to ~300k `datetime` objects per cycle at the bootstrap window of 1499 minutes × 200 markets.

**ORCHESTRATOR DECISION (implement exactly this):**
- Before computing `missing`, **reopen** `failed` gaps whose `detected_at <= now - FAILED_RETRY_AFTER_S` (default 3600 s, a module constant) by setting `status = 'open'` and `attempts = 0`, bounded to at most `MAX_REOPEN_PER_CYCLE = 20` rows per pass. Log each reopen.
- `covered` is then computed from `open` gaps **plus** the `failed` gaps still inside their cooldown — so a failed gap never silently disappears from the ledger and never spawns a duplicate row, but it does get retried instead of suppressing the data forever.
- `_count_open_gaps` counts **only** `status = 'open'` (that is what `heartbeat_state.open_gaps` reports). Publish the `failed` count separately through `market_ingestion_gaps.labels(exchange=..., status=...)` (set both `open` and `failed`). Do **not** touch `heartbeat.py` or the heartbeat hash — A1's and the API's contract stays as it is.
- Bound the memory: never build `expected_times` for a range wider than the detection window you actually query.

**Tests:** a `failed` gap older than the cooldown is reopened and recovered on the next pass with a working adapter; a `failed` gap inside the cooldown is neither reopened nor duplicated by a new `open` row; `heartbeat_state.open_gaps` is 0 when the only gap is `failed`, and `market_ingestion_gaps{status="failed"}` is 1.

---

## M2 — a newly listed perpetual gets an impossible, permanently `failed` gap
`recovery.py:149` / `recover_registered`. Bootstrap computes `start = end - MINUTE * 1499` with no notion of when the market started existing, and registers every missing open time.

**Scenario:** a perpetual listed two hours ago returns all the candles it has. The 22 hours before listing are still demanded; after five attempts the gap becomes `failed` and the market is reported `degraded` forever for history that never existed.

**Fix:** in `recover_registered`, after filtering `closed`, if the list is non-empty and `min(open_time) > gap.gap_start`, set `gap.gap_start = min(open_time)` before the coverage check — the exchange's history simply does not go back further. Log it once per gap (`market_gap_history_starts_later`). Only when the adapter actually returned candles (an empty response means "REST failed / nothing yet", not "history starts later") and only when the fetch covered the whole requested range.
**Test:** a fake adapter that returns only the last 120 minutes of a 1500-minute gap recovers the gap instead of failing it; an adapter returning `[]` still increments `attempts` and eventually fails the gap.

---

## L3 — the cadence gate of `run_recovery` has no test
`recovery.py:179-192`: `if not universe.symbols or (now - last_check < CHECK_INTERVAL_S and reconnects == last_reconnects): continue`. An inverted operator would silently change the gap-detection frequency with nothing failing.
**Fix:** a unit test that pins the gate — no check before `CHECK_INTERVAL_S`, an immediate check when `heartbeat_state.reconnects` increases, no check while the universe is empty.

---

## MEDIUM-6 — the funding watermark costs one query per market per poll
`funding.py:39-44`: a dict comprehension running `SELECT max(funding_time) WHERE market_id = :id` once per market, inside one open transaction.
**Scenario:** 200 markets → 200 round trips every `market_oi_poll_s`, all inside a single transaction, for data one `GROUP BY` returns.
**Fix:** one `SELECT market_id, max(funding_time) FROM funding_rates WHERE market_id = ANY(:ids) GROUP BY market_id`; markets with no history keep their `None` watermark. Behaviour must be identical.
**Test:** the existing funding tests stay green and a new one asserts the statement count does not grow with the number of markets.

---

## HIGH-4 — the universe refresh row-locks every market for seconds
`universe.py:212-224` (`_rank_and_monitor` issues one `UPDATE` per market, ~500 of them) after `refresh_universe:253-257` has already reset `is_monitored`/`monitor_rank` for all of them in the same transaction.
**Scenario:** every market row is exclusively locked for the whole ranking loop (seconds). Any concurrent writer — including the `drain_loop`'s `load_market_ids` path and the API — waits behind it, and the persistence queue ages out while it does.
**Fix:** one `UPDATE markets SET monitor_rank = v.rank, is_monitored = v.monitored FROM (VALUES ...) AS v(id, rank, monitored) WHERE markets.id = v.id`, built with SQLAlchemy `values()` and bound parameters (never string interpolation), with explicit casts for the id and boolean columns. Same resulting ranks and the same `(old_monitored, new_monitored)` return.
**Test:** the existing `test_universe.py` assertions on ranks/monitored sets stay green, plus one test asserting a single `UPDATE` statement is issued for the ranking (event-listener statement count).

---

## Explicitly NOT in scope (do not "fix" these)
- Anything in `packages/exchange-adapters/**` (missing `update_subscriptions`, missing `fetch_realized_funding`, `parse_kline_ws` not filling `event_ts`, missing `restart_connection`) — that is T1.2b, another agent's task right now.
- `lock_timeout` in `infra/scripts/create_partitions.py` and UTC-explicit partition bounds (D4, D12) — out of T1.3, already recorded in the plan.
- The `market.liquidations` publication lost when the process dies between the Postgres commit and the `XADD` — an accepted M1 limitation.
- Any Alembic migration; any change to `docs/**`.

## Verification you must run and paste verbatim in your report
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter
uv run pytest services/market-worker -q -p no:cacheprovider
uv run ruff check services/market-worker && uv run ruff format --check services/market-worker
uv run pyright services/market-worker
uv run python infra/scripts/check_file_size.py
```
Docker Desktop is running; the integration tests have Postgres and Redis. Failures in `test_persistence_contracts.py`, `test_queues.py`, `test_persist_batch.py`, `test_partitions.py` or the non-snapshot tests of `test_persist.py` are **A1's work in flight** — say so explicitly and report the result for your own files.

## Before you report DONE — mandatory second opinion (`.claude/rules/astra-second-opinion.md`)
```bash
bash infra/scripts/astra.sh ask T1.3-A2 "Review the current services/market-worker/hunter_market_worker/{sampling,recovery,funding,universe}.py. Focus: per-field staleness in the minute snapshot (no stale value republished as fresh), UTC-aligned sampling boundaries, the failed-gap reopen policy (no duplicate ingestion_gaps rows, no permanently suppressed minutes), REST fetch moved out of the open transaction while keeping candles+status atomic, and the set-based UPDATE of the universe ranking. Rules: Decimal, UTC, spread_pct stays a FRACTION, no fake data, no file over 350 lines. Answer in Portuguese: must-fix with a concrete failure scenario, nice-to-have, what you would do differently, what you agree with."
```
Include her answer in your report under **"Segunda opinião (Astra)"**: what she flagged, what you fixed, what you rejected and why. If `codex` is unavailable, write "Astra indisponível: <erro>" and continue — never block, never invent her answer.

## Report format (final message; do not write a report file)
One line per finding ID (H5, D9, D1, M5, D8, HIGH-2, M3, D5, D6+MEDIUM-5, M2, L3, MEDIUM-6, HIGH-4): FIXED / NOT FIXED + why, the `file:line` you changed, the name of the test that proves it. Then the verbatim command outputs. Then anything you found and did **not** change, with its failure scenario. Then "Segunda opinião (Astra)". **Do not commit.**
