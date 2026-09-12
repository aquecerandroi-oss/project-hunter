"""``https://swap-api.pump.fun/v2/coins/{mint}/trades`` — the trade tape with a
cursor (``docs/PUMPFUN.md`` §2 route 5).

Measured live on 2026-09-12: ``limit ≤ 100``, newest first, ``pagination
{nextCursor, hasMore, limit}`` with ``nextCursor = "<slotIndexId>-<epoch ms>"``
pointing at the page *before* (older) the one returned; the host answers with
``x-ratelimit-limit: 1000`` per 60 s.

**The real limit is not that header (T4.2f, 12/09 13:36–13:48 UTC, four probes,
115 requests, five 429s —** ``tests/fixtures/pumpfun/t42f_swap_api_ratelimit_probes.json``**).**
Every 429 came from Cloudflare (error 1015, ``server: cloudflare``, ``retry-after:
60``, no ``x-ratelimit-*`` at all) while the backend's own header still said
``remaining ≈ 900``. The rule counts **per IP, about 20 requests per 60 s**,
whatever the mint: cut at the 20th, 20th, 23rd and 24th request of a window at
0,85–6 req/s (only 8 of the 22 fell in the last 10 s, so the window is not 10 s),
at the 28th in a 16 req/s burst (distributed counters), and with 40 distinct
mints at 1,2 req/s at the 24th. A breach costs a **60 s block of every request
from the IP**. So this client spends a :data:`REQUEST_CAPACITY` = **16 / 60 s**
bucket (``rl:pumpfun_swap_api:requests``): the measured 20 minus four of margin
for the edge's approximate counting; :data:`MEASURED_LIMIT` is the ceiling the
constructor refuses to exceed, and a ``429`` is :class:`HttpRateLimited` with
the headers it came with — never a silent retry. T4.2c/T4.2e spent a 900/60 s
bucket eight requests at a time, which is exactly what tripped the rule every
cycle and produced the ``rate_limited`` rows they measured.

What a row does and does not say, and what this client does about it:

- ``program`` names the venue of the fill: ``pump`` is the bonding curve,
  ``pump_amm`` the PumpSwap pool after graduation, ``raydium_cpmm`` another
  launchpad's AMM (all three observed live). Every row is returned with
  ``is_bonding_curve`` so the caller filters by name instead of by guess;
- ``amountSol``/``quoteAmount``: equal and lamport-exact on the ``pump`` rows
  (``0.724716993`` → 724 716 993 lamports); on the ``raydium_cpmm`` rows
  ``amountSol`` is a 28-decimal conversion of a non-SOL quote. So
  ``quote_is_native_sol`` is *both* conditions, and ``sol_lamports`` exists only
  when it holds;
- ``slotIndexId`` begins with the slot (twelve digits, verified against
  ``getTransaction``); the rest is an undocumented ordering key kept raw;
- nothing states finality, an instruction index or the Mayhem attribution, and
  the client invents none of them (``meme_trades.commitment`` became nullable
  in ``0023`` for exactly this producer).
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from urllib.parse import quote

import httpx

from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.board_models import NormalizedSwapTrade
from hunter_exchanges.pumpfun.market_activity import (
    DEFAULT_WINDOWS,
    MAX_ADDRESSES,
    METRICS,
    WINDOW_SECONDS,
    ActivityBatch,
    parse_activity_batch,
    response_stamp,
)
from hunter_exchanges.pumpfun.rate_shared import get_json_with_budget, request_json_with_budget
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

logger = get_logger(__name__)

EXCHANGE = "pumpfun_swap_api"
BASE_URL = "https://swap-api.pump.fun"
REQUEST_BUCKET = "requests"
HEADER_LIMIT = 1000
"""What ``x-ratelimit-limit`` says: the backend's window, never the one that refuses."""
MEASURED_LIMIT = 20
"""Cloudflare's rule, measured (module docstring): ~20 requests per 60 s per IP."""
MEASURED_BLOCK_S = 60.0
"""``retry-after`` of every 429 seen — the cost of one breach."""
REQUEST_CAPACITY = 16
REQUEST_PERIOD_S = 60.0
MAX_PAGE = 100
CURVE_PROGRAM = "pump"
SLOT_DIGITS = 12
LAMPORTS_PER_SOL = Decimal(1_000_000_000)


