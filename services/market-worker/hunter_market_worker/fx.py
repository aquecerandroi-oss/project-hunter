"""FX collector — the producer half of T3.11: ``fx_observations`` for USDTBRL.

The consumer half already exists: ``hunter_core.portfolio.opening.
open_paper_wallet`` (T3.3b) and ``hunter_core.portfolio.ledger.
record_equity_point`` both refuse a rate older than ``FxPolicy.
availability_max_age_s`` (300s) or ``FxPolicy.observation_max_age_s`` (600s),
and ``infra/scripts/open_paper_wallet.py`` fetches one quote by hand for the
one-time opening act. This module is the continuous collector that keeps a
rate that fresh in the table on an ongoing basis, so the wallet's opening is
never blocked on a stale quote and the equity curve is never more than a poll
cycle behind.

Polls ``GET /api/v3/ticker/24hr?symbol=USDTBRL`` (weight 2) roughly every 60s
(± 5s jitter), on **shard 0 only** — one collector per venue, never N
(directive of T3.11a); every other shard, and every shard of a
non-``binance`` exchange code, idles this task forever. The pair, the
endpoint's ``closeTime``-as-``observed_at`` choice and the ``source`` string
are exactly what ``PAPER_FX_POLICY`` (``hunter_core.portfolio.fx_policy``)
already declares — imported, never re-typed, because a source or pair spelled
differently here could never open a wallet ("fonte inválida não abre").

Uses :class:`~hunter_exchanges.binance_spot.http.SpotHttp` directly rather
than :class:`~hunter_exchanges.binance_spot.rest.BinanceSpotRestClient`, for
the reason ``infra/scripts/open_paper_wallet.py`` already gives: the REST
client normalizes the ticker and discards the raw body, and
``fx_observations.raw`` needs the body itself. ``SpotHttp`` still gives the
full contract this task requires: the shared Redis token bucket
(``rl:binance:spot_request_weight``, official weight), the shared IP gate, and
a ``429``/``418`` that raises :class:`~hunter_exchanges.base.RateLimited`
rather than retrying silently (EXCHANGE_INTEGRATION.md §5).

Every write is its own transaction, outside any wallet or equity-curve unit of
work: this module never opens a wallet, never reads or locks
``portfolio_risk_state``, and cannot be a party to the lock ordering
``build_portfolio_state`` documents. An observation outside ``FxPolicy``'s
plausibility band is still persisted — the collector's job is to record what
the exchange printed, unedited; refusing an implausible rate is the
*consumer*'s job (``validate_fx_observation``, blocking-3 of the adversarial
review of ``8a6a69f``) — but it is logged at ``warning`` and counted
separately (``hunter_fx_implausible_total``), never silently.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, cast

from prometheus_client import Counter, Gauge
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.fx import FxObservation
from hunter_core.db.session import role_session
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.logging import get_logger
from hunter_core.observability import registry
from hunter_core.portfolio.attribution import FX_PAIR
from hunter_core.portfolio.fx_policy import PAPER_FX_POLICY
from hunter_exchanges.base import ExchangeUnavailable, MalformedMessage, RateLimited
from hunter_exchanges.binance_spot import normalize
from hunter_exchanges.binance_spot.http import (
    REQUEST_WEIGHT_CAPACITY,
    REQUEST_WEIGHT_PERIOD_S,
    SpotHttp,
)
from hunter_exchanges.binance_spot.identity import EXCHANGE as SPOT_EXCHANGE
from hunter_exchanges.rate_limit import TokenBucketRateLimiter
from hunter_market_worker.heartbeat import safe_record_system_event

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime

__all__ = [
    "FX_SOURCE",
    "FX_SYMBOL",
    "FxCollectorHealth",
    "build_spot_http",
    "collect_once",
    "run_fx_collector",
]

logger = get_logger(__name__)

FX_SOURCE = PAPER_FX_POLICY.source
"""``binance.spot.ticker`` — the wallet's declared source (T3.3's
``FxPolicy``), imported rather than re-typed: a value that drifted from this
constant would write observations ``validate_fx_observation`` never accepts."""

FX_SYMBOL = FX_PAIR
"""``USDTBRL``: both the pair we persist and the Binance spot symbol we poll.
They happen to share a spelling; nothing here assumes a future pair would."""

TICKER_WEIGHT = 2
POLL_INTERVAL_S = 60.0
POLL_JITTER_S = 5.0
BACKOFF_BASE_S = 5.0
BACKOFF_MAX_S = 60.0

Outcome = Literal["ok", "duplicate", "malformed", "rate_limited", "network_error", "error"]
_RETRY_OUTCOMES = frozenset({"rate_limited", "network_error", "error"})


fx_observations_total = Counter(
    "hunter_fx_observations_total",
    "USDTBRL polls, by outcome.",
    ["outcome"],
    registry=registry,
)
fx_implausible_total = Counter(
    "hunter_fx_implausible_total",
    "Observations written outside FxPolicy's plausibility band. Still "
    "persisted — the raw print is the record, never fabricated or clamped.",
    registry=registry,
)
fx_age_seconds = Gauge(
    "hunter_fx_age_seconds",
    "Age, in seconds, of the last successfully polled USDTBRL observation.",
    registry=registry,
)


class FxCollectorHealth:
    """When did this process last successfully reach the exchange?

    Monotonic and in-process, like ``supervision.IngestionHealth``: a
    ``/ready`` status detail must answer with no I/O, so it reads the same
    clock the collector's own loop advances rather than querying Postgres.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last_success: float | None = None

    def record_success(self) -> None:
        self._last_success = self._clock()

    def age_seconds(self) -> float:
        if self._last_success is None:
            return float("inf")
        return self._clock() - self._last_success

    def status(self) -> str:
        """``"unknown"`` before the first success, else ``"ok"``/``"stale"``.

        The threshold is ``FxPolicy.availability_max_age_s`` (300s) — the same
        number the wallet's opening and the equity curve refuse a quote past,
        so this answers exactly what an operator wants to know: would the
        wallet accept the latest rate right now. It is a *status detail*
        (``WorkerRuntime.status_details``), never a readiness check: the
        wallet may fail to open, but the rest of market collection continues,
        so ``/ready`` must not turn red over it.
        """
        if self._last_success is None:
            return "unknown"
        return "stale" if self.age_seconds() > PAPER_FX_POLICY.availability_max_age_s else "ok"


