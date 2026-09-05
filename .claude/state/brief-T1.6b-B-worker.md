# Brief T1.6b-B — market-worker hot path (owner: backend-specialist)

## Why (measured, not guessed)
`py-spy` on the real container — full numbers in `.claude/state/t16b-profile.md`, raw data in
`.claude/state/profile/raw-50.txt` (50 markets) and `raw-200.txt` (200 markets).

At **50 markets** (CPU 95% of one core), the worker's own share:

| Function | Cumulative |
|---|---|
| `handle_event` (ingest.py) | **15.03%** |
| — `write_ticker` → `hot_state._hash` | **10.02%** |
| — `push_trade` | 2.48% |
| — `write_book` | 0.98% |
| `flush_ticks` (coalescer, 250 ms) | 3.25% |
| redis client self time (encode/send/parse) | 6.33% |

At **200 markets** the same functions collapse to 0.18% — not because they got fast, but because
the consumer is **starved**: the adapter's reader tasks take 66% of the loop and `handle_event`
never gets scheduled. Both problems are real and both must be fixed.

## Files you may touch (nothing else)
- `services/market-worker/hunter_market_worker/{streaming.py,hot_state.py,ingest.py,persist.py,queues.py}`
- `services/market-worker/tests/**`
- `services/market-worker/benchmarks/**` (new)
- `packages/core/hunter_core/runtime.py` (uvloop only — see B6)

**Do NOT touch**: `services/market-worker/hunter_market_worker/{config.py,universe.py,heartbeat.py,main.py,funding.py,recovery.py}`
(a second agent is sharding those in parallel), `packages/exchange-adapters/**` (a third agent is
in there), `apps/**`, `infra/**`, `packages/core/hunter_core/domain/**`, `.env`.

## What to implement (TDD: failing test first, then the change)

### B1 — the consumer loop creates a task and a timer per event (`streaming.py:36-37`)
`consume_once` does `asyncio.ensure_future(stream.__anext__())` + `asyncio.wait({...}, timeout=0.1)`
**per event**: one new Task, one `call_at` entry in the loop's timer heap and one cancellation for
every single event, purely so it can poll `universe.changed` and `watchdog.restart_stream` every
100 ms. At ~30 000 events/s that is pure overhead and it is one of the reasons the consumer loses
the loop to the reader tasks.

Required: drain the stream with a plain `async for` (no per-event task, no per-event timer) and
move the 100 ms housekeeping (universe diff → `adapter.update_subscriptions`,
`watchdog.restart_stream`, `health.observe_adapter`) into a **separate task with its own
`asyncio.sleep(0.1)` loop**, cancelled in the `finally`. Every existing behaviour must be preserved
and proven by a test:
- a universe diff still calls `update_subscriptions(added, removed, CHANNELS)` and updates the
  local `symbols` list, and an adapter without `update_subscriptions` still raises `RuntimeError`;
- `watchdog.restart_stream = True` still returns from `consume_once` (and clears the flag) even
  when **no event is arriving at all** — this is the regression an `async for` most easily breaks;
- `health.observe_adapter` is still called at least every ~100 ms with `active=bool(symbols)`,
  including when the stream is silent;
- `StopAsyncIteration` from the stream still becomes `RuntimeError("task stream exited unexpectedly")`;
- events whose `symbol` is no longer in `symbols` are still skipped;
- `heartbeat_state.last_event_at` still only moves forward (`max`), and only for accepted events;
- the `finally` still cancels cleanly and calls `stream.aclose()`.
Keep `services/market-worker/tests/test_ingest_integration.py` and `test_supervision.py` green.

### B2 — one Redis round trip per event, then per cycle: `hot_state._hash`
`_hash` runs `WATCH key` + `HGET key ts_field` (round trip 1), then `MULTI/HSET/HDEL/EXPIRE/EXEC`
(round trip 2), inside a `WatchError` retry loop — **for every bookTicker frame**. That is the
10.02% above.

