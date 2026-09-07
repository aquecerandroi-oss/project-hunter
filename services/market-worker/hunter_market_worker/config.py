"""Worker configuration: which exchange to run, and how to build its adapter.

docs/plans/M1.md T1.3: the exchange code comes from config (default
``binance``); the concrete adapter is built by a factory so ``main.py`` and
tests never import a concrete ``hunter_exchanges`` submodule directly. Tests
use ``services/market-worker/tests/fakes.FakeAdapter`` instead of any of
this.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_core.settings import Settings
    from hunter_exchanges.base import ExchangeAdapter

from hunter_core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_EXCHANGE_CODE = "binance"
_SUPPORTED_CODES = frozenset({"binance"})


class UnsupportedExchangeError(RuntimeError):
    """Raised by :func:`build_adapter` when ``code`` has no known adapter.

    Covers both an unknown code and a known code whose package
    (``hunter_exchanges.binance``, developed concurrently as T1.2) is not
    importable yet — either way there is no data source to run, so the
    caller must treat this as a startup failure, not a soft-fail.
    """


def exchange_code() -> str:
    """Which exchange this worker instance ingests (``MARKET_EXCHANGE_CODE``, default ``binance``)."""
    return os.environ.get("MARKET_EXCHANGE_CODE", DEFAULT_EXCHANGE_CODE).strip().lower()


def build_adapter(code: str, settings: Settings, redis: redis_asyncio.Redis) -> ExchangeAdapter:
    """Construct the concrete :class:`~hunter_exchanges.base.ExchangeAdapter` for ``code``.

    Imports ``hunter_exchanges.binance`` lazily so this module — and every
    caller that only needs the Protocol — can be imported before that
    package exists (T1.2 lands concurrently). Raises
    :class:`UnsupportedExchangeError` on an unknown code or a failed import;
    ``main.py`` logs it and the process exits non-zero rather than running
    with no data source.
    """
    if code not in _SUPPORTED_CODES:
        logger.error("market_adapter_unsupported", exchange=code)
        raise UnsupportedExchangeError(f"no adapter registered for exchange code {code!r}")
    try:
        from hunter_exchanges.binance import BinanceAdapter
        from hunter_exchanges.binance.rest import BinanceRestClient
        from hunter_exchanges.rate_limit import TokenBucketRateLimiter
    except ImportError as exc:
        logger.error("market_adapter_missing", exchange=code)
        raise UnsupportedExchangeError(
            f"hunter_exchanges.binance is not importable yet: {exc}"
        ) from exc
    # The rate limiter is handed a Redis client so `rl:binance:{bucket}` is a
    # real distributed token bucket (EXCHANGE_INTEGRATION.md §5) instead of
    # per-process local buckets; `settings` is accepted for parity with the
    # brief's factory signature and future use (e.g. BINANCE_API_KEY to
    # elevate public-data rate limits) even though it is unused today.
    del settings
    rate_limiter = TokenBucketRateLimiter(code, redis=cast(Any, redis))
    rest = BinanceRestClient(rate_limiter=rate_limiter)
    return BinanceAdapter(rest=rest)


def build_spot_adapter(
    code: str, settings: Settings, redis: redis_asyncio.Redis
) -> ExchangeAdapter:
    """The SPOT adapter of the same venue (T3.0c) — a *second* adapter, never a
    mode of the first.

    Same ``code`` (one ``exchanges`` row, one IP, one 429/418 surface,
    ``binance_spot/identity.py``) and a different ``market_type``. What it does
    **not** share is the REST budget: spot is 6000 weight/min on ``/api/v3``
    and USDS-M is 2400/min on ``/fapi``, two independent quotas, so the client
    builds its own bucket (``rl:binance:spot_request_weight``). Pointing both at
    one bucket key with two capacities would corrupt the accounting of both
    (T3.0a §3).
    """
    if code not in _SUPPORTED_CODES:
        logger.error("market_spot_adapter_unsupported", exchange=code)
        raise UnsupportedExchangeError(f"no spot adapter registered for exchange code {code!r}")
    try:
        from hunter_exchanges.binance_spot import BinanceSpotAdapter
        from hunter_exchanges.binance_spot.http import (
            REQUEST_WEIGHT_CAPACITY,
            REQUEST_WEIGHT_PERIOD_S,
        )
        from hunter_exchanges.binance_spot.rest import BinanceSpotRestClient
        from hunter_exchanges.rate_limit import TokenBucketRateLimiter
    except ImportError as exc:
        logger.error("market_spot_adapter_missing", exchange=code)
        raise UnsupportedExchangeError(
            f"hunter_exchanges.binance_spot is not importable: {exc}"
        ) from exc
    del settings
    # Redis explicitly, never the client's own default: without it the limiter
    # falls back to a *per-process* bucket, and N processes with a local budget
    # each add up to N quotas against one shared exchange quota — the fail-closed
    # rule of PIPELINE.md §1.7, whose price for getting it wrong is an IP ban.
    rate_limiter = TokenBucketRateLimiter(
        code,
        redis=cast(Any, redis),
        capacity=REQUEST_WEIGHT_CAPACITY,
        refill_period_s=REQUEST_WEIGHT_PERIOD_S,
    )
    return BinanceSpotAdapter(rest=BinanceSpotRestClient(rate_limiter=rate_limiter))
