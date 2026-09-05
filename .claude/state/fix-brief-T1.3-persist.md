# Fix brief — T1.3 part A: persistence, sampling, recovery

You are fixing an existing, working implementation (73 tests green). Every item below is an **accepted finding with a concrete failure scenario**, reconciled from four reviewers (`code-reviewer`, `exchange-integration-specialist`, `database-architect`) and an adversarial second opinion from the original implementer (Astra/GPT-6). Do not redesign; make the minimal correct change and prove each one with a test that **fails before your change and passes after** (run it before, paste the failure, then fix).

A second agent is working **in parallel** on the ingest half (`ingest.py`, `hot_state.py`, `streaming.py`, `supervision.py`, `README.md` and their tests). You must not touch those files — you would collide.

## Files you may touch (nothing else)
- `services/market-worker/hunter_market_worker/persist.py`
- `services/market-worker/hunter_market_worker/persist_rows.py`
- `services/market-worker/hunter_market_worker/recovery.py`
- `services/market-worker/hunter_market_worker/sampling.py`
- `services/market-worker/hunter_market_worker/queues.py`
- `packages/core/hunter_core/observability.py` (**only** to add the new counters listed below — do not change existing metric names, labels or helpers, the API and the web app read them)
- `services/market-worker/tests/test_persist.py`
- `services/market-worker/tests/test_persistence_contracts.py`
- `services/market-worker/tests/test_recovery.py`
- `services/market-worker/tests/test_recovery_contracts.py`
- `services/market-worker/tests/db_helpers.py`, `services/market-worker/tests/builders.py` (additive only; other test modules import them)
- New test files under `services/market-worker/tests/` if you need one

**Forbidden (another agent or another task owns them right now):** `services/market-worker/hunter_market_worker/{ingest,hot_state,streaming,supervision,universe,heartbeat,funding,publication,main,config,wire}.py`, `services/market-worker/README.md`, `services/market-worker/tests/{conftest,fakes,test_contracts,test_hot_state,test_ingest_coalesce,test_ingest_integration,test_supervision,test_universe,test_heartbeat,test_funding,test_config,test_role_registration}.py`, everything in `packages/core` **except** `observability.py`, `packages/core/hunter_core/domain/**`, `packages/exchange-adapters/**`, `apps/**`, `infra/migrations/**`, `.env`, and any `git commit` / `git push` / `git checkout` / `git stash` / `git mv` / `git add`.

If a fix needs a schema change, **do not write a migration** — report it as NOT FIXED with the exact DDL you would need; migrations are reviewed separately.

## Hard rules (CLAUDE.md)
`Decimal` for every monetary/quantity value; **UTC** for everything persisted, `time.monotonic()` only for watchdogs and internal age; **no file over 350 lines** (`uv run python infra/scripts/check_file_size.py`); `structlog` via `get_logger`, never `print`; no local state on disk; **no fake data** — absence becomes `stale`/`degraded`/`unavailable`, never a stale value republished as fresh; every meaningful mutation observable.

---

## HIGH

### H1 — a transient DB blip kills the whole worker through the loss-reporting path
`persist.py:80`. `drain_loop` starts every iteration with an unguarded `await report_losses(factory, exchange_code, queues)`, while the sibling `flush_batch` three lines down is wrapped in `try/except Exception: runtime.mark_error()`. `report_losses` opens a real `role_session` whenever `queues.losses` is non-empty, which happens routinely (a `Snapshot` "replaced" drop occurs every time a new minute snapshot supersedes one not yet flushed).
**Scenario:** Postgres has a 2 s blip (pool recycle, cold start) while one loss is pending → `report_losses` raises → propagates out of `drain_loop` → `forever("persist", ...)` re-raises → `TaskGroup` cancels ingest, universe, recovery and heartbeat → process exits non-zero. Liquidations still buffered in memory are lost. The 30 s readiness grace and the `/ready` 503 exist precisely so this degrades instead of dying.
**Fix:** wrap the `report_losses` call in the same catch-log-`mark_error` pattern as `flush_batch`, leaving `queues.losses` untouched so it retries next iteration. Do the same for the `record_system_event("persistence_lag", ...)` call at `persist.py:110`.
**Test:** a `report_losses` that raises must leave the loop alive and the losses queue intact.

