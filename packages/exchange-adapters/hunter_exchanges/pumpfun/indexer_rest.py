"""``https://advanced-indexer.pump.fun`` over HTTP — the board twin and the
rug-risk read (``docs/PUMPFUN.md`` §3.1).

- ``GET /boards/{board}?offset&limit`` answers with the **same shape as a WS
  snapshot** (``{board, version, serverTs, entries[]}``, measured live on
  2026-09-12: ``tests/fixtures/pumpfun/indexer_boards_new_raw.json``) — the
  fallback when the socket is down, parsed by the same ``parse_entry``;
- ``GET /in-memory-coin/{mint}`` answers 65 undocumented fields
  (``indexer_in_memory_coin_raw.json``), kept raw next to the handful whose
  names state their meaning.

No rate-limit header was ever observed on this host (T4.0c: "sem cabeçalho
x-ratelimit"), and an absence of headers is not "unlimited": this client spends
a declared **60 requests / 60 s** bucket (``rl:pumpfun_indexer:requests``), the
same conservative figure the site's own ``/coins*`` group enforces. A
``429``/``418`` is :class:`RateLimited`, never a silent retry loop.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from urllib.parse import quote

import httpx

from hunter_core.domain.types import utcnow
from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, MalformedMessage, RateLimited
from hunter_exchanges.pumpfun.board_models import (
    BOARDS,
    BOARDS_REST_SOURCE,
    NormalizedBoardEntry,
    NormalizedRiskSnapshot,
)
from hunter_exchanges.pumpfun.rate_shared import get_json_with_budget
from hunter_exchanges.pumpfun.trenches_state import parse_entry
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

EXCHANGE = "pumpfun_indexer"
BASE_URL = "https://advanced-indexer.pump.fun"
REQUEST_BUCKET = "requests"
REQUEST_CAPACITY = 60
REQUEST_PERIOD_S = 60.0
_HUNDRED = Decimal(100)


class AdvancedIndexerClient:
    """Rate-limited GETs against the site's indexer; no key, no cookie."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"Accept": "application/json", "Origin": "https://pump.fun"},
        )
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(
            EXCHANGE, capacity=REQUEST_CAPACITY, refill_period_s=REQUEST_PERIOD_S
        )
        self._max_retries = max_retries
        self._sleep = sleep

    @property
    def rate_limiter(self) -> TokenBucketRateLimiter:
        return self._rate_limiter

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict[str, str | int] | None = None) -> Any:
        return await get_json_with_budget(
            self._client,
            path,
            params=params,
            exchange=EXCHANGE,
            limiter=self._rate_limiter,
            bucket=REQUEST_BUCKET,
            max_retries=self._max_retries,
            sleep=self._sleep,
            rand=random.uniform,
        )

    async def get_board(
        self, board: str, *, limit: int = 50, offset: int = 0
    ) -> list[NormalizedBoardEntry]:
        """The board as the HTTP twin lists it right now, in board order."""
        if board not in BOARDS:
            raise ValueError(f"unknown board {board!r}; boards are {BOARDS}")
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1..100 and offset >= 0")
        raw = await self._get(f"/boards/{board}", {"offset": offset, "limit": limit})
        if not isinstance(raw, dict):
            raise MalformedMessage("board must be an object", exchange=EXCHANGE)
        payload = cast(dict[str, Any], raw)
        entries, version, ts = (
            payload.get("entries"),
            payload.get("version"),
            payload.get("serverTs"),
        )
        if (
            not isinstance(entries, list)
            or not isinstance(version, int)
            or not isinstance(ts, int)
            or isinstance(version, bool)
            or isinstance(ts, bool)
        ):
            raise MalformedMessage("board fields have an unexpected shape", exchange=EXCHANGE)
        observed_at = datetime.fromtimestamp(ts / 1000, tz=UTC)
        received_at = utcnow()
        out: list[NormalizedBoardEntry] = []
        for index, item in enumerate(cast(list[Any], entries)):
            if not isinstance(item, dict):
                raise MalformedMessage("board entry is not an object", exchange=EXCHANGE)
            out.append(
                parse_entry(
                    cast(dict[str, Any], item),
                    board=board,
                    position=offset + index,
                    version=version,
                    observed_at=observed_at,
                    received_at=received_at,
                    source=BOARDS_REST_SOURCE,
                )
            )
        return out

    async def get_risk_snapshot(self, mint: str) -> NormalizedRiskSnapshot:
        raw = await self._get(f"/in-memory-coin/{quote(mint, safe='')}")
        if not isinstance(raw, dict):
            raise MalformedMessage("in-memory-coin must be an object", exchange=EXCHANGE)
        payload = cast(dict[str, Any], raw)
        if payload.get("mint") != mint:
            raise MalformedMessage("in-memory-coin returned a different mint", exchange=EXCHANGE)
        return parse_risk_snapshot(payload, received_at=utcnow())


def _opt_int(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise MalformedMessage(f"in-memory-coin {key} is not an integer", exchange=EXCHANGE)
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise MalformedMessage(f"in-memory-coin {key} is not an integer", exchange=EXCHANGE)
        return int(value)
    return value


def _opt_fraction(value: Any, key: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise MalformedMessage(f"in-memory-coin {key} is not a number", exchange=EXCHANGE)
    return Decimal(value) / _HUNDRED


def _opt_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def parse_risk_snapshot(
    payload: dict[str, Any], *, received_at: datetime
) -> NormalizedRiskSnapshot:
    """65 raw fields -> the labelled object plus the few extracted columns.
    ``observed_at`` is ``received_at``: the response states no instant of its
    own (``lastRecommendedAt`` is about recommendation, not the numbers)."""
    graduated = _opt_int(payload.get("graduationDate"), "graduationDate")
    progress = payload.get("progress")
    return NormalizedRiskSnapshot(
        mint=str(payload["mint"]),
        program=_opt_text(payload.get("program")),
        platform=_opt_text(payload.get("platform")),
        quote_mint=_opt_text(payload.get("quoteMint")),
        quote_asset=_opt_text(payload.get("pair")),
        holders=_opt_int(payload.get("numHolders"), "numHolders"),
        top10_share=_opt_fraction(payload.get("top10HoldersPercent"), "top10HoldersPercent"),
        dev_share=_opt_fraction(payload.get("devHoldingsPercent"), "devHoldingsPercent"),
        snipers=_opt_int(payload.get("sniperCount"), "sniperCount"),
        sniper_share=_opt_fraction(payload.get("snipersOwnedPercent"), "snipersOwnedPercent"),
        bundled_share=_opt_fraction(
            payload.get("bundlerOwnedPercentageV2"), "bundlerOwnedPercentageV2"
        ),
        progress_pct=None
        if progress is None or isinstance(progress, bool)
        else Decimal(progress)
        if isinstance(progress, (int, Decimal))
        else None,
        graduated_at=None if not graduated else datetime.fromtimestamp(graduated / 1000, tz=UTC),
        is_mayhem=payload.get("isMayhemMode")
        if isinstance(payload.get("isMayhemMode"), bool)
        else None,
        mayhem_state=_opt_text(payload.get("mayhemState")),
        raw=json.loads(json.dumps(payload, default=str)),
        observed_at=received_at,
        received_at=received_at,
    )


__all__ = [
    "BASE_URL",
    "REQUEST_CAPACITY",
    "AdvancedIndexerClient",
    "ExchangeError",
    "ExchangeUnavailable",
    "RateLimited",
    "parse_risk_snapshot",
]
