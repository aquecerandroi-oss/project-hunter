# Fix brief — T1.2 + T1.2b reconciliation pass (`packages/exchange-adapters/**`)

**Owner:** `exchange-integration-specialist` · **Date:** 2026-09-05 · **Do NOT commit.**

Sources reconciled by the orchestrator: `code-reviewer` (2026-09-05), `exchange-integration-specialist`
cross-review (2026-09-05), Astra adversarial final (`.claude/state/astra-review-review-T1.2-final.md`).

Baseline before this pass: `uv run pytest packages/exchange-adapters -q -p no:cacheprovider` →
**155 passed, 2 skipped**; ruff/format/pyright clean; `check_file_size.py` clean;
`hunter_exchanges/binance/ws.py` = 349 lines (budget 350 — **you will need to extract a module**).

---

## Allowed files
`packages/exchange-adapters/**` and nothing else. Do not touch `services/market-worker/**`,
`apps/**`, `packages/core/**`, `docs/**` — other tasks are in flight there and their tests are
unstable right now. Never read `.env`. Never commit.

## Rules that apply (CLAUDE.md)
`Decimal` for every price/qty/notional (never `float`), UTC-aware datetimes, `structlog` never
`print`, no file over 350 lines, no raw exchange field outside `metadata`, no fabricated numbers,
async everywhere on the IO path, TDD (write the failing test first, then the fix).

---

## F1 — HIGH — `fetch_funding()` returns the realized rate mislabeled as estimated
`binance/rest.py:251-256` + `binance/normalize.py:269-297`.
`fetch_funding()` calls `/fapi/v1/premiumIndex` **and** `/fapi/v1/fundingRate?limit=1`, and
`parse_funding` prefers the history rate, then leaves `funding_kind` at its default `"estimated"`.
With the checked-in fixtures: `premium_index.json.lastFundingRate = 0.00000649` vs
`funding_rate.json[0].fundingRate = 0.00001014` — a 36 % difference. Any consumer gets a stale,
already-settled number stamped as a fresh estimate.

**Orchestrator decision (final, not open for debate):** `fetch_funding()` returns the
`premiumIndex` estimate with `funding_kind="estimated"` explicitly set; realized history comes
**only** from `fetch_realized_funding()`.

Do: `fetch_funding()` issues a single `/fapi/v1/premiumIndex` request (weight 1). `parse_funding`
loses its `funding_history` parameter and builds from `lastFundingRate`, `markPrice`,
`indexPrice`, `nextFundingTime`, `time`, with `funding_kind="estimated"`. Put any extra raw field
you want to keep (e.g. `estimatedSettlePrice`, `interestRate`) in `metadata`.
Replace `tests/unit/test_normalize_rest.py::test_parse_funding_prefers_the_realized_history_rate`
and `::test_parse_funding_falls_back_to_premium_index_when_history_is_empty`, and
`tests/unit/test_rest_client.py::test_fetch_funding_combines_premium_index_and_funding_rate`
with tests that pin the new contract, including one asserting `fetch_funding` makes exactly one
HTTP call and never hits `/fapi/v1/fundingRate`.

## F2 — HIGH — Redis bucket TTL (120 s) shorter than the funding window (300 s)
`rate_limit.py:32` (`_BUCKET_STATE_TTL_S = 120`) vs `binance/rest.py:45`
(`FUNDING_HISTORY_WINDOW_S = 300.0`).
Failure scenario (Astra, reproduced): the funding bucket spends its 500 calls at the start of a
5-minute window, then sits idle 121 s; the Redis key expires; the next `acquire` recreates the
bucket at full capacity and allows another 500 calls **inside the same exchange window** →
`429`, then `418` (IP ban, 2 min to 3 days) which takes the whole market-worker down.
Do: derive the TTL from the limiter's own `refill_period_s` (e.g. `max(2 * refill_period_s, 120)`)
so state can never expire inside a window. Test: a limiter with a 300 s period writes a key whose
TTL is ≥ 600 s.