Required: replace it with a **single `EVALSHA` Lua script** that does the whole thing atomically in
one round trip: read `ts_field`, compare against the incoming ISO timestamp, and only if newer do
`HSET mapping` + `HDEL stale...` + `EXPIRE ttl`; return 1/0 so the Python side keeps returning the
same `bool`. Requirements:
- the timestamp comparison must be **on the actual instants, not on string bytes** — pass the
  incoming value as epoch microseconds (or compare the stored ISO string only if you can prove in
  a test that every writer emits the same canonical, lexicographically-orderable form; the safe
  route is a numeric field). If you introduce a numeric ts field alongside the ISO one, the ISO
  field that `apps/api` and the UI read (`ts`, `funding_ts`, `mark_ts`, `oi_ts`) **must keep its
  exact current name, format and meaning** — `apps/` is off-limits and must not need a change.
- cache the SHA per Redis client, and fall back to `EVAL` on `NOSCRIPT` (a Redis restart flushes
  the script cache — T1.6 already proved Redis restarts happen; a `NOSCRIPT` that kills the worker
  is a regression, write the test).
- keep the "owned fields" semantics exactly (`TICKER_FIELDS`, `FUNDING_FIELDS`, `MARK_FIELDS`,
  `OI_FIELDS`: an owned field absent from the incoming mapping is `HDEL`-ed in the same atomic
  step — H4). Existing `tests/test_hot_state.py` must stay green.

### B3 — coalesce the hot-state writes into the 250 ms cycle (the "one round trip per symbol per cycle" the plan asks for)
Today every bookTicker writes the ticker hash, every depth20 frame writes the book key, and
`flush_ticks` then does **two awaited Redis commands per dirty symbol, serially** — at 200 symbols
that is ~400 round trips every 250 ms on top of the per-event ones.

Required:
- Keep the latest ticker and the latest book **snapshot** per `(exchange, symbol)` in memory
  (a book from `@depth20` is a full snapshot: a newer one entirely supersedes an older one, so
  coalescing loses nothing but latency), and write them to Redis **once per `tick_coalesce_ms`
  cycle**, batched: build **one** `redis.pipeline(transaction=False)` for the whole cycle carrying
  every symbol's ticker script call, book SET, `XADD` and `PUBLISH`, and `await pipe.execute()`
  once. Not one pipeline per symbol.
- `handle_event` must keep returning the same `bool` ("was this event accepted") without a Redis
  round trip: the in-memory monotonic gate already exists (`AcceptedEvents.accept`). Prove with a
  test that an out-of-order ticker/book/funding is still rejected and does not move
  `health`/`watchdog`/`heartbeat_state`.
- **Trades and final candles keep their existing per-event semantics** (a trade is not a snapshot
  and a final candle must never be lost/coalesced) — but batch them into the same cycle pipeline
  where ordering allows, and say in your report exactly what you batched and what you did not.
- The cost of the change is up to `tick_coalesce_ms` (250 ms) of extra staleness in
  `mkt:ticker:*`/`mkt:book:*`. That is inside `MARKET_STALE_AFTER_S = 10`. State it explicitly in
  your report and add a test asserting the flush interval is the coalescer's, not longer.
- A shutdown/cancellation must flush what is buffered (or, if you choose not to, say so and prove
  the data is recoverable) — do not silently lose a final candle.

### B4 — `push_trade` reads 50 msgpack rows per trade (2.48%)
`push_trade` does `LRANGE key 0 49` + `msgpack.unpackb` on all 50 **per trade** just to dedupe.
Required: keep an in-memory, bounded (per-symbol) set/deque of recent `trade_id`s for the dedupe
and the "older than head" check, and reduce Redis to a pipelined `LPUSH` + `LTRIM`. Correctness
requirements to prove with tests:
- a duplicate `trade_id` inside the window is still rejected (this is what protects against a WS
  reconnect replaying recent trades — the reason the window exists);
