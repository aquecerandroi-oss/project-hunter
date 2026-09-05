# Fix brief — T1.3 part B: ingest, hot state, streaming, supervision

You are fixing an existing, working implementation (73 tests green). Every item below is an **accepted finding with a concrete failure scenario**, reconciled from four reviewers (`code-reviewer`, `exchange-integration-specialist`, `database-architect`) and an adversarial second opinion from the original implementer (Astra/GPT-6). Do not redesign; make the minimal correct change and prove each one with a test that **fails before your change and passes after** (run it before, paste the failure, then fix).

A second agent is working **in parallel** on the persistence half (`persist.py`, `persist_rows.py`, `recovery.py`, `queues.py`, `sampling.py`, `observability.py` and their tests). You must not touch those files — you would collide.

## Files you may touch (nothing else)
- `services/market-worker/hunter_market_worker/ingest.py`
- `services/market-worker/hunter_market_worker/hot_state.py`
- `services/market-worker/hunter_market_worker/streaming.py`
- `services/market-worker/hunter_market_worker/supervision.py`
- `services/market-worker/README.md`
- `services/market-worker/tests/test_contracts.py`
- `services/market-worker/tests/test_hot_state.py`
- `services/market-worker/tests/test_ingest_coalesce.py`
- `services/market-worker/tests/test_ingest_integration.py`
- `services/market-worker/tests/test_supervision.py`
- `services/market-worker/tests/fakes.py` (only additive: new methods/attributes on `FakeAdapter`; do not change existing signatures — other test modules depend on them)
- New test files under `services/market-worker/tests/` if you need one

**Forbidden (another agent or another task owns them right now):** `services/market-worker/hunter_market_worker/{persist,persist_rows,recovery,queues,sampling,universe,heartbeat,funding,publication,main,config,wire}.py`, `services/market-worker/tests/{conftest,builders,db_helpers,test_persist,test_persistence_contracts,test_recovery,test_recovery_contracts,test_universe,test_heartbeat,test_funding,test_config,test_role_registration}.py`, `packages/core/**`, `packages/exchange-adapters/**`, `apps/**`, `infra/migrations/**`, `.env`, and any `git commit` / `git push` / `git checkout` / `git stash` / `git mv`.

## Hard rules (CLAUDE.md)
`Decimal` for every monetary/quantity value; UTC for everything persisted, `time.monotonic()` only for watchdogs and internal age; **no file over 350 lines** (`uv run python infra/scripts/check_file_size.py`) — `ingest.py` is already at 313 lines, so if your changes push it over, extract a small helper module (e.g. `hunter_market_worker/ticks.py`) rather than deleting behaviour, and note it in your report; `structlog` via `get_logger`, never `print`; no local state on disk; **no fake data** — absence becomes `stale`/`degraded`/`unavailable`, never a stale value republished as fresh; every meaningful mutation observable.

---

## CRITICAL

### C1 — partial candles are rejected forever because the code reads the wrong attribute
`ingest.py:280-292` and `hot_state.py:122-138`.
`NormalizedCandle` now has a real `event_ts: datetime | None` field (committed in `3139fb4`), but `handle_event` calls `hot_state.push_candle(redis, event)` without forwarding it, and `push_candle`'s fallback is `getattr(candle, "ts", None)` — an attribute that does not exist on the model, so it is always `None`. Therefore `if event_ts is None and not candle.is_final: return False` fires for **every** partial candle, forever: `mkt:{ex}:{sym}:candles:1m` never receives a partial in production. The 73 green tests miss it because `test_contracts.py` calls `push_candle(..., event_ts=ts)` directly, bypassing `handle_event`.
**Fix:** in `ingest.py` pass `event_ts=event.event_ts`; in `hot_state.py:130` change the fallback to `getattr(candle, "event_ts", None)`. Also fix the sibling `getattr(event, "ts", None)` check at `ingest.py:284` that gates the one-shot `market_candle_source_ts_missing` error — it must read `event.event_ts` too. Keep the honest rejection + one-shot error when `event_ts` really is `None`.
**Test:** an integration test that pushes two growing partials of the same `open_time` with distinct `event_ts` **through `handle_event`** and asserts the Redis list holds the newer one; plus a late partial that is rejected.

---

## HIGH

### H2 — freshness and watchdog progress are refreshed before we know the event was accepted
`streaming.py:64-70`. `watchdog.last_event = time.monotonic()` and `health.data_event()` both run right after pulling a message off the stream, **before** `handle_event()`/`AcceptedEvents.accept()` decides whether it is a duplicate or a late event.
**Scenario:** the exchange keeps re-sending the same last-known ticker. Every frame is rejected as a duplicate, yet `last_data`/`last_event` keep advancing: `/ready` stays 200 and the 30 s-silence/3-restart fatal path never fires. The worker looks healthy while genuinely frozen — exactly the "frozen price republished as new" failure the joint decision forbids.
**Fix:** move both updates to after `accepted = await handle_event(...)` and apply them only when `accepted` is true.
**Test:** feed N duplicate events; assert readiness turns false after 60 s and the watchdog warns after 30 s.