def build_spot_http(redis: redis_asyncio.Redis) -> SpotHttp:
    """A ``SpotHttp`` bound to the shared Redis token bucket and IP gate.

    Mirrors ``config.build_adapter``'s USDS-M construction: a bare
    ``TokenBucketRateLimiter`` built with no ``redis=`` silently falls back to
    a **local** budget, which is exactly the per-process quota T2.9's
    fail-closed contract exists to prevent. The IP gate is left to
    ``SpotHttp``'s own default (a bare ``IpRateGate()``): its setter binds it
    to this limiter's Redis client and exchange the moment it is assigned, so
    a second gate object is still the one shared coordination point.
    """
    limiter = TokenBucketRateLimiter(
        SPOT_EXCHANGE,
        # Same cast as ``config.build_adapter``: the protocol
        # ``TokenBucketRateLimiter`` wants is narrower than what
        # ``redis.asyncio.Redis`` type-checks as, though the real client
        # satisfies it at runtime (``eval`` is what the limiter actually calls).
        redis=cast(Any, redis),
        capacity=REQUEST_WEIGHT_CAPACITY,
        refill_period_s=REQUEST_WEIGHT_PERIOD_S,
    )
    return SpotHttp(rate_limiter=limiter)


async def collect_once(
    http: SpotHttp, session_factory: async_sessionmaker[AsyncSession]
) -> Outcome:
    """One poll: fetch, validate the shape, persist, never fabricate a rate.

    Idempotent by construction: the insert conflicts on
    ``uq_fx_observations_observation`` (``pair``, ``source``, ``observed_at``)
    with ``ON CONFLICT DO NOTHING``, so polling the same closed second twice —
    a retry, two overlapping runs — writes at most one row and reports
    ``"duplicate"`` rather than raising.

    Never raises for a failure this module already has a name for (rate
    limit, transport failure after ``SpotHttp``'s own retries, a malformed
    body): those are reported through the return value so the caller can
    back off. A genuinely unexpected error (e.g. a database outage on the
    insert) still propagates — the caller's own ``try/except`` is what keeps
    that from taking the whole worker down.
    """
    try:
        raw: dict[str, Any] = await http.get(
            "/api/v3/ticker/24hr", params={"symbol": FX_SYMBOL}, weight=TICKER_WEIGHT
        )
    except RateLimited as exc:
        logger.warning("fx_collector_rate_limited", retry_after_s=exc.retry_after_s)
        await safe_record_system_event(
            session_factory,
            "fx_collector_rate_limited",
            f"USDTBRL poll refused by Binance spot: {exc}",
            RiskEventSeverity.WARNING,
        )
        fx_observations_total.labels(outcome="rate_limited").inc()
        return "rate_limited"
    except ExchangeUnavailable as exc:
        logger.warning("fx_collector_unavailable", error=str(exc))
        fx_observations_total.labels(outcome="network_error").inc()
        return "network_error"

    try:
        ticker = normalize.parse_ticker_24h(raw)
    except MalformedMessage as exc:
        logger.error("fx_collector_malformed", error=str(exc))
        fx_observations_total.labels(outcome="malformed").inc()
        return "malformed"

    if not (
        PAPER_FX_POLICY.plausible_rate_min <= ticker.last <= PAPER_FX_POLICY.plausible_rate_max
    ):
        fx_implausible_total.inc()
        logger.warning(
            "fx_observation_implausible",
            pair=FX_SYMBOL,
            rate=str(ticker.last),
            band_min=str(PAPER_FX_POLICY.plausible_rate_min),
            band_max=str(PAPER_FX_POLICY.plausible_rate_max),
        )

    async with role_session(session_factory, db_role="hunter_worker") as session:
        result = await session.execute(
            pg_insert(FxObservation)
            .values(
                id=uuid7(),
                pair=FX_SYMBOL,
                rate=ticker.last,
                source=FX_SOURCE,
                observed_at=ticker.ts,
                available_at=utcnow(),
                raw=raw,
            )
            .on_conflict_do_nothing(index_elements=["pair", "source", "observed_at"])
            .returning(FxObservation.id)
        )
        inserted = result.first() is not None
    outcome: Outcome = "ok" if inserted else "duplicate"
    fx_observations_total.labels(outcome=outcome).inc()
    return outcome


