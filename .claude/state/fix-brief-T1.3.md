# Fix brief — T1.3 `hunter_market_worker`, findings accepted after review

You are fixing an existing, working implementation (73 tests green). Every item below is an **accepted finding with a concrete failure scenario**, reconciled from three reviewers (`code-reviewer`, `exchange-integration-specialist`, `database-architect`) and an adversarial second opinion from the original implementer (Astra/GPT-6). Do not redesign; make the minimal correct change and prove each one with a test that fails before your change and passes after.

## Files you may touch (nothing else — other tasks are in flight in the same tree)
- `services/market-worker/hunter_market_worker/*.py`
- `services/market-worker/tests/*.py`
- `services/market-worker/README.md`
- `services/market-worker/docs/T1.3-report.md` (move the existing `services/market-worker/T1.3-report.md` here with `git mv`; do not edit its content)
- `packages/core/hunter_core/observability.py` (only to add counters listed below)

**Forbidden:** `packages/exchange-adapters/**` (T1.2 agent is editing it right now), `apps/api/**` (T1.4), `apps/web/**` (T1.5), `packages/core/hunter_core/domain/**`, `infra/migrations/**`, `.env`, any `git commit`/`git push`/`git checkout`/`git stash`.

## Hard rules (CLAUDE.md)
`Decimal` for every monetary/quantity value; UTC for everything persisted, `time.monotonic()` only for watchdogs and internal age; no file over 350 lines (`uv run python infra/scripts/check_file_size.py`); `structlog` via `get_logger`, never `print`; no local state on disk; no fake data — absence becomes `stale`/`degraded`/`unavailable`, never a stale value republished as fresh; every meaningful mutation observable.

---

## CRITICAL

### C1 — partial candles are rejected forever because the code reads the wrong attribute
`services/market-worker/hunter_market_worker/ingest.py:280-292` and `hot_state.py:122-138`.
`NormalizedCandle` now has a real `event_ts: datetime | None` field (committed in `3139fb4`), but `handle_event` calls `hot_state.push_candle(redis, event)` without forwarding it, and `push_candle`'s fallback is `getattr(candle, "ts", None)` — an attribute that does not exist on the model, so it is always `None`. Therefore `if event_ts is None and not candle.is_final: return False` fires for **every** partial candle, forever: `mkt:{ex}:{sym}:candles:1m` never receives a partial in production. The 73 green tests miss it because `test_contracts.py` calls `push_candle(..., event_ts=ts)` directly, bypassing `handle_event`.
**Fix:** in `ingest.py` pass `event_ts=event.event_ts`; in `hot_state.py:130` change the fallback to `getattr(candle, "event_ts", None)`. Keep the honest rejection + one-shot `market_candle_source_ts_missing` error when `event_ts` really is `None`.
**Test:** an integration test that pushes two growing partials of the same `open_time` with distinct `event_ts` **through `handle_event`** and asserts the Redis list holds the newer one; plus a late partial that is rejected.

---

## HIGH

### H1 — a transient DB blip kills the whole worker through the loss-reporting path
`services/market-worker/hunter_market_worker/persist.py:80`. `drain_loop` starts every iteration with an unguarded `await report_losses(factory, exchange_code, queues)`, while the sibling `flush_batch` three lines down is wrapped in `try/except Exception: runtime.mark_error()`. `report_losses` opens a real `role_session` whenever `queues.losses` is non-empty, which happens routinely (a `Snapshot` "replaced" drop occurs every time a new minute snapshot supersedes one not yet flushed).
**Scenario:** Postgres has a 2 s blip (pool recycle, cold start) while one loss is pending → `report_losses` raises → propagates out of `drain_loop` → `forever("persist", ...)` re-raises → `TaskGroup` cancels ingest, universe, recovery and heartbeat → process exits non-zero. Liquidations still buffered in memory are lost. The 30 s readiness grace and the `/ready` 503 exist precisely so this degrades instead of dying.
**Fix:** wrap the `report_losses` call in the same catch-log-`mark_error` pattern as `flush_batch`, leaving `queues.losses` untouched so it retries next iteration. Do the same for the `record_system_event("persistence_lag", ...)` call at `persist.py:110`.
**Test:** a `report_losses` that raises must leave the loop alive and the losses queue intact.