## F3 — HIGH — `record_used_weight` releases in-flight reservations
`rate_limit.py:180-207`. It sets `tokens = capacity - used_weight` unconditionally; the existing
guard only rejects a *header lower than a previous header*, never a header lower than what this
process has already consumed locally.
Failure scenario (Astra, reproduced, single process): cold start fires 200 concurrent
`fetch_candles(limit=1500)` at weight 10 → 2000 weight reserved locally. The **first** response
returns `X-MBX-USED-WEIGHT-1M: 10` → the bucket is reset to `2400 - 10 = 2390` tokens, releasing
1990 of weight already in flight, and the remaining requests flood out → `429`/`418`.
Do: the header may only ever **take budget away**, never give it back —
`new_tokens = min(current_tokens_after_refill, capacity - used_weight)`. Keep the existing
stale-header guard. Test the exact scenario above (reserve N, then apply a low header, assert the
tokens did not increase).

## F4 — HIGH — a `429` on one bucket does not stop the other bucket (same IP)
`rate_limit.py:216-226` + `binance/rest.py:150-160`. `cooldown()` only drains the offending
bucket's tokens; the funding-history limiter and the general-weight limiter are two separate
instances sharing one IP, and there is no deadline honouring `Retry-After`.
Failure scenario (Astra, reproduced): the exchange answers `429` with `Retry-After: 60`; a
weight-1 call on the other bucket goes out **25 ms later**; Binance escalates to `418` and bans
the IP. The whole worker loses market data.
Do: add a small process-local IP gate (monotonic `blocked_until`, shared object injected into
both limiters — `TokenBucketRateLimiter(..., ip_gate=gate)`), set from the `Retry-After` of any
`429`/`418`, consulted at the top of `acquire()` for **every** bucket. Raise `RateLimited` (do not
sleep past `max_wait_s`). Cross-process persistence stays out of scope — see "known limitations".
Test: a `429` with `Retry-After: 60` on the funding bucket makes the next general-bucket
`acquire()` wait/raise instead of passing.

## F5 — HIGH — catch-up overshoots the 1024-stream limit
`binance/subscriptions.py:199-220` (`catch_up`) sends `SUBSCRIBE` **before** `UNSUBSCRIBE`.
Failure scenario (Astra, reproduced): a market connection opens with 200 symbols × 4 channels =
800 streams; 100 symbols are swapped during the handshake; catch-up goes 800 → **1200** → 800.
The intermediate state is over Binance's documented 1024 streams/connection and the SUBSCRIBE
can be rejected; the error-ACK path (see F6) does not recover the desired set.
Do: in `catch_up`, send `UNSUBSCRIBE` first, then `SUBSCRIBE` (that is already the order in
`update()`). Test the overshoot: assert the sent-frame order and that the declared stream count
never exceeds 1024 at any intermediate step.

## F6 — HIGH — a rejected subscription stays reported as active
`binance/subscriptions.py:189-198, 232-245`. State is updated right after `send()`, and
`resolve_ack` only logs on an error ACK.
Failure scenario: the 15-minute universe refresh adds `ETHUSDT`; the SUBSCRIBE comes back with an
error ACK (or never gets an ACK). `states[key].subscriptions` still lists it, the other 199
symbols keep streaming so nothing looks stale at the connection level, and `ETHUSDT` silently has
no book/trade/kline for the life of the connection (up to 23.5 h).
Do: keep the group's *desired* set as the source of truth; on an error ACK (or an ACK that never
arrives within a short deadline) drop the affected names from `states[key].subscriptions`, log a
warning with the names, and force that one connection to reconnect so it resubscribes from the
desired set. Also: a `send()` failure inside `update()` must not propagate raw to the caller —
route it through the same reconnect path (`catch_up` was already fixed this way).
Test: error ACK → names removed from the reported subscriptions and the connection restarts.