async def run_fx_collector(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    exchange_code: str,
    runtime: WorkerRuntime,
) -> None:
    """Shard 0's continuous USDTBRL poll; every other shard idles forever.

    Reads ``runtime.settings.shard_index`` (``MARKET_SHARD=i/N``,
    ``hunter_core.settings.Settings``) directly — no new setting is declared
    by this task. ``exchange_code`` guards against a future non-``binance``
    market-worker also running this task: the source is bound to Binance
    spot regardless of which perpetual venue this process ingests, so only
    one exchange's shard 0 may ever collect it.
    """
    if exchange_code != SPOT_EXCHANGE or runtime.settings.shard_index != 0:
        logger.info(
            "fx_collector_idle",
            exchange_code=exchange_code,
            shard_index=runtime.settings.shard_index,
        )
        await asyncio.Event().wait()
        return

    http = build_spot_http(redis)
    health = FxCollectorHealth()
    runtime.status_details["fx"] = health.status
    fx_age_seconds.set_function(health.age_seconds)
    backoff_attempt = 0
    try:
        while True:
            try:
                outcome = await collect_once(http, factory)
            except asyncio.CancelledError:
                raise
            except Exception:
                runtime.mark_error()
                logger.exception("fx_collector_unexpected_error")
                fx_observations_total.labels(outcome="error").inc()
                outcome = "error"
            if outcome in _RETRY_OUTCOMES:
                runtime.mark_error()
                delay = min(BACKOFF_MAX_S, BACKOFF_BASE_S * (2**backoff_attempt))
                backoff_attempt += 1
                await asyncio.sleep(delay + random.uniform(0, delay * 0.1))
                continue
            backoff_attempt = 0
            health.record_success()
            await asyncio.sleep(POLL_INTERVAL_S + random.uniform(-POLL_JITTER_S, POLL_JITTER_S))
    finally:
        runtime.status_details.pop("fx", None)
        await http.aclose()
