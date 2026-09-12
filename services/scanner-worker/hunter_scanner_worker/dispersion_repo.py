"""The three reads the ``dispersion_24h`` producer makes, and the one write.

T3.90. Same contract as ``breadth_repo``/``regime_repo``/``beta_repo`` and,
deliberately, the same clauses written out again rather than shared through a
helper with three parameters: what makes a candle count is a **rule**, and a rule
stated once per query is a rule a reviewer can check against the query that used
it.

- ``is_final`` only. The minute still printing is not evidence; it is what makes a
  fold computed at 12:06:04 identical to the same fold recomputed from history a
  month later;
- ``open_time < cut``, never ``<= now``. A candle whose ``open_time`` is the cut
  closes *after* the cut, so it may not enter — the whole of the anti-look-ahead
  rule, expressed where the rows are chosen;
- the universe is **whatever the series version says it is**, and it arrives as an
  explicit list of market ids rather than as a predicate repeated here
  (:func:`universe_members`, one rule shared with the shadow universe and the
  breadth producer in :mod:`hunter_core.universe`). Spot is out of it by that
  rule: ``dispersion_24h`` is a statement about perpetuals, and a spot listing of
  the same coin would put the same asset in the median twice.

**Two ranges, not one, and not 2 881 index probes.** A reading at minute ``T``
needs exactly two candles per market (``T-1min`` and ``T-24h-1min``), so a pass
over ``N`` due minutes needs two contiguous runs of ``N`` minutes each, a day
apart. Fetching the single span that contains both would read ``1 440 + N``
minutes per market to use ``2N`` of them — 23 056 rows to produce one steady-state
reading over sixteen markets. Fetching each instant by equality would be ``2N``
probes. Two range predicates ``OR``-ed is both: constant SQL text, two index scans,
partition pruning intact, and 32 rows read for the minute that just closed. When a
chunk is a whole day the two runs are adjacent (``T-1441`` … ``T-2``, then
``T-1`` …) and Postgres merges them; nothing about the result changes either way.

Nothing here interprets: :func:`endpoint_closes` returns whatever closes exist and
:func:`hunter_indicators.dispersion.compute_dispersion` is what turns a market
with one of its two closes into a market that is not counted.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.dispersion import MarketDispersion
from hunter_core.domain.enums import Timeframe
from hunter_core.universe import UniverseMember, load_history_universe

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.dispersion import DispersionReading

__all__ = [
    "endpoint_closes",
    "existing_minutes",
    "exchange_id_for",
    "universe_members",
    "write_readings",
]

_EXCHANGE = text("SELECT id FROM exchanges WHERE code = :exchange")

_CLOSES = text(
    "SELECT market_id, open_time, close FROM candles "
    " WHERE timeframe = CAST(:timeframe AS candle_timeframe) AND is_final "
    "   AND market_id = ANY(:market_ids) AND open_time < :cut "
    "   AND ( (open_time >= :old_first AND open_time <= :old_last) "
    "      OR (open_time >= :new_first AND open_time <= :new_last) )"
).bindparams(bindparam("market_ids", type_=ARRAY(PG_UUID(as_uuid=True))))
"""Every final 1m close of the universe at either end of the horizon.

The universe arrives as **one array parameter**, never as an expanding ``IN`` list
of uuids, for ``breadth_repo``'s reason: a statement whose text changes with the
size of the universe is a **new statement** — a new parse and a new plan — every
time a market is listed or delisted. ``= ANY(:market_ids)`` keeps the SQL text
constant for the life of the process *and* lets the caller decide which universe a
version folds.

``open_time < :cut`` is redundant with ``:new_last`` by construction and stated
anyway: it is the anti-look-ahead rule, and a rule the reader can see in the query
is a rule the next edit cannot lose.

It does **not** keep a prepared statement: the session builds its engine with
``statement_cache_size=0`` / ``prepared_statement_cache_size=0``
(``hunter_core.db.session``, DATABASE.md §1), because a server-prepared statement
from one transaction leaks into another caller's under a transaction pooler.
Stable SQL text is the whole of the argument."""

_EXISTING = text(
    "SELECT end_time FROM market_dispersion "
    " WHERE exchange_id = :exchange_id AND dispersion_version = :version "
    "   AND end_time >= :first AND end_time <= :last"
)

_UNIQUE_READING = "uq_market_dispersion_reading"
"""``market_dispersion``'s only index, named as a literal for the reason
``ddl/dispersion.py`` keeps its own copy of the version string: the database's
contract must not follow a later edit to a Python constant, and a worker must not
import the migrations package to read one."""

_INSERT = (
    pg_insert(MarketDispersion)
    .on_conflict_do_nothing(constraint=_UNIQUE_READING)
    .returning(MarketDispersion.id)
)
"""``DO NOTHING ... RETURNING id``, which is the whole idempotency story.