### H5 — the minute snapshot copies `mark_price` without checking `mark_ts`
`sampling.py:~105-120`. The snapshot stamps `snapshot_ts = align_open_time(utcnow(), M1)` and copies `mark_price` (and the other `deriv` fields) straight from the hash without consulting the per-field `*_ts`.
**Scenario:** the mark-price stream dies while OI keeps polling and keeps the shared 600 s TTL alive. The same stale `mark_price` is written into `market_snapshots` minute after minute as if it were a fresh observation; nothing in the row distinguishes "unchanged" from "not updated". Downstream (scanner, indicators) treats it as a live series.
**Fix:** read `mark_ts`, `oi_ts` and `funding_ts` from the hash and, for each field, write `None` into the snapshot when its own timestamp is older than `settings.market_stale_after_s` relative to `snapshot_ts`. Ownership: `mark_ts` → `mark_price`, `index_price`; `oi_ts` → `open_interest`, `open_interest_value`; `funding_ts` → `funding_rate`. A missing `*_ts` means the field was never written → `None`. Increment a counter (`market_snapshot_stale_fields_total`, label `field`) when you drop one, so the omission is observable. `write_snapshots` must therefore receive `settings` (it currently does not) — thread it from `snapshot_loop`, which already has it.
**Test:** a hash with a fresh `oi_ts` and a `mark_ts` older than the threshold produces a snapshot row with `mark_price=None`, `open_interest` intact, and a bumped counter.

### H6 — the production persistence path inserts one row per round trip
`persist_rows.py:150-171`. `flush_batch` loops `for snapshot in snapshots: await session.execute(pg_insert(...).values(...))` and repeats the pattern for open interest. This *is* the production path: `sampling.py` enqueues into `queues` when queues are present, so the batched `.values(list)` code in `sampling.py` is only used when queues are absent.
**Scenario:** a batch carrying 200 snapshots with 60 ms per statement needs ≥12 s, but the whole flush is wrapped in `asyncio.wait_for(..., timeout=10)` at `persist.py:115`. The transaction is cancelled before commit, the batch is retried, does the same work, and is eventually dropped by age — snapshots are lost every minute at the target universe size of 200 markets.
**Fix:** build one `pg_insert(MarketSnapshot).values(list_of_dicts).on_conflict_do_nothing(index_elements=["market_id", "ts"])` and one equivalent for `OpenInterestHistory`, deduplicating rows by the conflict key **in Python first** (a multi-row `INSERT` cannot resolve two rows with the same conflict key in one statement — PostgreSQL raises `CardinalityViolation`; keep the **last** row for the key, it is the most recent reading). Keep the 5-minute UTC bucket computation. The same Python-side dedupe is needed for `upsert_candles`, `upsert_funding` and `upsert_liquidations` — a WS reconnect can put two identical candles or liquidations in one batch and today that raises `CardinalityViolation` and kills the whole flush.
**Test:** a batch of 200 snapshots issues exactly one `INSERT` (count the executed statements) and is idempotent when flushed twice; a batch containing two rows with the same `(market_id, ts)` does not raise; likewise two identical liquidations in one batch.

---

## MEDIUM

### M1 — liquidation duplicates are invisible
`persist_rows.py:109-132`. The `ON CONFLICT (id, ts) DO NOTHING` statement has no `.returning(...)`, so nothing counts how many rows collapsed.
**Scenario:** an overlapping WS reconnect redelivers thousands of liquidations. The history stays correct, but the duplicate storm is invisible — an operator watching persisted-liquidation volume drop cannot distinguish "we deduped correctly" from "we are losing data", and every item of the batch is still published to the stream at `persist.py:131`.
**Fix:** add `.returning(Liquidation.id)`, compute `len(values) - len(inserted_ids)`, increment a new `market_liquidation_duplicates_total` counter in `packages/core/hunter_core/observability.py`, and have `upsert_liquidations` return the set of ids actually inserted so `drain_loop` publishes only those. `drain_loop` currently re-derives the item list; pass the inserted-id set out of `flush_batch` (change its return type) and filter with `liquidation_id(item)`.
**Test:** insert the same batch twice; the counter equals the batch size on the second pass and no second publication happens.

### M2 — a newly listed perpetual gets an impossible, permanently `failed` gap
`recovery.py:149` / `recover_registered`. Bootstrap computes `start = end - MINUTE * 1499` with no notion of when the market started existing, and registers every missing open time.
**Scenario:** a perpetual listed two hours ago returns all the candles it has. The 22 hours before listing are still demanded; after five attempts the gap becomes `failed` and the market is permanently reported as `degraded` for history that never existed.
**Fix:** in `recover_registered`, after filtering `closed`, if the list is non-empty and `min(open_time) > gap.gap_start`, set `gap.gap_start = min(open_time)` before the coverage check — the exchange's history simply does not go back further. Log it once per gap (`market_gap_history_starts_later`). Only do this when the adapter actually returned candles (an empty response means "REST failed / nothing yet", not "history starts later") and only when the fetch covered the whole range.
**Test:** a fake adapter that only returns the last 120 minutes of a 1500-minute gap recovers the gap instead of failing it; an adapter returning `[]` still increments `attempts` and eventually fails the gap.

