# Brief T1.6b-A — Binance adapter hot path (owner: exchange-integration-specialist)

## Why (measured, not guessed)
`py-spy` was attached to the real container (`.claude/state/t16b-profile.md`, raw data in
`.claude/state/profile/raw-50.txt` and `raw-200.txt`). At **200 markets** the process burns
**99.9% of one core** and:

| Frame | Self time (200 mkts) |
|---|---|
| `pydantic/main.py:__init__` | **20.36%** |
| `event_queue._is_final_kline` (l.30-31) | **11.51%** |
| `event_queue._evict_one` (l.66/67/70) | **6.30%** |
| `json.loads` (stdlib) | 6.23% |
| `normalize.to_decimal` / `ms_to_datetime` | 5.69% |

Cumulative: `_handle_raw_message` = **66.05%**, `parse_stream_message` = 33.92%, of which
`parse_depth20` = **23.02%** and `parse_book_ticker` = 7.82%. The worker's own consumer
(`handle_event`) gets **0.18%** — it is starved, which is exactly why T1.6 measured book in
8/200 and 11.6 M dropped events.

## Files you may touch (nothing else)
- `packages/exchange-adapters/hunter_exchanges/binance/{ws.py,streams.py,event_queue.py,normalize.py,connection.py,subscriptions.py}`
- `packages/exchange-adapters/tests/**`
- `packages/exchange-adapters/benchmarks/**` (new)
- `packages/exchange-adapters/pyproject.toml` (only to add `orjson>=3.10`; then run
  `uv sync --all-packages`, which will touch the root `uv.lock` — that is expected and is the
  only file outside this list you may change)

**Do NOT touch** `services/**`, `apps/**`, `packages/core/**`, `infra/**`, `docs/**`, `.env`.
Another agent is editing `services/market-worker/**` in parallel.

## What to implement (TDD: failing test first, then the change)

### A1 — O(1) eviction in `event_queue.py` (biggest pure-waste win: ~17.8%)
`_evict_one` walks a 10 000-item `deque` from index 0 on **every** `put` while the queue is
full, calling `isinstance` + attribute access per item, then `del self._items[index]` (O(n) on a
deque). Under real saturation every put pays it — a positive feedback loop.

Required: eviction becomes O(1) amortised **with the exact same observable contract**:
- a final kline is never the eviction victim;
- when the queue is full of finals and the incoming event is not a final, the incoming one is
  dropped and counted on its own connection key;
- when both are finals, `put` awaits `_has_room` (real backpressure), size never exceeds `maxsize`.

Suggested shape (you choose, justify in the report): keep two deques — `_normal` and `_finals` —
plus a monotonic sequence number per item so `get()` still returns strict FIFO across both;
eviction is then `self._normal.popleft()`. Or keep one deque plus a `_final_count` and evict from
the head whenever the head is not a final (the common case), falling back to the scan only when
`_final_count == len(self._items)`. Whatever you pick, `_is_final_kline` must stop being called
O(n) times per put.

Existing tests in `packages/exchange-adapters/tests/unit/test_event_queue.py` must all still pass
unchanged; add tests for: strict FIFO ordering preserved across the two-structure split, eviction
never picking a final, the both-finals backpressure path, and a performance regression guard
(e.g. 50 000 puts into a full queue complete under a generous wall-clock budget).

### A2 — stop paying pydantic validation per event (~20% self time)
In `streams.py`, build every `Normalized*` with `Model.model_construct(...)` instead of
`Model(...)`. The **public type stays identical** — no contract change for any consumer of
`adapter.stream()`. What is lost is pydantic's validators, so you must keep the guarantees
explicitly and cheaply in the parsers:
- `ts` UTC-aware: already guaranteed by `ms_to_datetime` (returns `tz=UTC`). Add a unit test that
  proves a constructed event's `ts.tzinfo` is UTC for every channel.
- `BookLevel.qty >= 0`: keep as an explicit check in `parse_depth20` (raise `MalformedMessage`).
- bids sorted desc / asks sorted asc: keep as an explicit check in `parse_depth20` (raise
  `MalformedMessage`). Do not silently drop this guarantee.
- `received_at` / any `default_factory`: `model_construct` applies defaults; add a test asserting
  `received_at` is populated and UTC-aware for each event type.