@dataclass(frozen=True, slots=True)
class TradesPage:
    """One page, newest first, plus what the page could not be turned into."""

    mint: str
    trades: tuple[NormalizedSwapTrade, ...]
    next_cursor: str | None
    has_more: bool
    malformed: int = 0
    received_at: datetime = field(default_factory=utcnow)


class SwapApiClient:
    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        capacity: int = REQUEST_CAPACITY,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not 1 <= capacity <= MEASURED_LIMIT:
            raise ValueError(f"capacity must be 1..{MEASURED_LIMIT} (the measured limit)")
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"Accept": "application/json", "Origin": "https://pump.fun"},
        )
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(
            EXCHANGE, capacity=capacity, refill_period_s=REQUEST_PERIOD_S
        )
        self._max_retries = max_retries
        self._sleep = sleep

    @property
    def rate_limiter(self) -> TokenBucketRateLimiter:
        return self._rate_limiter

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_trades(
        self, mint: str, *, limit: int = MAX_PAGE, cursor: str | None = None
    ) -> TradesPage:
        """One page of the tape; ``cursor`` walks towards older trades."""
        if not 1 <= limit <= MAX_PAGE:
            raise ValueError(f"limit must be 1..{MAX_PAGE}")
        params: dict[str, str | int] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        raw = await get_json_with_budget(
            self._client,
            f"/v2/coins/{quote(mint, safe='')}/trades",
            params=params,
            exchange=EXCHANGE,
            limiter=self._rate_limiter,
            bucket=REQUEST_BUCKET,
            max_retries=self._max_retries,
            sleep=self._sleep,
            rand=random.uniform,
        )
        return parse_trades_page(mint, raw, received_at=utcnow())

    async def market_activity_batch(
        self, mints: Sequence[str], *, windows: Sequence[str] = DEFAULT_WINDOWS
    ) -> ActivityBatch:
        """``POST /v1/coins/market-activity/batch`` (T4.2g, ``market_activity.py``):
        up to :data:`~.market_activity.MAX_ADDRESSES` coins, every metric, the
        windows asked for — **one request of this client's budget**, the same
        Cloudflare rule as the tape. Refuses a batch the validator would refuse
        before spending the request."""
        if not 1 <= len(mints) <= MAX_ADDRESSES:
            raise ValueError(f"mints must be 1..{MAX_ADDRESSES} per request (measured)")
        unknown = [w for w in windows if w not in WINDOW_SECONDS]
        if unknown or not windows:
            raise ValueError(f"windows must be among {sorted(WINDOW_SECONDS)}: {unknown}")
        raw, headers = await request_json_with_budget(
            self._client,
            "POST",
            "/v1/coins/market-activity/batch",
            params=None,
            json_body={
                "addresses": list(mints),
                "intervals": list(windows),
                "metrics": list(METRICS),
            },
            exchange=EXCHANGE,
            limiter=self._rate_limiter,
            bucket=REQUEST_BUCKET,
            max_retries=self._max_retries,
            sleep=self._sleep,
            rand=random.uniform,
        )
        received_at = utcnow()
        return parse_activity_batch(
            raw,
            mints=mints,
            windows=windows,
            observed_at=response_stamp(headers, received_at=received_at),
            received_at=received_at,
        )


def _malformed(text: str) -> MalformedMessage:
    return MalformedMessage(f"swap-api {text}", exchange=EXCHANGE)