### H2 — freshness and watchdog progress are refreshed before we know the event was accepted
`services/market-worker/hunter_market_worker/streaming.py:64-70`. `watchdog.last_event = time.monotonic()` and `health.data_event()` both run right after pulling a message off the stream, **before** `handle_event()`/`AcceptedEvents.accept()` decides whether it is a duplicate or a late event.
**Scenario:** the exchange keeps re-sending the same last-known ticker. Every frame is rejected as a duplicate, yet `last_data`/`last_event` keep advancing: `/ready` stays 200 and the 30 s-silence/3-restart fatal path never fires. The worker looks healthy while genuinely frozen — exactly the "frozen price republished as new" failure the joint decision forbids.
**Fix:** move both updates to after `accepted = await handle_event(...)` and apply them only when `accepted` is true.
**Test:** feed N duplicate events; assert readiness turns false after 60 s and the watchdog warns after 30 s.

### H3 — readiness returns true for the first 15 s with zero data received
`services/market-worker/hunter_market_worker/supervision.py:60-72`. Once `observe_adapter` reports `connecting`, `ingestion()` falls through to `return self.unhealthy_since is not None and now - self.unhealthy_since < 120` → **true**, even though `last_data is None`.
**Scenario:** the container starts, `/ready` answers 200 within a second, the Compose healthcheck marks the service healthy, and the API's system page shows the worker up before a single market event has arrived. The joint decision requires "bootstrap without data exposes `initializing` and readiness false".
**Fix:** in `ingestion()`, if `self.last_data is None` and `self.state != "idle"`, return `False`. The 120 s monotonic tolerance keeps applying after the first accepted event (do not break `test_readiness_grace_is_monotonic_and_not_reset_by_flapping`).
**Test:** readiness is false at t=1 s while `connecting` with no data, and true only after the first accepted data event.

### H4 — `HSET` leaves stale optional fields alive under a fresh timestamp
`services/market-worker/hunter_market_worker/hot_state.py:29-30` and `:50`. `_mapping` drops `None` values and `_hash` writes with `HSET`, which never removes fields.
**Scenario:** one ticker carries `volume_24h`; the next ticker for the same symbol does not (the exchange omitted it). The old `volume_24h` stays in the hash and now sits next to the **new** `ts`. The API (T1.4) and the UI (T1.5) read a stale value as current — fake data by omission.
**Fix:** for each writer, declare the set of fields it owns; on an accepted write, `HDEL` the owned fields whose value is `None` inside the same `MULTI` as the `HSET`. Owned sets: ticker writer → the ticker fields; funding writer → `funding_rate`, `funding_kind`, `next_funding_time`, `funding_ts`; mark writer → `mark_price`, `index_price`, `mark_ts`; OI writer → `open_interest`, `open_interest_value`, `oi_ts`. A writer must never delete a field it does not own.
**Test:** write a ticker with `volume_24h`, then one without; assert the field is gone, not stale.

### H5 — the minute snapshot copies `mark_price` without checking `mark_ts`
`services/market-worker/hunter_market_worker/sampling.py:~94`. The snapshot stamps `snapshot_ts = align_open_time(utcnow(), M1)` and copies `mark_price` (and the other `deriv` fields) straight from the hash without consulting the per-field `*_ts`.
**Scenario:** the mark-price stream dies while OI keeps polling and keeps the shared 600 s TTL alive. The same stale `mark_price` is written into `market_snapshots` minute after minute as if it were a fresh observation; nothing in the row distinguishes "unchanged" from "not updated". Downstream (scanner, indicators) treats it as a live series.
**Fix:** read `mark_ts`, `oi_ts` and `funding_ts` from the hash and, for each field, write `None` into the snapshot when its own timestamp is older than `settings.market_stale_after_s`. Increment a counter (`market_snapshot_stale_fields_total`, labels `field`) when you drop one, so the omission is observable.
**Test:** a hash with a fresh `oi_ts` and a `mark_ts` older than the threshold produces a snapshot row with `mark_price=None` and a bumped counter.

### H6 — the production persistence path inserts one row per round trip
`services/market-worker/hunter_market_worker/persist_rows.py:150-171`. `flush_batch` loops `for snapshot in snapshots: await session.execute(pg_insert(...).values(...))` and repeats the pattern for open interest. This *is* the production path: `sampling.py` enqueues into `queues` when queues are present, so the batched `.values(list)` code in `sampling.py` is only used when queues are absent.
**Scenario:** a batch carrying 200 snapshots with 60 ms per statement needs ≥12 s, but the whole flush is wrapped in `asyncio.wait_for(..., timeout=10)` at `persist.py:115`. The transaction is cancelled before commit, the batch is retried, does the same work, and is eventually dropped by age — snapshots are lost every minute at the target universe size of 200 markets.
**Fix:** build one `pg_insert(MarketSnapshot).values(list_of_dicts).on_conflict_do_nothing(index_elements=["market_id", "ts"])` and one equivalent for `OpenInterestHistory`, deduplicating rows by the conflict key **in Python first** (a multi-row `INSERT` cannot resolve two rows with the same conflict key in one statement — it raises `CardinalityViolation`). Keep the 5-minute UTC bucket computation.
**Test:** a batch of 200 snapshots issues exactly one `INSERT` (count the executed statements) and is idempotent when flushed twice; a batch containing two rows with the same `(market_id, ts)` does not raise.

