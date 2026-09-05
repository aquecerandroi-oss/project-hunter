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
