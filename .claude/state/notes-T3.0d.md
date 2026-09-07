# T3.0d — closing the SPOT identity gap before `MARKET_SPOT_ENABLED` in any shared environment

**Date:** 2026-09-07. **Scope:** `services/market-worker/**`, `services/scanner-worker/**` (one
line), `packages/exchange-adapters/hunter_exchanges/binance_spot/identity.py` (docstrings only),
`docs/PIPELINE.md`. No commit. Nothing touched under `.env*`, `infra/migrations/**`,
`services/execution-worker/**`, `packages/core/hunter_core/{admission,db}/**`,
`tests/integration/paper/**`, `apps/**`.

Closes the item `review-T3.0b.md` marked "blocking for T3.0d" and `notes-T3.0c.md` §12
ressalva 9 explicitly deferred here.

---

## 1. The blocking bug, and the fix

**Reproduced before the fix (2026-09-07, same as `notes-T3.0c.md` §12 ressalva 9):** a perpetual
and a spot candle of `BTCUSDT` closing the same minute hashed to the identical uuid5
(`candle_event_id` derived only from `exchange`/`symbol`/`timeframe`/`open_time`, and those four
are equal for the two listings). The row in `candles` was correct for both products
(`load_market_ids` already resolves per `market_type` since T3.0b), but the outbox's
`ON CONFLICT (event_id) DO NOTHING` silently dropped whichever `market.candles.closed`
committed second — no consumer of the closed-candle stream ever saw that side's close.

**The fix, in `durable.py` and `backfill_announce.py`:** the same spelling
`universe_event_id` already used (T3.0c) — `venue = keys.market_slug(exchange, "",
market_type).rstrip(":")` — now feeds `candle_event_id` and
`backfill_announce.candles_backfilled_event_id` instead of the bare `exchange`. For
`PERPETUAL`, `venue == exchange` (byte-identical string), so **no id already announced in
production changes**. For `SPOT`, `venue == f"{exchange}:spot"`, so the two listings never
collide. The envelope `key=` of both events got the same treatment (`keys.market_slug(exchange,
symbol, market_type)`), matching what `market.ticks` already does since T3.0c.

Pinned in a test (`test_outbox_producers.py`):
`durable.candle_event_id` of `binance`/`BTCUSDT`/`M1`/`2026-09-07T07:00:00Z` is
**`40b42f73-c29e-5e66-ad43-670b8f7d1ae4`** for `PERPETUAL` — computed by hand against the
formula exactly as it stood before this fix (`event_id_for(stream, exchange, symbol,
timeframe.value, open_time)`), and asserted unchanged.

**Same collision, same fix, in `market.candles.backfilled`.** `candles_backfilled_event_id` had
the identical shape (`exchange, symbol, timeframe, "rest", start, end`, no `market_type`), and
the recovery path runs for both products (`spot.py`'s `spot-recovery` task calls
`run_recovery(..., MarketType.SPOT)`, which reaches `recovery_drain.py`'s
`enqueue_candles_backfilled`). Fixed the same way; `market_type` is read off `candles[0]`
(the caller is always one gap's recovery, one market) and added to the payload additively.

**Checked, not colliding today:** `market.backfill.requested` (produced by `scanner-worker`,
which has no spot universe — out of scope and out of reach of this collision) and
`market.derivatives`/`market.liquidations` (funding, open interest and liquidations do not
exist on spot — `NormalizedFunding`/`NormalizedOpenInterest`/`NormalizedLiquidation` carry no
`market_type` field at all, and nothing produces them from the spot adapter). `market.ticks` is
ephemeral (no outbox, no `event_id` dedup) — not affected by this class of bug by construction.
`market.universe.changed` was already fixed in T3.0c; unchanged here.

## 2. `load_market_ids` filter — dedicated test

`market_ids.py:47` had no test of its own before this: the filter was only ever exercised
incidentally through callers that seeded a single listing. New file
`services/market-worker/tests/test_market_ids.py`: seeds `binance` perp + spot of the same
symbol, asserts each `market_type` gets only its own `market_id`, that the default stays
`PERPETUAL` (byte-identical answer to before spot rows existed), and that an empty symbol set
short-circuits without a query.

## 3. `binance_spot/identity.py` docstrings

Rewrote the module docstring's "known gap" paragraph (T3.0b closed it: every event model
carries `market_type`, defaulting to `PERPETUAL`; every Redis key builder folds it into the
venue segment) and the `market_identity()` function's docstring, which implied a Redis key
template (`mkt:{exchange}:{market_type}:{symbol}:...`) that is **not** how real hot-state keys
are built — the perpetual's real key has no segment at all. Clarified that `market_identity()`
is for the adapter's own in-memory identity string, not the hot-state key shape, and pointed at
KB-0044 for why the ticker hash's own fields never carry `market_type`.

