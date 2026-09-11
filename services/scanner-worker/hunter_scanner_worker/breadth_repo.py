"""The three reads the ``breadth_5m`` producer makes, and the one write.

T3.77. Same contract as ``regime_repo``/``beta_repo`` and, deliberately, the same
clauses written out again rather than shared through a helper with three
parameters: what makes a minute count is a **rule**, and a rule stated once per
query is a rule a reviewer can check against the query that used it.

- ``is_final`` only. The minute still printing is not evidence; it is what makes
  a fold computed at 12:06:04 identical to the same fold recomputed from history
  a month later;
- ``open_time < cut``, never ``<= now``. A candle whose ``open_time`` is the cut
  closes *after* the cut, so it may not enter — the whole of the anti-look-ahead
  rule, expressed where the rows are chosen;
- the universe is **whatever the series version says it is**, and since T3.88 it
  arrives as an explicit list of market ids rather than as a predicate repeated
  here: ``breadth_v1`` folds every monitored active perpetual
  (:func:`monitored_universe`) and ``breadth_v2`` folds the ones with 90 days of
  1m history (:func:`history_universe_ids`, one rule shared with the shadow
  universe in :mod:`hunter_core.universe`). Spot is out of both:
  ``breadth_5m`` is a statement about perpetuals (D-P9 §4 counted 200 of them)
  and a spot listing of the same coin would double-count it.

Nothing here interprets: :func:`window_closes` returns whatever closes exist and
:func:`hunter_indicators.breadth.compute_breadth` is what turns a market with
five of six minutes into a market that is not counted.
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

from hunter_core.db.models.breadth import MarketBreadth
from hunter_core.domain.enums import Timeframe
from hunter_core.universe import load_history_universe

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.breadth import BreadthReading

__all__ = [
    "existing_minutes",
    "exchange_id_for",
    "history_universe_ids",
    "monitored_universe",
    "window_closes",
    "write_readings",
]

_UNIVERSE = text(
    "SELECT m.id FROM markets m JOIN exchanges e ON e.id = m.exchange_id "
    " WHERE e.code = :exchange AND m.is_monitored AND m.status = 'active' "
    "   AND m.market_type = 'perpetual' ORDER BY m.symbol"
)

_EXCHANGE = text("SELECT id FROM exchanges WHERE code = :exchange")

_CLOSES = text(
    "SELECT market_id, open_time, close FROM candles "
    " WHERE timeframe = CAST(:timeframe AS candle_timeframe) AND is_final "
    "   AND open_time >= :first_minute AND open_time < :cut "
    "   AND market_id = ANY(:market_ids)"
).bindparams(bindparam("market_ids", type_=ARRAY(PG_UUID(as_uuid=True))))
"""Every final 1m close of the universe inside ``[first_minute, cut)``.

The universe arrives as **one array parameter**, never as an expanding ``IN``
list of 200 uuids, for the reason the sub-select that stood here until T3.88
existed: a pass folds hundreds of minutes at once, and a statement whose text
changes with the size of the universe is a **new statement** — a new parse and a
new plan — every time a market is listed or delisted. ``= ANY(:market_ids)``
keeps the SQL text constant for the life of the process *and* lets the caller
decide which universe a version folds (T3.88: ``breadth_v1`` hands it every
monitored active perpetual, which is exactly the set the old sub-select
selected, so a re-folded v1 minute is the same number it was; ``breadth_v2``
hands it the sixteen with 90 days of history).

It does **not** keep a prepared statement, and this docstring said it did until
T3.77c. The session builds its engine with ``statement_cache_size=0`` and
``prepared_statement_cache_size=0`` (``hunter_core.db.session``, DATABASE.md §1)
because a server-prepared statement from one transaction leaks into another
caller's transaction under a transaction pooler; nothing here is ever prepared.
Stable SQL text is the whole of the argument.
"""

_EXISTING = text(
    "SELECT end_time FROM market_breadth "
    " WHERE exchange_id = :exchange_id AND breadth_version = :version "
    "   AND window_minutes = :window AND end_time >= :first AND end_time <= :last"
)

_UNIQUE_READING = "uq_market_breadth_reading"
"""``market_breadth``'s only index, named as a literal for the reason
``ddl/breadth.py`` keeps its own copy of the version string: the database's
contract must not follow a later edit to a Python constant, and a worker must
not import the migrations package to read one."""

_INSERT = (
    pg_insert(MarketBreadth)
    .on_conflict_do_nothing(constraint=_UNIQUE_READING)
    .returning(MarketBreadth.id)
)
"""``DO NOTHING ... RETURNING id``, which is the whole idempotency story.

Built from the model rather than as SQL text — unlike every read in this module —
for one reason: SQLAlchemy's *insertmanyvalues* can only rewrite a Core
``insert()`` over a list of parameter sets into multi-row ``VALUES``, and a
backfill that executes one statement per minute spends its whole life in round
trips (measured: 21 rows/s, ~100 min for ninety days). The clause that matters is
still written out here and nowhere else: ``ON CONFLICT ON CONSTRAINT
uq_market_breadth_reading DO NOTHING``.