## F7 — HIGH — the rotation deadline never fires on a quiet socket
`binance/ws.py:246-250`: `raw = await connection.recv()` has no deadline; the
`while self._clock() - connected_at < max_age` check only runs *between frames*.
Failure scenario (Astra, reproduced): a market connection whose symbols go quiet (or a half-open
TCP socket with no FIN) never rotates. Binance's own 24 h cut closes it instead — an unplanned
disconnect at an arbitrary moment, and in the half-open case nothing at all is detected inside the
adapter; only the worker's 30 s watchdog notices, and its fallback tears down **every** connection.
Do: give `recv()` a deadline — `asyncio.wait_for(connection.recv(), timeout=...)` bounded by the
remaining rotation time and by an idle timeout. Timeout with the rotation deadline reached →
rotate cleanly (no backoff, as today). Idle timeout before the deadline → treat as a connection
failure and reconnect with backoff. Test both: quiet socket rotates at the deadline; quiet socket
past the idle timeout reconnects.

## F8 — MEDIUM — `restart_connection(key)` is still missing
`binance/ws.py` / `binance/__init__.py`. The worker checks
`getattr(self.adapter, "restart_connection", None)` (`services/market-worker/.../supervision.py:134`)
and falls back to `restart_stream = True`, which calls `aclose()` and cancels every task.
Failure scenario: only `market:0` goes silent; the healthy `public:0` connection — book and
best bid/ask for all 200 symbols — is torn down with it, creating an avoidable book/ticker hole
across the whole universe on every single-connection stall.
Do: `async def restart_connection(self, key: str) -> None` on `BinanceWsClient`, delegated by
`BinanceAdapter`, that cancels and restarts only that connection's task (reusing `_start_group`),
leaving the others untouched. Declare it in `ExchangeAdapterExtras`. Test: restarting `market:0`
leaves `public:0`'s task alive and its state untouched.

## F9 — MEDIUM — a malformed bookTicker frame counts as a healthy frame
`binance/streams.py:337-339`: for `BOOK_TICKER` the dispatcher returns `None` when `last_price`
is unknown **before validating the payload**, so `{"stream": "btcusdt@bookTicker", "data": {}}`
is treated as a well-formed frame (`ws.py:313-315` advances `last_data_event_*` and resets the
backoff attempt counter, `malformed_count` stays 0).
Failure scenario (Astra, reproduced): a connection emitting only garbage bookTicker frames looks
alive, keeps resetting the reconnect backoff to its minimum and never increments the malformed
counter — the "ACK/garbage is not proof of life" rule of the joint decision is bypassed.
Do: validate the required bookTicker fields (`s`, `b`, `a`, `B`, `A` and `T`/`E`) even when the
frame is deferred for want of a last price; a payload missing them raises `MalformedMessage`.
A *valid* deferred bookTicker keeps counting as proof of life (that is the recorded M1 decision).

## F10 — MEDIUM — two trades in the same millisecond can regress the cached last price
`binance/ws.py:319-323` compares `event.ts >= cached[1]` only.
Failure scenario (Astra, reproduced): aggTrade id 2 @ 200 then id 1 @ 100 with the same `T` →
cache ends at 100, and the next bookTicker republishes 100 as `last` with a fresh timestamp.
Do: tie-break on the aggregate trade id when the timestamps are equal (store `(price, ts, id)`).

## F11 — MEDIUM — `_last_trade` grows forever
`binance/ws.py:154, 322`: the cache is cleared only when `stream()` is first called;
`update_subscriptions` never evicts a removed symbol.
Failure scenario: the 15-minute top-200-by-volume refresh churns symbols for weeks; every symbol
ever monitored keeps an entry for the life of the process.
Do: drop the entries for `removed` symbols in `update_subscriptions`. Test it.