## 4. Scanner contamination — closed

`hunter_scanner_worker/main.py::touch_batch_handler` now drops (with ACK, no reprocessing) any
delivery whose `payload.get("market_type", "perpetual") != "perpetual"` **before** coalescing
the batch — one filter, both problems it caused (`notes-T3.0c.md` §6) fixed at once: a spot tick
no longer marks the perpetual's `MarketState` dirty, and no longer contaminates
`scanner_stream_delay_seconds` with a different venue's latency. Two new unit tests in
`test_consumers.py::TestTouchHandler` (a spot-only batch touches nothing and the perpetual's
delay histogram gets no sample from it; a perpetual tick right after still gets sampled).

## 5. Ticker hash — `mkt:*:ticker` assertions

Two new tests in `test_market_type_identity.py`, closing `review-T3.0b.md` item 4:
- the hash never carries a `market_type` field on either listing's key (the discriminator is
  already the key, KB-0044);
- writing a spot ticker never creates or mutates the perpetual's own key
  (`mkt:{exchange}:{symbol}:ticker`, no venue segment) — the write always lands on the spot's
  separately-keyed hash.

The code side of this (`hot_state.py::_ticker_fields` popping `market_type` before building the
hash mapping) already existed since T3.0b/c; only the test coverage was missing.

## 6. `docs/PIPELINE.md` — new §1d

Added the spot data-path section the two prior tasks never wrote: universe rule, identity
scheme, the hot-state keys (`mkt:{ex}:spot:{sym}:*`, `hb:market:spot:{ex}`), the pub/sub channel
(`rt:market-spot:{ex}:{sym}`, unreachable today by design — grammar refuses it, no subscriber),
the event-id fix from §1 above, the scanner filter from §4, readiness semantics, and the
condition for turning `MARKET_SPOT_ENABLED=true` on anywhere shared (event-loop headroom on
shard 0, with the exact A/B numbers from `t30-proof.md` §1 reproduced in the doc). Left the
floor's flapping (`PROMUSDT`) as an open question for Everton, as instructed — not decided here.

## 7. Honest concerns

1. **Not re-verified live.** This task fixed and unit/integration-tested the collision against
   the local stack's fixtures and a real Postgres/Redis via testcontainers, but did **not**
   rerun the live A/B of `t30-proof.md` (Astra unavailable until 2026-09-12 per the brief's own
   note, and the brief's operational rule keeps this offline/foreground). The numbers quoted in
   `PIPELINE.md` §1d are copied from `t30-proof.md`, not re-measured.
2. **`market_backfill_planned`/`market_persist_flush_failed` still don't log `market_type`**
   (`notes-T3.0c.md` §12 ressalva 3) — pre-existing observability gap, not touched here; out of
   this brief's five numbered items.
3. **The floor's hysteresis question is explicitly left open** in `docs/PIPELINE.md` §1d, per
   the brief's instruction not to decide it.
4. Ran the full scope named in the brief's "Provar" section (all `test_spot_*`,
   `test_persistence_contracts`, `test_outbox_producers`, `test_market_type_identity`, the two
   new files/tests, `packages/exchange-adapters`, `services/scanner-worker/tests -m unit`) plus a
   few adjacent files that touch the same producers (`test_recovery.py`,
   `test_recovery_contracts.py`, `test_backfill_consumer.py`, `test_backfill_lane.py`,
   `test_universe_outbox.py`, `test_recovery_gate.py`) as a wider regression check, one file per
   `pytest` invocation. Did not run the entire `services/market-worker` suite file by file
   (~40 files); the untouched files have no dependency on `durable.py`'s or
   `backfill_announce.py`'s changed functions beyond what was exercised.

## 8. Event ids — changed vs. byte-identical

**Changed (spot only; perpetual pinned unchanged):**
- `durable.candle_event_id` — spot candles of `market.candles.closed` now hash a distinct id
  from the perpetual of the same symbol/minute.
- `backfill_announce.candles_backfilled_event_id` — spot `market.candles.backfilled` batches now
  hash a distinct id from a perpetual batch of the same symbol/timeframe/span.

**Byte-identical to before this task (and to before T3.0b/c, for every input that existed then):**
- `durable.candle_event_id` for `market_type=PERPETUAL` — pinned in
  `test_the_perpetuals_candle_event_id_is_the_exact_value_it_had_before_market_type_existed`.
- `backfill_announce.candles_backfilled_event_id` for `market_type=PERPETUAL`.
- `durable.funding_event_id`, `durable.open_interest_event_id`,
  `hunter_market_worker.publication.liquidation_id` — untouched, no `market_type` involved (spot
  produces none of these).
- `durable.universe_event_id` — already fixed in T3.0c; not touched again here.
- Every Redis hot-state key builder in `hunter_core.redis.keys` — not touched in this task.