- Add a test that a malformed payload still raises `MalformedMessage` for every channel (every
  existing case in `tests/unit/test_streams.py` must keep passing verbatim).

### A3 — `orjson` in `ws.py::_handle_raw_message` (~6%)
Replace `json.loads(raw)` with `orjson.loads(raw)`. `orjson.JSONDecodeError` subclasses
`ValueError`; adjust the `except` clause so a malformed frame is still counted and logged and
never propagates. `orjson.loads` accepts `bytes` directly — prefer feeding it the raw bytes
without a `.decode()`. Keep `malformed_count` semantics identical.

### A4 — cheaper `normalize.to_decimal` / `ms_to_datetime` (~5.7%)
- `to_decimal` does `Decimal(str(value))`: when `value` is already a `str` (the Binance case,
  always), skip the `str()` call. Keep the `bool`/`None`/`float` rejections exactly as they are
  (CLAUDE.md: money is `Decimal`, never `float`) and keep every existing test passing.
- `ms_to_datetime`: only change it if the benchmark shows a real gain, and prove with a
  round-trip/property test over a range of epoch-ms values that the output is identical to the
  current implementation (same value, same `tzinfo`).

### A5 — configurable book cadence, default 500 ms (halves the 23%)
`_CHANNEL_SUFFIX[StreamChannel.BOOK]` is `"depth20"` (Binance default 250 ms). Make the cadence a
module-level/constructor parameter with **default `500`** producing `"depth20@500ms"`, and keep
`250` reachable (empty suffix) for anyone who needs it. `channel_for_stream_name` must keep
resolving both `depth20` and `depth20@500ms` back to `StreamChannel.BOOK` — the reverse map routes
incoming frames, so breaking it turns every book frame into "unknown stream".
Add tests for both directions and for a connection subscribed at 500 ms receiving a frame named
`depth20@500ms`. Also check `subscriptions.py` / `MAX_STREAMS_PER_CONNECTION` assumptions still hold.
Record in your report that this changes the M1 joint decision ("depth20 sem sufixo, 250 ms"); the
evidence is `parse_depth20` = 23% of one core at 200 markets.

### A6 — `parse_depth20` allocation cost
Beyond `model_construct`, avoid the wasted work: `raw["b"]`/`raw["a"]` are lists of
`[price_str, qty_str]`. Build the 20+20 `BookLevel`s with `model_construct` and `Decimal(value)`
without the intermediate `str()` (A4). Do not change `NormalizedOrderBook`'s public shape —
`packages/core/hunter_core/domain/market.py` is off-limits for this task.

## Verification you must run and paste (real output, not a claim)
```
uv run pytest packages/exchange-adapters -q -p no:cacheprovider
uv run ruff check packages/exchange-adapters
uv run ruff format --check packages/exchange-adapters
uv run pyright packages/exchange-adapters
uv run python infra/scripts/check_file_size.py
```
Plus a micro-benchmark you write at `packages/exchange-adapters/benchmarks/bench_parse.py`
(must NOT be collected by pytest — keep it out of `tests/`):
- loads the real recorded frames from `hunter_exchanges/testing/fixtures/ws_*.json`;
- replays each channel N times through `parse_stream_message` (N large enough for a stable
  number: ~200 000 for bookTicker/aggTrade, ~20 000 for depth20);
- prints **events/s and µs/event per channel**, plus a combined number for a realistic channel mix.
Run it against the current `HEAD` (use `git stash` or a worktree) and after your change, and paste
**both** tables. That before/after pair is the deliverable — a claim without it is rejected.

## Hard rules (CLAUDE.md)
Money is `Decimal`, never `float`. Every timestamp is timezone-aware UTC. No file over 350 lines
(`check_file_size.py`). No secrets, never read `.env`. No fake data. `structlog` only, no `print`
in library code (the benchmark script may print). **Do not commit** — Sexta-feira commits per task.

## Report format
`## Segunda opinião (Astra)` is mandatory. Before reporting, run:
`bash infra/scripts/astra.sh ask t16b-A-diff "<your question about your own diff>"`
and say what she flagged, what you fixed, what you rejected and why. If Astra is unavailable, say
"Astra indisponível: <erro>" and continue — never fake her answer.
Then: what changed per file · before/after benchmark tables · the real output of every verification
command · what you did NOT do and why · any risk you are handing over.