## F12 — MEDIUM — the 1024-stream limit is never computed or asserted
`binance/streams.py:48` hardcodes `MAX_SYMBOLS_PER_CONNECTION = 200`; the string `1024` does not
appear anywhere in the package.
Failure scenario: safe today only because 200 × 4 market channels = 800. Adding a sixth market
channel later gives 200 × 6 = 1200 and silently breaks the connection in production, with no test
failing first.
Do: name the limit as a constant, assert it where groups/names are built (raise, don't truncate),
and add a regression test computing streams = symbols × channels for a full group on each route.

## F13 — MEDIUM — `fetch_realized_funding` does not paginate
`binance/rest.py:258-280` issues exactly one request; Binance caps a page at `limit` (max 1000 ≈
333 days of 8 h settlements).
Failure scenario: backfilling a long-lived market from its listing date silently returns only the
first ~333 days after `start`, with no signal that more rows exist and no gap detection on the
funding path — a permanent, invisible hole in `funding_rates`.
Do: loop internally like `fetch_candles` does (advance `startTime` past the last `fundingTime`
until a short page comes back or `end` is reached), respecting the dedicated bucket on every
iteration and guarding against a non-advancing cursor. Test with a paged fake transport.

## F14 — LOW — tests that promise more than they check
- `tests/unit/test_streams.py:140` — the "full replacement" test reuses the same payload and only
  varies `u`. Add a second payload with a level removed/changed and assert the result contains
  only the current payload's levels.
- `tests/unit/test_subscriptions.py:161` — the error-ACK test only asserts the pending entry is
  consumed; extend it to the F6 contract.
- `tests/unit/test_ws_client.py:116` — add the F7 quiet-socket rotation case.

## F15 — LOW — fixture provenance
`testing/fixtures/exchange_info.json` holds 8 entries (`OMGUSDT` SETTLING, `ETHBTC`,
`BTCUSDT_260925`) while `testing/record.py`'s `TRIM_SYMBOLS=5` filter would only keep 5 USDT
perpetuals, so re-running the recorder silently drops the rows three tests depend on.
Do: make `record.py` keep one row per edge-case category (settling / non-USDT quote / quarterly
future), or state in a comment that they were added deliberately and why. They are real recorded
payloads — this is about the refresh procedure, not fake data.

## F16 — LOW — a `live` test that proves data on both routes
`tests/live/test_live_binance.py` only exercises REST. The joint checklist says "an ACK alone does
not prove data was received". Add a `live`-marked, `HUNTER_LIVE_TESTS=1`-gated test (never in CI,
hard timeout ~60 s) that opens the stream for one symbol and asserts a real data payload arrives
on **both** the `/public` route (book or bookTicker) and the `/market` route (trade/kline/mark).

---

## Explicitly NOT to be fixed in this pass (documented M1 limitations)
Do not spend effort on these; the orchestrator has accepted them in writing:
1. Cross-process cooldown / `blocked_until` persisted in Redis, and cross-process reconciliation of
   in-flight reservations (M1 runs one process per IP; M2 gets the atomic Lua version).
2. Connection rotation **without overlap** — the reopen gap stays; F7 is the part being fixed.
3. Reader-failure detection window of ~31 s (worker watchdog contract).
4. `last_data_event_*` advancing on duplicate frames (the accepted-progress gate lives in the
   worker's readiness).
5. `BoundedEventQueue` bounding by item count only (no byte/age bound).

## File-size budget
`ws.py` is at 349/350 lines and F6/F7/F8 all add to it. Extract a module (for example
`binance/connection.py` for the connect/rotate/backoff loop) rather than squeezing lines. Every
file must stay ≤ 350 lines.

## Verification to run and paste in your report
```bash
cd /c/dev/project-hunter
uv run pytest packages/exchange-adapters -q -p no:cacheprovider
HUNTER_LIVE_TESTS=1 uv run pytest packages/exchange-adapters -m live -q -p no:cacheprovider
uv run ruff check packages/exchange-adapters && uv run ruff format --check packages/exchange-adapters
uv run pyright packages/exchange-adapters
uv run python infra/scripts/check_file_size.py
git status --short packages/exchange-adapters
```
Do **not** run `services/market-worker` tests — unstable from concurrent edits, not a criterion.

## Report format
Per finding F1–F16: fixed / not fixed (why), file:line, the test that proves it. Then the pasted
output of every verification command, and the final line count of `ws.py` and any new module.