Built from the model rather than as SQL text — unlike every read in this module —
for one reason, and it is T3.88's measurement: SQLAlchemy's *insertmanyvalues* can
only rewrite a Core ``insert()`` over a list of parameter sets into multi-row
``VALUES``, and a backfill that executes one statement per minute spends its whole
life in round trips (measured on ``market_breadth``: 21 rows/s, ~100 min for
ninety days, against 2,2 s per 1 440 rows batched). The clause that matters is
still written out here and nowhere else: ``ON CONFLICT ON CONSTRAINT
uq_market_dispersion_reading DO NOTHING``.

``RETURNING`` is how the caller learns whether the row landed: a conflicted insert
returns no row, so counting rows returned counts rows written — without asking the
driver for a ``rowcount`` whose meaning varies with the dialect.

There is no ``UPDATE`` path here and the worker role holds no ``UPDATE`` grant to
write one with (``0020``)."""


async def exchange_id_for(session: AsyncSession, exchange: str) -> UUID | None:
    """The venue's id, or ``None`` when the code is not in ``exchanges``."""
    return await session.scalar(_EXCHANGE, {"exchange": exchange})


async def universe_members(
    session: AsyncSession,
    *,
    exchange: str,
    min_history_days: int,
    clock: Callable[[], datetime],
) -> tuple[UniverseMember, ...]:
    """The eligible members of the series' universe, **with their symbols**.

    Delegates to :func:`hunter_core.universe.load_history_universe` — the same call
    the shadow universe and the breadth producer make, so "the sixteen" cannot mean
    one thing here and another there. Unlike ``breadth_repo.history_universe_ids``
    this returns the members and not only their ids, because this series has to
    find **one** of them: the reference market, by symbol
    (``DispersionSpec.reference_symbol``). Resolving the reference from the same
    load that defines the universe is what makes "the BTC is in the fold" checkable
    instead of assumed.

    ``clock`` is passed in rather than read here: for a backfill the instant that
    matters is the pass's own cut, not the wall clock of the operator running it.
    """
    universe = await load_history_universe(
        session, min_history_days=min_history_days, exchange=exchange, clock=clock
    )
    return universe.eligible


async def endpoint_closes(
    session: AsyncSession,
    *,
    market_ids: Sequence[UUID],
    old_first: datetime,
    old_last: datetime,
    new_first: datetime,
    new_last: datetime,
    cut: datetime,
) -> dict[UUID, dict[datetime, Decimal]]:
    """``market -> {open_time: close}`` for the candles at either endpoint run."""
    out: dict[UUID, dict[datetime, Decimal]] = {}
    if not market_ids:
        return out
    rows = await session.execute(
        _CLOSES,
        {
            "market_ids": list(market_ids),
            "timeframe": Timeframe.M1.value,
            "old_first": old_first,
            "old_last": old_last,
            "new_first": new_first,
            "new_last": new_last,
            "cut": cut,
        },
    )
    for row in rows:
        out.setdefault(row.market_id, {})[row.open_time] = row.close
    return out


async def existing_minutes(
    session: AsyncSession,
    *,
    exchange_id: UUID,
    version: str,
    first: datetime,
    last: datetime,
) -> set[datetime]:
    """The minutes of ``[first, last]`` that already have a row."""
    rows = await session.execute(
        _EXISTING,
        {"exchange_id": exchange_id, "version": version, "first": first, "last": last},
    )
    return {row.end_time.replace(tzinfo=row.end_time.tzinfo or UTC) for row in rows}


async def write_readings(
    session: AsyncSession,
    readings: Sequence[DispersionReading],
    *,
    exchange_id: UUID,
    version: str,
    inputs: str,
    ids: Sequence[UUID],
) -> int:
    """Insert the readings that are not there yet; return how many landed.

    ``ids`` is supplied by the caller rather than generated here so that a dry-run
    can build the very rows it would write and print them without this module ever
    being asked to be "almost" a writer.

    One statement per batch, not per row (T3.88's fix, applied from the start).
    """
    if not readings:
        return 0
    inputs_body = cast("dict[str, Any]", json.loads(inputs))
    payload = [
        {
            "id": row_id,
            "exchange_id": exchange_id,
            "end_time": reading.end_time,
            "dispersion_version": version,
            "horizon_minutes": reading.horizon_minutes,
            "universe_size": reading.universe_size,
            "covered": reading.covered,
            "alts_covered": reading.alts_covered,
            "alts_below_btc": reading.alts_below_btc,
            "btc_r24h": reading.btc_r24h,
            "median_alt_r24h": reading.median_alt_r24h,
            "dispersion": reading.dispersion,
            "share_below_btc": reading.share_below_btc,
            "coverage": reading.coverage,
            "usable": reading.usable,
            "reason": reading.reason,
            "inputs": inputs_body,
        }
        for row_id, reading in zip(ids, readings, strict=True)
    ]
    landed = await session.execute(_INSERT, payload)
    return len(landed.scalars().all())
