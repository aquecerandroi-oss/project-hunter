# Task T1.1 — Normalized market domain types (PROJECT HUNTER, Milestone 1)

You are implementing ONE task in an existing monorepo. Read `CLAUDE.md` first (hard rules) and `docs/EXCHANGE_INTEGRATION.md` §2–§3 (the exact model list), `docs/plans/M1.md` (T1.1 row). Do NOT commit. Do NOT touch any file other than the two listed below. Do NOT read `.env`.

## Files you may create/modify
- `packages/core/hunter_core/domain/market.py` (new, ≤ 350 lines)
- `packages/core/tests/unit/test_domain_market.py` (new)

## What to build (`hunter_core.domain.market`)
Pydantic v2 models (`frozen=True`, `extra="forbid"`), all prices/quantities as `decimal.Decimal`, all datetimes timezone-aware UTC (validate: reject naive datetimes). Reuse existing enums from `hunter_core.domain.enums`: `MarketType` (`spot|perpetual`), `MarketStatus` (`active|suspended|delisted`), `Timeframe` (`1m|5m|15m|1h|4h|1d`), `OrderSide` (`buy|sell`). Reuse `utcnow` from `hunter_core.domain.types`.

Models (fields exactly as `docs/EXCHANGE_INTEGRATION.md` §3, plus `received_at: datetime` defaulting to `utcnow()` on every event model):
- `NormalizedMarket`: exchange, symbol, market_type, base, quote, status, tick_size, step_size, min_notional, contract_size (Decimal | None), max_leverage (int | None), metadata (dict, default empty).
- `NormalizedTicker`: exchange, symbol, ts, last, bid, ask, bid_qty, ask_qty, volume_24h, quote_volume_24h, high_24h, low_24h, change_24h_pct (Decimals; bid/ask etc. may be None). Computed property `spread_pct` = (ask - bid) / mid * 100 when both present else None.
- `NormalizedTrade`: exchange, symbol, ts, trade_id (str), price, qty, side (OrderSide, taker side), is_block (bool, default False).
- `BookLevel` (price, qty) and `NormalizedOrderBook`: exchange, symbol, ts, bids (list[BookLevel] sorted desc by price), asks (sorted asc), sequence (int | None), is_snapshot (bool). Validators enforce the sort order and non-negative qty. Computed: `best_bid`, `best_ask`, `mid`, `spread_pct`, `imbalance(depth: int) -> Decimal | None` = (sum bid qty − sum ask qty) / (sum bid qty + sum ask qty) over the top `depth` levels.
- `NormalizedCandle`: exchange, symbol, timeframe, open_time, close_time, open, high, low, close, volume, quote_volume (None ok), trade_count (int | None), taker_buy_volume (None ok), is_final (bool). Validators: high ≥ max(open, close), low ≤ min(open, close), close_time > open_time, open_time aligned to the timeframe (see helpers).
- `NormalizedFunding`: exchange, symbol, ts, funding_rate, next_funding_time (datetime | None), mark_price, index_price (None ok).
- `NormalizedOpenInterest`: exchange, symbol, ts, open_interest, open_interest_value (None ok).
- `NormalizedLiquidation`: exchange, symbol, ts, side, qty, price, notional (None ok → computed qty*price if None).
- `NormalizedEvent = NormalizedTicker | NormalizedTrade | NormalizedOrderBook | NormalizedCandle | NormalizedFunding | NormalizedOpenInterest | NormalizedLiquidation` plus a `kind` discriminator: give each event model a `Literal` field `kind` (`"ticker" | "trade" | "book" | "candle" | "funding" | "open_interest" | "liquidation"`) with a fixed default so `TypeAdapter(NormalizedEvent)` can parse a dict back into the right class.
- `DataQuality` StrEnum: `ok`, `stale`, `degraded`, `unavailable`.

Helpers (pure functions, unit-tested):
- `timeframe_seconds(tf: Timeframe) -> int`
- `align_open_time(ts: datetime, tf: Timeframe) -> datetime` (floor to the timeframe boundary, UTC)
- `close_time_for(open_time: datetime, tf: Timeframe) -> datetime` (open_time + timeframe, exclusive end)
- `is_aligned(ts: datetime, tf: Timeframe) -> bool`
- `data_quality(last_event_at: datetime | None, *, now: datetime, stale_after_s: int, has_open_gap: bool) -> DataQuality` (None → unavailable; gap → degraded; age > stale_after_s → stale; else ok)
- `to_wire(model) -> dict` and `from_wire(cls, data)` using `model_dump(mode="json")` so Decimals become strings and datetimes ISO 8601; round trip must be lossless (test it with Decimal("0.00000001") and Decimal("123456789.123456789")).

## Tests (`test_domain_market.py`, pytest, marker `@pytest.mark.unit` like the neighbours in `packages/core/tests/unit/`)
Cover: every model constructs from valid data; naive datetime rejected; negative qty rejected; book sort order enforced; imbalance math (e.g. bids 3+2, asks 1+1 → 3/7); candle OHLC invariants and alignment (open_time 12:00:30 with 1m → rejected; 12:00:00 ok); `align_open_time`/`close_time_for` for 1m, 15m, 1h, 1d; `data_quality` for the four outcomes; wire round trip for each model; `TypeAdapter(NormalizedEvent)` discriminates by `kind`; `spread_pct` when bid or ask missing → None. Use `hypothesis` (already a dev dependency) for at least one property (alignment idempotence: align(align(x)) == align(x)).

## Verification you must run and paste in your report
```
uv run pytest packages/core/tests/unit/test_domain_market.py -q
uv run ruff check packages/core && uv run ruff format --check packages/core
uv run pyright packages/core/hunter_core/domain/market.py packages/core/tests/unit/test_domain_market.py
uv run python infra/scripts/check_file_size.py
```
If any command fails, fix and re-run. Report: STATUS (DONE/BLOCKED), files created, real output of each command, anything you could not do.