### H3 — readiness returns true for the first 15 s with zero data received
`supervision.py:60-72`. Once `observe_adapter` reports `connecting`, `ingestion()` falls through to `return self.unhealthy_since is not None and now - self.unhealthy_since < 120` → **true**, even though `last_data is None`.
**Scenario:** the container starts, `/ready` answers 200 within a second, the Compose healthcheck marks the service healthy, and the API's system page shows the worker up before a single market event has arrived. The joint decision requires "bootstrap without data exposes `initializing` and readiness false".
**Fix:** in `ingestion()`, if `self.last_data is None` and `self.state != "idle"`, return `False`. The 120 s monotonic tolerance keeps applying after the first accepted data event (do not break `test_readiness_grace_is_monotonic_and_not_reset_by_flapping`).
**Test:** readiness is false at t=1 s while `connecting` with no data, and true only after the first accepted data event.

### H4 — `HSET` leaves stale optional fields alive under a fresh timestamp
`hot_state.py:29-30` and `:50`. `_mapping` drops `None` values and `_hash` writes with `HSET`, which never removes fields.
**Scenario:** one ticker carries `volume_24h`; the next ticker for the same symbol does not (the exchange omitted it). The old `volume_24h` stays in the hash and now sits next to the **new** `ts`. The API (T1.4) and the UI (T1.5) read a stale value as current — fake data by omission.
**Fix:** for each writer, declare the set of fields it owns; on an accepted write, `HDEL` the owned fields whose value is `None` inside the same `MULTI` as the `HSET`. Owned sets: ticker writer → the ticker fields; funding writer → `funding_rate`, `funding_kind`, `next_funding_time`, `funding_ts`; mark writer → `mark_price`, `index_price`, `mark_ts`; OI writer → `open_interest`, `open_interest_value`, `oi_ts`. A writer must never delete a field it does not own (the ticker and deriv hashes are shared by several writers — deleting someone else's field is a worse bug than the one you are fixing).
**Test:** write a ticker with `volume_24h`, then one without; assert the field is gone, not stale. Plus: an OI write must not delete `mark_price`.

### H7 — `push_trade` reads the entire 2000-item list on every single trade
`hot_state.py:100-119`. `rows = await redis.lrange(key, 0, -1)` then msgpack-decodes all of them, on every trade, only to dedupe by `trade_id` and compare against the head's `ts`.
**Scenario:** with the real adapter subscribed to `aggTrade` for 200 symbols at a modest 10 trades/s each (2 000 trades/s), each trade pulls ~300 KB from Redis and decodes 2 000 msgpack objects — hundreds of MB/s of Redis traffic and millions of decodes per second. The ingest coroutine saturates the event loop, the 250 ms coalescer never flushes on time, the watchdog sees no accepted data for 30 s and restarts connections, escalating to a fatal exit after three restarts. The worker cannot survive real trade volume.
**Fix:** read only a bounded window — `await redis.lrange(key, 0, 49)` (module constant `TRADE_DEDUPE_WINDOW = 50`) — for both the duplicate check and the head-`ts` ordering check. A WS reconnect only ever replays a handful of recent trades, so a 50-item window covers the overlap; document the bound in the README (L4).
**Test:** assert the call reads a bounded range (a spy/fake Redis recording the `lrange` arguments is fine), and that a duplicate inside the window is still rejected.

### H8 — `push_candle` rewrites the whole 1500-item list on every candle
`hot_state.py:133-157`. Every accepted candle does `LRANGE 0 -1` (up to 1500 msgpack blobs), decodes them all, sorts, then `DELETE` + `RPUSH` of 1500 elements.
**Scenario:** once C1 is fixed, partials arrive roughly every second per symbol. At 200 markets that is ~200 full read-decode-sort-rewrite cycles per second over a 1500-element list — the same event-loop saturation as H7, plus the Redis list is briefly emptied by `DELETE` on every write, so a concurrent reader (the API in T1.4) can observe an empty candle list.
**Fix:** fast paths, keeping the current full rewrite only as a rare fallback:
1. `LRANGE key 0 15` (16 newest entries, module constant).
2. If an entry with the same `open_time` is found at index `i`, apply the existing precedence rules and `LSET key i <value>`.
3. Else, if the list is empty or the new `open_time` is greater than the head's, `LPUSH` + `LTRIM key 0 1499`.
4. Else (older than the 16-entry window) fall back to the current full read-modify-rewrite.
The precedence rules (H9, "partial never replaces final", "older partial rejected", "a late final of an older open_time updates its entry without moving or refreshing the head") must behave identically on all four paths.
**Test:** a normal new-minute final does not issue `DELETE`; the existing contract tests for the ordering rules must still pass unchanged.

### H9 — a final candle with the same `event_ts` as the last partial is rejected
`hot_state.py:144`. The `not _newer(event_ts, previous["ts"])` guard runs before the finality check, so a final that carries the same event timestamp as the last partial of that `open_time` is discarded.
**Scenario:** Binance emits the closing kline frame with the same `E` as the last partial update of that minute. The Redis list keeps the **partial** as the newest state of a closed minute, and the API serves an unclosed candle as the last known one. The contract says "final replaces partial" unconditionally.
**Fix:** check finality first — if the incoming candle `is_final` and the stored entry is not, always replace, regardless of `event_ts`. Keep "partial never replaces final" and "older partial rejected".
**Test:** partial at `ts=T`, then final at `ts=T` → the entry is final.

### H10 — the tick payload republishes a frozen price under a fresh timestamp
`ingest.py:98-103` and `:115-130`. `_TickAccum` keeps a single `ts` advanced by any of ticker/trade/book, and `reset()` preserves `price`/`bid`/`ask` across flushes. A book update alone marks the accumulator dirty and advances `ts`.
**Scenario:** trades and ticker stop for a symbol while the order book keeps updating. Every 250 ms the worker publishes `market.ticks` with the old `price` and a brand-new `ts`; the UI shows a live-looking price that has not moved in minutes with no way to tell.
**Fix (additive, so T1.4/T1.5 consumers do not break):** track `price_ts` and `book_ts` on `_TickAccum`, each advanced only by the event kind that owns it (`price_ts` by ticker and trade — both carry a price; `book_ts` by book), and add `price_ts` and `book_ts` to the payload built by `build_tick_payload`. Keep `ts` as the timestamp of the last accepted event of any kind, and keep every existing payload field with its current name and type. Document the three fields in the README (L4).
**Test:** ticker at T0, then only book events at T1 → payload has `ts=T1`, `price_ts=T0`, `book_ts=T1`.

---

## LOW (do them, they are one-liners)

- **L1** `ingest.py:250-254`: `_enqueue`'s `except asyncio.QueueFull` is dead code — `BoundedEvents.put_nowait` never raises, it drops with a metric. Remove the dead handler (or replace `_enqueue` with a direct call to `queues.events.put_nowait`). Do **not** edit `queues.py` — only the caller.
- **L2** `tests/test_contracts.py:73-89`: capture `head["ts"]` before the late-final write and assert it is unchanged afterwards, so the "late final does not refresh head freshness" guarantee is asserted directly rather than implied by the loop structure.
- **L4** `README.md`: state explicitly that liquidation identity is `uuid5` over `(exchange, symbol, side, normalized price, normalized qty, ts_ms)`, so **two genuinely distinct real-world liquidations sharing that exact tuple collapse into one row** — a documented, accepted M1 consequence of the deterministic id. Also document the H7 50-trade dedupe window, the H8 16-entry candle fast-path window, and the H10 `ts` / `price_ts` / `book_ts` fields with their exact meaning.

---

## Explicitly NOT in scope (do not "fix" these)
- Anything in `packages/exchange-adapters/**`: the missing `update_subscriptions`, the missing `fetch_realized_funding`, `parse_kline_ws` not filling `event_ts`, the missing `restart_connection`, the unbounded internal `asyncio.Queue`, and the reader tasks created with `ensure_future` outside the worker's `TaskGroup`. All belong to the T1.2 agent.
- The watchdog's `restart_stream` fallback tearing down both connections: accepted M1 behaviour pending T1.2's `restart_connection`.
- The persistence half (H1, H5, H6, M1, M2, M3, M4, M5, L3, L5 and the database-architect findings): another agent is doing it right now in the files listed as forbidden above.

## Verification you must run and paste verbatim in your report
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter
uv run pytest services/market-worker -q -p no:cacheprovider
uv run ruff check services/market-worker && uv run ruff format --check services/market-worker
uv run pyright services/market-worker
uv run python infra/scripts/check_file_size.py
```
Docker Desktop must be running (the integration tests need Postgres and Redis). If the full suite shows failures in `test_persist*.py` / `test_recovery*.py`, that is the other agent's work in flight — say so explicitly and report the result for your own files.

## Report format (final message, no report file)
One line per finding ID (C1, H2, H3, H4, H7, H8, H9, H10, L1, L2, L4): FIXED / NOT FIXED + why, the `file:line` you changed, and the name of the test that proves it. Then the verbatim command outputs. Then anything you found while fixing that you did **not** change, with its failure scenario. **Do not commit.**