### M3 — one slow cycle destroys the one-minute gap-detection cadence
`recovery.py:152-171` and `:179-188`. Markets and gaps are processed strictly sequentially, each REST call awaited **inside its own open transaction** (`recover_registered` calls `adapter.fetch_candles` at line 114 while the `role_session` transaction and the `SELECT ... FOR UPDATE` row lock are held), and the loop only re-checks the clock after everything finishes.
**Scenario:** 200 markets need backfill and each REST call takes one second — the calls alone exceed three minutes, so new holes stop being detected at the contracted one-minute cadence, and a single stuck call blocks every market behind it while holding a Postgres transaction and a row lock open for the whole duration.
**Fix:** (a) bound the work per cycle: process at most `MAX_GAPS_PER_CYCLE = 50` registered gaps per pass (remaining gaps are picked up by the next cycle, which is why they are durable rows); (b) wrap each `adapter.fetch_candles` in `asyncio.wait_for(..., timeout=20)` so one stuck call cannot block the rest — the existing `except Exception` in `recover_registered` already turns that into an incremented `attempts`; (c) move the `fetch_candles` call **out of** the open transaction: fetch first, then open the `role_session`, re-read the gap `FOR UPDATE`, and write candles + status in one transaction. Detection (`register_missing`) must keep running every cycle for every market.
**Test:** with 120 open gaps, one cycle processes 50 and returns; a `fetch_candles` that hangs raises `TimeoutError` inside the existing per-gap handler, increments `attempts` and does not kill the loop; the transaction is not open while `fetch_candles` runs (assert with a fake adapter that checks `session.in_transaction()` is false, or that no connection is checked out).

### M4 — `spread_pct` is stored in the wrong unit
`sampling.py:57`. `_spread_pct` returns `(ask - bid) / mid`, while the domain helper in `packages/core/hunter_core/domain/market.py:176` returns the same ratio multiplied by 100.
**Scenario:** bid 99 / ask 101 stores `0.02` in `market_snapshots` while every other consumer of the domain helper sees `2`. Anything comparing the historical series against a live computation (the scanner's spread filter in M2) underestimates the spread by 100×.
**Fix:** call the domain helper directly (preferred), or multiply by 100. Do **not** edit `packages/core/hunter_core/domain/market.py`.
**Test:** bid 99 / ask 101 → `Decimal("2")`.

### M5 — the sampling loops drift and skip buckets
`sampling.py:69-70` and `:146-147`. Both loops `await asyncio.sleep(interval)` and only then do the work, so the real period is `interval + work_time`.
**Scenario:** an OI round takes two minutes; each market is then polled roughly every seven minutes. Two of the 5-minute UTC buckets have no reading at all, and aligning the sample to a bucket does not bring back the ones that were skipped.
**Fix:** sleep until the next aligned UTC boundary instead of a fixed duration — compute the delay from `utcnow()` to the next multiple of the interval and sleep that. Add a `market_sampling_bucket_skipped_total` counter (label `loop`) and increment it, with a `logger.warning`, when the boundary that just passed was missed because the previous round overran.
**Test:** a fake clock where the work takes longer than the interval still aligns the next run to the following boundary, and the skip is counted.

---

## LOW

- **L3** `recovery.py:174-192`: add a unit test for `run_recovery`'s cadence gate (`now - last_check < CHECK_INTERVAL_S and reconnects == last_reconnects`) — today an inverted operator would silently change the gap-detection frequency with no test failing.

---

## Explicitly NOT in scope (do not "fix" these)
- Anything in `packages/exchange-adapters/**` (T1.2 agent): missing `update_subscriptions`, missing `fetch_realized_funding`, `parse_kline_ws` not filling `event_ts`, missing `restart_connection`, the unbounded internal `asyncio.Queue`, reader tasks created with `ensure_future` outside the `TaskGroup`.
- The loss of a `market.liquidations` publication when the process dies between the Postgres commit and the `XADD`: an explicitly accepted M1 limitation (transactional outbox is an M2 follow-up).
- The ingest half (C1, H2, H3, H4, H7, H8, H9, H10, L1, L2, L4): another agent is doing it right now in the files listed as forbidden above.
- Any Alembic migration.

## Verification you must run and paste verbatim in your report
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter
uv run pytest services/market-worker -q -p no:cacheprovider
uv run pytest packages/core/tests/unit -q -p no:cacheprovider
uv run ruff check services/market-worker packages/core && uv run ruff format --check services/market-worker packages/core
uv run pyright services/market-worker packages/core/hunter_core/runtime.py
uv run python infra/scripts/check_file_size.py
```
Docker Desktop must be running (the integration tests need Postgres and Redis). If the full suite shows failures in `test_contracts.py` / `test_hot_state.py` / `test_ingest_*.py` / `test_supervision.py`, that is the other agent's work in flight — say so explicitly and report the result for your own files.

## Report format (final message, no report file)
One line per finding ID (H1, H5, H6, M1, M2, M3, M4, M5, L3 and every D-numbered item below): FIXED / NOT FIXED + why, the `file:line` you changed, and the name of the test that proves it. Then the verbatim command outputs. Then anything you found while fixing that you did **not** change, with its failure scenario. **Do not commit.**