- a trade older than the newest known one is still rejected;
- the per-symbol memory is bounded and is dropped when a symbol leaves the universe (otherwise
  the 15-minute universe refresh grows it forever — the same bug class as F11 in `ws.py`);
- a worker restart (cold in-memory state) must not duplicate trades in Redis — decide how (e.g.
  seed the in-memory window from one `LRANGE` on first touch of a symbol) and test it.

### B5 — `TickCoalescer` parses ISO strings on every event (`ingest.py:92-93,102-103,110-111`)
`max(filter(None, [accum.price_ts, event_ts]), key=datetime.fromisoformat)` runs
`datetime.fromisoformat` **twice per event**. Store `datetime` objects in `_TickAccum` and format
to ISO **once, at flush time**. `build_tick_payload`'s output must stay byte-identical (it is the
`market.ticks` / `rt:market:*` wire contract the frontend reads) — add a test comparing the payload
built from the old and new accumulators for the same event sequence.

### B6 — uvloop in the container (`packages/core/hunter_core/runtime.py`)
`uvloop` is already installed in the Linux image (transitively via `uvicorn[standard]`). Install it
with a **guarded** import: `try: import uvloop` / `except ImportError: pass`, only when
`sys.platform != "win32"`, and log once which loop policy is active (`runtime_event_loop`,
structlog). It must never change behaviour on Windows (local tests run there) and never be a hard
dependency. Add a test that the fallback path is taken when the import fails.
If the benchmark shows no gain, keep it anyway only if it costs nothing; report the measured delta.

### B7 — the benchmark (this is a deliverable, not optional)
`services/market-worker/benchmarks/bench_ingest.py`, **not** collected by pytest:
- builds a 60-second corpus of events with the **real payload shapes** from
  `packages/exchange-adapters/hunter_exchanges/testing/fixtures/ws_*.json` fanned out over N
  symbols with a realistic channel mix (aggTrade heaviest, then bookTicker, then depth20, then
  kline/markPrice), values varied deterministically from a fixed seed;
- feeds them through `handle_event` + the coalescer flush against a **real Redis** (the one in
  `docker compose`, via `REDIS_URL`) — a fake Redis measures nothing about round trips;
- prints **events/s, µs/event, and Redis round trips per 1000 events**.
Run it on the current `HEAD` (via `git stash` or a worktree) and after your change; paste **both**
outputs. A performance claim without this pair is rejected.

## Verification you must run and paste (real output, not a claim)
```
uv run pytest services/market-worker -q -p no:cacheprovider
uv run pytest packages/core/tests/unit -q -p no:cacheprovider
uv run ruff check services/market-worker packages/core
uv run ruff format --check services/market-worker packages/core
uv run pyright services/market-worker packages/core
uv run python infra/scripts/check_file_size.py
```

## Hard rules (CLAUDE.md)
Money is `Decimal`, never `float`. Every timestamp is timezone-aware UTC. No local state files —
Postgres + Redis only (the in-memory windows in B3/B4 are per-process caches of Redis-backed data,
which is fine; they must never become the source of truth). No file over 350 lines. No secrets,
never read `.env`. No fake data in the product (the benchmark corpus is a benchmark, it must never
be importable by the worker). `structlog` only, no `print` in library code.
**Do not commit** — Sexta-feira commits per task.

## Report format
`## Segunda opinião (Astra)` is mandatory. Before reporting, run:
`bash infra/scripts/astra.sh ask t16b-B-diff "<your question about your own diff>"`
and say what she flagged, what you fixed, what you rejected and why. If Astra is unavailable, say
"Astra indisponível: <erro>" and continue — never fake her answer.
Then: what changed per file · before/after benchmark output · the real output of every verification
command · exactly what extra staleness the coalescing introduces · what you did NOT do and why.