### H7 — `push_trade` reads the entire 2000-item list on every single trade
`services/market-worker/hunter_market_worker/hot_state.py:100-119`. `rows = await redis.lrange(key, 0, -1)` then msgpack-decodes all of them, on every trade, only to dedupe by `trade_id` and compare against the head's `ts`.
**Scenario:** with the real adapter subscribed to `aggTrade` for 200 symbols at a modest 10 trades/s each (2 000 trades/s), each trade pulls ~300 KB from Redis and decodes 2 000 msgpack objects — hundreds of MB/s of Redis traffic and millions of decodes per second. The ingest coroutine saturates the event loop, the 250 ms coalescer never flushes on time, the watchdog sees no accepted data for 30 s and restarts connections, escalating to a fatal exit after three restarts. The worker cannot survive real trade volume.
**Fix:** read only a bounded window — `await redis.lrange(key, 0, 49)` — for both the duplicate check and the head-`ts` ordering check. A WS reconnect only ever replays a handful of recent trades, so a 50-item window covers the overlap; document the bound in the README.
**Test:** assert the call reads a bounded range (assert on the fake Redis call arguments), and that a duplicate inside the window is still rejected.

### H8 — `push_candle` rewrites the whole 1500-item list on every candle
`services/market-worker/hunter_market_worker/hot_state.py:133-157`. Every accepted candle does `LRANGE 0 -1` (up to 1500 msgpack blobs), decodes them all, sorts, then `DELETE` + `RPUSH` of 1500 elements.
**Scenario:** once C1 is fixed, partials arrive roughly every second per symbol. At 200 markets that is ~200 full read-decode-sort-rewrite cycles per second over a 1500-element list — the same event-loop saturation as H7, plus the Redis list is briefly emptied by `DELETE` on every write.
**Fix:** fast paths, keeping the current full rewrite only as a rare fallback:
1. `LRANGE key 0 15` (16 newest entries).
2. If an entry with the same `open_time` is found at index `i`, apply the existing precedence rules and `LSET key i <value>`.
3. Else, if the list is empty or the new `open_time` is greater than the head's, `LPUSH` + `LTRIM key 0 1499`.
4. Else (older than the 16-entry window) fall back to the current full read-modify-rewrite.
**Test:** a normal new-minute final does not issue `DELETE`; the existing contract tests for the ordering rules must still pass unchanged.

### H9 — a final candle with the same `event_ts` as the last partial is rejected
`services/market-worker/hunter_market_worker/hot_state.py:144`. The `not _newer(event_ts, previous["ts"])` guard runs before the finality check, so a final that carries the same event timestamp as the last partial of that `open_time` is discarded.
**Scenario:** Binance emits the closing kline frame with the same `E` as the last partial update of that minute. The Redis list keeps the **partial** as the newest state of a closed minute, and the API serves an unclosed candle as the last known one. The contract says "final replaces partial" unconditionally.
**Fix:** check finality first — if the incoming candle `is_final` and the stored entry is not, always replace, regardless of `event_ts`. Keep "partial never replaces final" and "older partial rejected".
**Test:** partial at `ts=T`, then final at `ts=T` → the entry is final.

### H10 — the tick payload republishes a frozen price under a fresh timestamp
`services/market-worker/hunter_market_worker/ingest.py:98-103` and `:115-130`. `_TickAccum` keeps a single `ts` advanced by any of ticker/trade/book, and `reset()` preserves `price`/`bid`/`ask` across flushes. A book update alone marks the accumulator dirty and advances `ts`.
**Scenario:** trades and ticker stop for a symbol while the order book keeps updating. Every 250 ms the worker publishes `market.ticks` with the old `price` and a brand-new `ts`; the UI shows a live-looking price that has not moved in minutes with no way to tell.
**Fix (additive, so T1.4/T1.5 consumers do not break):** track `price_ts` and `book_ts` on `_TickAccum`, each advanced only by the event kind that owns it, and add `price_ts` and `book_ts` to the payload built by `build_tick_payload`. Keep `ts` as the timestamp of the last accepted event of any kind. Document the three fields in the README.
**Test:** ticker at T0, then only book events at T1 → payload has `ts=T1`, `price_ts=T0`.