``RETURNING`` is how the caller learns whether the row landed: a conflicted
insert returns no row, so counting rows returned counts rows written — without
asking the driver for a ``rowcount`` whose meaning varies with the dialect.

A reading is a fold over candles that are already ``is_final``; a second pass
over the same minute either finds the same candles or finds candles a backfill
added — and in the second case the honest answer is a **new**
``breadth_version``, not a silent rewrite of a minute a decision may already have
been gated by. There is no ``UPDATE`` path here and the worker role holds no
``UPDATE`` grant to write one with (``0019``).
"""


async def exchange_id_for(session: AsyncSession, exchange: str) -> UUID | None:
    """The venue's id, or ``None`` when the code is not in ``exchanges``."""
    return await session.scalar(_EXCHANGE, {"exchange": exchange})


async def monitored_universe(session: AsyncSession, exchange: str) -> list[UUID]:
    """``breadth_v1``'s universe: every monitored active perpetual, by symbol."""
    rows = await session.execute(_UNIVERSE, {"exchange": exchange})
    return [row.id for row in rows]


async def history_universe_ids(
    session: AsyncSession,
    *,
    exchange: str,
    min_history_days: int,
    clock: Callable[[], datetime],
) -> list[UUID]:
    """``breadth_v2``'s universe: the same set, restricted to the markets whose
    1m history reaches ``min_history_days`` days before ``clock()``.

    Delegates to :func:`hunter_core.universe.load_history_universe` — the same
    call the shadow universe makes, so "the sixteen" cannot mean one thing in the
    scanner and another in the strategy worker. ``clock`` is passed in rather than
    read here: for a backfill the instant that matters is the fold's cut, not the
    wall clock of the operator running it.
    """
    universe = await load_history_universe(
        session, min_history_days=min_history_days, exchange=exchange, clock=clock
    )
    return list(universe.eligible_ids)


async def window_closes(
    session: AsyncSession,
    *,
    market_ids: Sequence[UUID],
    first_minute: datetime,
    cut: datetime,
) -> dict[UUID, dict[datetime, Decimal]]:
    """``market -> {open_time: close}`` for every final 1m candle in the window."""
    out: dict[UUID, dict[datetime, Decimal]] = {}
    if not market_ids:
        return out
    rows = await session.execute(
        _CLOSES,
        {
            "market_ids": list(market_ids),
            "timeframe": Timeframe.M1.value,
            "first_minute": first_minute,
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
    window: int,
    first: datetime,
    last: datetime,
) -> set[datetime]:
    """The minutes of ``[first, last]`` that already have a row."""
    rows = await session.execute(
        _EXISTING,
        {
            "exchange_id": exchange_id,
            "version": version,
            "window": window,
            "first": first,
            "last": last,
        },
    )
    return {row.end_time.replace(tzinfo=row.end_time.tzinfo or UTC) for row in rows}


async def write_readings(
    session: AsyncSession,
    readings: Sequence[BreadthReading],
    *,
    exchange_id: UUID,
    version: str,
    inputs: str,
    ids: Sequence[UUID],
) -> int:
    """Insert the readings that are not there yet; return how many landed.

    ``ids`` is supplied by the caller rather than generated here so that a
    dry-run can build the very rows it would write and print them without this
    module ever being asked to be "almost" a writer.

    **One statement per batch, not per row (T3.88).** Until this task the loop
    executed :data:`_INSERT` once per reading, which is invisible at one row per
    minute and was measured at **21 rows/s** for a backfill — 129 600 minutes
    would have taken ~100 min of round trips
    (``infra/scripts/tests/test_backfill_breadth_plan.py``). SQLAlchemy's
    *insertmanyvalues* rewrites one ``insert().returning()`` over a list of
    parameter sets into multi-row ``VALUES`` statements, so the semantics are
    unchanged — same ``ON CONFLICT DO NOTHING`` on the same constraint, same
    ``RETURNING id`` as the count of rows that actually landed — and the cost
    stops being a round trip per minute. Nothing about idempotency moves: a
    conflicted row returns nothing and is not counted, exactly as before.
    """
    if not readings:
        return 0
    inputs_body = cast("dict[str, Any]", json.loads(inputs))
    payload = [
        {
            "id": row_id,
            "exchange_id": exchange_id,
            "end_time": reading.end_time,
            "window_minutes": reading.window_minutes,
            "breadth_version": version,
            "universe_size": reading.universe_size,
            "covered": reading.covered,
            "falling": reading.falling,
            "value": reading.value,
            "coverage": reading.coverage,
            "usable": reading.usable,
            "reason": reading.reason,
            "inputs": inputs_body,
        }
        for row_id, reading in zip(ids, readings, strict=True)
    ]
    landed = await session.execute(_INSERT, payload)
    return len(landed.scalars().all())