def _decimal(value: Any, key: str) -> Decimal:
    """The API sends numbers as decimal **strings**; a float is refused."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise _malformed(f"{key} is not a decimal string: {value!r}")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise _malformed(f"{key} is not decimal: {value!r}") from exc
    if not result.is_finite() or result < 0:
        raise _malformed(f"{key} is negative or not finite: {value!r}")
    return result


def _text(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise _malformed(f"{key} is not text")
    return value


def parse_trade(mint: str, raw: dict[str, Any], *, received_at: datetime) -> NormalizedSwapTrade:
    slot_index_id = _text(raw.get("slotIndexId"), "slotIndexId")
    if len(slot_index_id) < SLOT_DIGITS or not slot_index_id.isdigit():
        raise _malformed(f"slotIndexId is not a digit string: {slot_index_id!r}")
    side = raw.get("type")
    if side not in ("buy", "sell"):
        raise _malformed(f"type is not buy/sell: {side!r}")
    try:
        block_time = ensure_utc(datetime.fromisoformat(_text(raw.get("timestamp"), "timestamp")))
    except ValueError as exc:
        raise _malformed("timestamp is not ISO-8601") from exc
    program = _text(raw.get("program"), "program")
    sol_amount = _decimal(raw.get("amountSol"), "amountSol")
    quote_amount = _decimal(raw.get("quoteAmount"), "quoteAmount")
    lamports = sol_amount * LAMPORTS_PER_SOL
    native = quote_amount == sol_amount and lamports == lamports.to_integral_value()
    token_amount = _decimal(raw.get("baseAmount"), "baseAmount")
    if token_amount == 0:
        raise _malformed("baseAmount is zero")
    marginal = raw.get("priceSol")
    usd = raw.get("amountUsd")
    return NormalizedSwapTrade(
        mint=mint,
        signature=_text(raw.get("tx"), "tx"),
        slot_index_id=slot_index_id,
        slot=int(slot_index_id[:SLOT_DIGITS]),
        trader=_text(raw.get("userAddress"), "userAddress"),
        side=cast(Any, side),
        program=program,
        is_bonding_curve=program == CURVE_PROGRAM,
        quote_is_native_sol=native,
        sol_amount=sol_amount,
        sol_lamports=int(lamports) if native else None,
        token_amount=token_amount,
        price=_decimal(raw.get("fillPriceSol"), "fillPriceSol"),
        marginal_price=None if marginal is None else _decimal(marginal, "priceSol"),
        amount_usd=None if usd is None else _decimal(usd, "amountUsd"),
        observed_at=block_time,
        received_at=received_at,
    )


def parse_trades_page(mint: str, raw: Any, *, received_at: datetime) -> TradesPage:
    """A whole response. A row the parser refuses is counted and skipped so one
    strange row does not lose the other ninety-nine; a body without the
    ``trades`` list is malformed as a whole."""
    if not isinstance(raw, dict):
        raise _malformed("response is not an object")
    payload = cast(dict[str, Any], raw)
    rows = payload.get("trades")
    if not isinstance(rows, list):
        raise _malformed("response has no trades list")
    pagination_raw = payload.get("pagination")
    pagination = cast(dict[str, Any], pagination_raw) if isinstance(pagination_raw, dict) else {}
    cursor = pagination.get("nextCursor")
    trades: list[NormalizedSwapTrade] = []
    malformed = 0
    for row in cast(list[Any], rows):
        if not isinstance(row, dict):
            malformed += 1
            continue
        try:
            trades.append(parse_trade(mint, cast(dict[str, Any], row), received_at=received_at))
        except MalformedMessage as exc:
            malformed += 1
            logger.warning("swap_api_malformed_trade", mint=mint, error=str(exc))
    return TradesPage(
        mint=mint,
        trades=tuple(trades),
        next_cursor=cursor if isinstance(cursor, str) and cursor else None,
        has_more=bool(pagination.get("hasMore")),
        malformed=malformed,
        received_at=received_at,
    )


__all__ = [
    "BASE_URL",
    "CURVE_PROGRAM",
    "HEADER_LIMIT",
    "MAX_PAGE",
    "MEASURED_BLOCK_S",
    "MEASURED_LIMIT",
    "REQUEST_CAPACITY",
    "ActivityBatch",
    "SwapApiClient",
    "TradesPage",
    "parse_trade",
    "parse_trades_page",
]