---

## MEDIUM

### M1 — liquidation duplicates are invisible
`services/market-worker/hunter_market_worker/persist_rows.py:109-132`. The `ON CONFLICT (id, ts) DO NOTHING` statement has no `.returning(...)`, so nothing counts how many rows collapsed.
**Scenario:** an overlapping WS reconnect redelivers thousands of liquidations. The history stays correct, but the duplicate storm is invisible — an operator watching persisted-liquidation volume drop cannot distinguish "we deduped correctly" from "we are losing data", and every item of the batch is still published to the stream at `persist.py:131`.
**Fix:** add `.returning(Liquidation.id)`, compute `len(values) - len(result.all())`, and increment a new `market_liquidation_duplicates_total` counter in `packages/core/hunter_core/observability.py`. Only publish the liquidations that were actually inserted.
**Test:** insert the same batch twice; the counter equals the batch size on the second pass and no second publication happens.

### M2 — a newly listed perpetual gets an impossible, permanently `failed` gap
`services/market-worker/hunter_market_worker/recovery.py:149`. Bootstrap computes `start = end - MINUTE * 1499` with no notion of when the market started existing, and registers every missing open time.
**Scenario:** a perpetual listed two hours ago returns all the candles it has. The 22 hours before listing are still demanded; after five attempts the gap becomes `failed` and the market is permanently reported as `degraded` for history that never existed.
**Fix:** in `recover_registered`, after filtering `closed`, if the list is non-empty and `min(open_time) > gap.gap_start`, set `gap.gap_start = min(open_time)` before the coverage check — the exchange's history simply does not go back further. Log it once per gap (`market_gap_history_starts_later`).
**Test:** a fake adapter that only returns the last 120 minutes of a 1500-minute gap recovers the gap instead of failing it.

### M3 — one slow cycle destroys the one-minute gap-detection cadence
`services/market-worker/hunter_market_worker/recovery.py:152-171` and `:179-188`. Markets and gaps are processed strictly sequentially, each REST call awaited inside its own transaction, and the loop only re-checks the clock after everything finishes.
**Scenario:** 200 markets need backfill and each REST call takes one second — the calls alone exceed three minutes, so new holes stop being detected at the contracted cadence, and a single stuck call blocks every market behind it.
**Fix:** bound the work per cycle: process at most `MAX_GAPS_PER_CYCLE = 50` registered gaps per pass (remaining gaps are picked up by the next cycle, which is why they are durable rows), and wrap each `adapter.fetch_candles` in `asyncio.wait_for(..., timeout=20)` so one stuck call cannot block the rest. Detection (`register_missing`) must keep running every cycle for every market.
**Test:** with 120 open gaps, one cycle processes 50 and returns; a `fetch_candles` that hangs raises `TimeoutError` inside the existing per-gap handler and increments `attempts` without killing the loop.

