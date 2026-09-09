"""Market connectivity: one row per collected exchange, from Redis heartbeats
and Postgres market/gap counts.

Split out of ``services/system_status.py`` in T3.44c, for the 350-line budget
(``infra/scripts/check_file_size.py``) and along the seam the module already
had: ``system_status`` answers *are the workers alive*, this answers *is the
market being collected*. ``system_status`` re-exports :func:`build_market_status`
so ``routers/system.py`` and every existing caller keep their import — a module
split that breaks an import is a refactor that broke something (DATABASE.md
§18.10).

:data:`CLOCK_SKEW_TOLERANCE_S` moved here rather than being copied a third time,
and ``system_status`` imports it back: the dependency runs one way only, so
there is no cycle, and the two views cannot drift on what "too far in the
future" means.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis.exceptions as redis_exceptions

from hunter_api.repositories.markets import MarketRepository
from hunter_api.schemas.system import MarketStatusExchangeOut, MarketStatusOut
from hunter_api.services.market_shards import CollectorView, read_collector
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

CLOCK_SKEW_TOLERANCE_S = 2.0
"""(F3) A ``ts`` more than this far ahead of ``now`` is a skewed producer
clock, not a live heartbeat -- reported ``dead`` regardless of how small the
naive ``now - ts`` looks. Mirrors ``services/markets.py``'s constant of the
same name and rationale; kept as a separate copy since the two modules are
independently owned and neither imports the other's internals.

(G6) Reduced from 5s to 2s, for the same reason ``services/markets_quality
.py`` reduced its copy: the API and every worker that writes a ``ts`` here
run on the same NTP-synced host, so genuine clock drift between them should
be near zero -- 2s is generous headroom for jitter, not for a producer that
has actually stopped. Also now applied to ``build_market_status``'s
``last_event_at`` handling, which previously only clamped the age and never
checked it against this tolerance at all."""


PLANNED_EXCHANGE_STATUS = "planned"
"""(T3.44c) ``exchanges.status`` for a venue catalogued with no collector
deployed — the label ``0016_exchange_status_planned`` added (DATABASE.md §28).

Spelled here rather than imported from ``hunter_core.domain.enums`` for the
reason this module already spells ``CLOCK_SKEW_TOLERANCE_S`` twice: the string
is a wire value this service compares against, and the schema tests are what
keep the database's labels and the domain enum in agreement.
"""


async def build_market_status(session: AsyncSession, redis: redis_asyncio.Redis) -> MarketStatusOut:
    """One row per **collected** ``exchanges`` entry (global, no RLS) — not per
    ``hb:market:*`` key found — so an exchange the worker has never touched
    still appears, reported ``ws_state: "unavailable"``, rather than silently
    missing.

    The exception is a venue whose ``status`` is ``planned``: it is catalogued
    and no collector was ever deployed for it, so it has no feed to be in
    trouble. It is named in ``exchanges_planned`` and kept out of ``exchanges``
    entirely — Redis is never read for it, it never enters the worst-of
    aggregate the topbar reduces (``2 exchanges · UNAVAILABLE`` with one worker
    running, T3.44b) and, crucially, it never counts toward the "every exchange
    failed" test below: with Bybit in that list, a genuine Redis outage on a
    single-collector deployment would have been one failure out of two and would
    have answered ``200`` instead of ``503``.

    (G4) One exchange's own heartbeat hash misbehaving (a lone ``WRONGTYPE``)
    still degrades only that row -- the same per-item isolation
    ``services/markets.py`` applies. But if *every* exchange's read failed,
    that is not "no worker has reported for any exchange yet", it is Redis
    itself being unreachable -- reported wholesale by re-raising
    ``redis.exceptions.RedisError`` (after logging only its ``error_type``
    per exchange, never a key name) so the router can answer an explicit
    ``503`` instead of a ``200`` indistinguishable from a healthy, idle
    cluster.
    """
    repository = MarketRepository(session)
    catalogue = await repository.list_exchanges_with_status()
    exchange_codes = [code for code, status in catalogue if status != PLANNED_EXCHANGE_STATUS]
    planned_codes = [code for code, status in catalogue if status == PLANNED_EXCHANGE_STATUS]
    monitored_counts = await repository.monitored_market_counts()
    gap_counts = await repository.open_gap_counts()

    collectors: list[tuple[str, CollectorView]] = []
    failed_reads = 0
    for code in exchange_codes:
        try:
            # T2.5g: the union of this exchange's shard heartbeats (or the solo
            # key), never a single hash N processes would overwrite.
            view = await read_collector(redis, code, now=utcnow())
        except redis_exceptions.RedisError as exc:
            logger.warning(
                "market_status_redis_error", error_type=type(exc).__name__, exchange=code
            )
            failed_reads += 1
            view = CollectorView(ws_state="unavailable")
        collectors.append((code, view))
    # (G5) captured after every Redis read above, not before the loop --
    # `now` must reflect when the reads actually completed.
    now = utcnow()
    if exchange_codes and failed_reads == len(exchange_codes):
        raise redis_exceptions.RedisError("every exchange heartbeat read failed")

    exchanges: list[MarketStatusExchangeOut] = []
    for code, view in collectors:
        last_event_at = view.last_event_at
        ws_state = view.ws_state
        age_ms: int | None = None
        if last_event_at is not None:
            age_s = (now - last_event_at).total_seconds()
            # (G6) apply the same clock-skew tolerance the component/
            # heartbeat freshness checks already apply: a `last_event_at`
            # further ahead of `now` than `CLOCK_SKEW_TOLERANCE_S` is not
            # evidence of a live feed, however fresh the naive `now - ts`
            # looks -- previously this branch only clamped the age at 0 and
            # left `ws_state` free to still read "connected" off an
            # impossible timestamp. An out-of-tolerance timestamp is treated
            # the same as no timestamp at all: `last_event_at`/`age_ms` come
            # back absent and `ws_state` is forced to "unavailable" rather
            # than trusting a signal that cannot be real.
            if age_s < -CLOCK_SKEW_TOLERANCE_S:
                last_event_at = None
                ws_state = "unavailable"
            else:
                age_ms = max(int(age_s * 1000), 0)
        exchanges.append(
            MarketStatusExchangeOut(
                exchange=code,
                ws_state=ws_state,
                last_event_at=last_event_at,
                last_event_age_ms=age_ms,
                markets_monitored=monitored_counts.get(code, 0),
                open_gaps=gap_counts.get(code, 0),
                reconnects=view.reconnects,
                shards_expected=view.shards_expected,
                shards_reporting=view.shards_reporting,
            )
        )
    return MarketStatusOut(
        exchanges=exchanges,
        # (T3.44c) summed over the venues that are actually collected, not over
        # every key ``monitored_market_counts`` returned: a ``planned`` venue's
        # markets can carry ``is_monitored`` from a catalogue sync and nothing
        # reads them, so counting them would make this header disagree with the
        # sum of the rows below it — which is exactly what the web client
        # computes for itself (``totalMonitoredFrom``).
        markets_monitored_total=sum(monitored_counts.get(code, 0) for code in exchange_codes),
        updated_at=now,
        exchanges_planned=planned_codes,
    )