### M4 — `spread_pct` is stored in the wrong unit
`services/market-worker/hunter_market_worker/sampling.py:57`. `_spread_pct` returns `(ask - bid) / mid`, while the domain helper in `packages/core/hunter_core/domain/market.py:176` returns the same ratio multiplied by 100.
**Scenario:** bid 99 / ask 101 stores `0.02` in `market_snapshots` while every other consumer of the domain helper sees `2`. Anything comparing the historical series against a live computation (the scanner's spread filter in M2) underestimates the spread by 100×.
**Fix:** multiply by 100 in `_spread_pct`, or better, call the domain helper directly. Do not edit `packages/core/hunter_core/domain/market.py`.
**Test:** bid 99 / ask 101 → `Decimal("2")`.

### M5 — the sampling loops drift and skip buckets
`services/market-worker/hunter_market_worker/sampling.py:~68` and `:146`. Both loops `await asyncio.sleep(interval)` and only then do the work, so the period is `interval + work_time`.
**Scenario:** an OI round takes two minutes; each market is then polled roughly every seven minutes. Two of the 5-minute UTC buckets have no reading at all, and aligning the sample to a bucket does not bring back the ones that were skipped.
**Fix:** sleep until the next aligned boundary instead of a fixed duration — compute the delay from `utcnow()` to the next multiple of the interval and sleep that. Log `market_sampling_bucket_skipped` (with a counter) when a boundary is missed.
**Test:** a fake clock where the work takes longer than the interval still aligns the next run to the following boundary, and the skip is counted.

---

## LOW (do them, they are one-liners)

- **L1** `services/market-worker/hunter_market_worker/ingest.py:250-254`: `_enqueue`'s `except asyncio.QueueFull` is dead code — `BoundedEvents.put_nowait` never raises, it drops with a metric. Remove the dead handler (or replace `_enqueue` with a direct call).
- **L2** `services/market-worker/tests/test_contracts.py:73-89`: capture `head["ts"]` before the late-final write and assert it is unchanged afterwards, so the "late final does not refresh head freshness" guarantee is asserted directly rather than implied by the loop structure.
- **L3** `services/market-worker/hunter_market_worker/recovery.py:174-192`: add a unit test for `run_recovery`'s cadence gate (`now - last_check < CHECK_INTERVAL_S and reconnects == last_reconnects`) — today an inverted operator would silently change the gap-detection frequency with no test failing.
- **L4** `services/market-worker/README.md`: state explicitly that liquidation identity is `uuid5` over `(exchange, symbol, side, normalized price, normalized qty, ts_ms)`, so **two genuinely distinct real-world liquidations sharing that exact tuple collapse into one row** — a documented, accepted M1 consequence of the deterministic id. Also document the H7 50-trade dedupe window and the H10 `price_ts`/`book_ts` fields.
- **L5** `git mv services/market-worker/T1.3-report.md services/market-worker/docs/T1.3-report.md` (both reviewers flagged a process report at the package root as clutter). Do not edit its content.

---

## Explicitly NOT in scope (do not "fix" these)
- Anything in `packages/exchange-adapters/**`: the missing `update_subscriptions`, the missing `fetch_realized_funding`, `parse_kline_ws` not filling `event_ts`, the missing `restart_connection`, the unbounded internal `asyncio.Queue`, and the reader tasks created with `ensure_future` outside the worker's `TaskGroup`. All are recorded in `.claude/state/review-T1.2.md` under "Pendências vindas da T1.3" and belong to the T1.2 agent.
- The loss of a `market.liquidations` publication when the process dies between the Postgres commit and the `XADD`: an explicitly accepted M1 limitation (transactional outbox is an M2 follow-up).
- The watchdog's `restart_stream` fallback tearing down both connections: accepted M1 behaviour pending T1.2's `restart_connection`.

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
Docker Desktop must be running (the integration tests need Postgres and Redis).

## Report format (final message, no report file)
One line per finding ID (C1, H1..H10, M1..M5, L1..L5): FIXED / NOT FIXED + why, the file:line you changed, and the name of the test that proves it. Then the verbatim command outputs. Then anything you found while fixing that you did **not** change, with its failure scenario. **Do not commit.**


## ATENÇÃO (orquestrador, 2026-09-05): a revisão do `database-architect` JÁ FOI FEITA — findings em `.claude/state/db-review-T1.3.md` (1 CRITICAL, 3 HIGH, 4 MEDIUM, 2 LOW). Não re-despachar; incorporar ao brief de correção.

## ATENÇÃO 2 (orquestrador): segunda passada do database-architect em `.claude/state/db-review-T1.3-part2.md` (D1–D12). **Não aplicar o M4 deste brief** (convenção de porcentagem: ver D1/DECISÃO). D2, D3, D5, D6, D7, D8, D9, D10 entram na parte A (persistência/recovery/queues). D4 e D12 são fora da T1.3 (anotar no plano/T1.6). D11 é nota em DATABASE.md + assert.

## ATENÇÃO 3 (orquestrador, após T1.4/T1.5 commitadas): (a) `apps/api/tests/integration/test_webhook.py::test_a_crash_where_even_the_release_never_runs_still_recovers_after_the_stale_window` passou a falhar depois do `command_timeout: 30` em `packages/core/hunter_core/db/session.py` (suíte da API 445/1). Investigar e corrigir dentro da T1.3 (provável: o teste segura uma conexão além do timeout, ou o timeout precisa ser configurável e maior para `hunter_app`); rodar `uv run pytest apps/api/tests/integration/test_webhook.py -q` como parte da verificação final. (b) Bug do hot state: no hash `mkt:*:ticker`, `last`/`ts` são renovados pelo `bookTicker`, então se o canal de trades parar e o book continuar, a API entrega preço velho com carimbo novo. Fix na T1.3: `ts` do ticker só avança com trade (`aggTrade`); bid/ask/`book_ts` avançam com `bookTicker`; a API já lê `price_ts`/`book_ts` no evento realtime — espelhar os dois no hash (`price_ts`, `book_ts`) e o `data_quality` do ticker usa `price_ts`. Teste: book ativo + trades parados por 15 s → componente ticker `stale`.
