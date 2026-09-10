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
- the universe is ``markets.is_monitored`` **and** ``status = 'active'`` **and**
  ``market_type = 'perpetual'``, which is exactly ``registry.load_universe``'s
  set. Spot is out: ``breadth_5m`` is a statement about perpetuals (D-P9 §4
  counted 200 of them) and a spot listing of the same coin would double-count it.

Nothing here interprets: :func:`window_closes` returns whatever closes exist and
:func:`hunter_indicators.breadth.compute_breadth` is what turns a market with
five of six minutes into a market that is not counted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.domain.enums import Timeframe

if TYPE_CHECKING:
    from collections.abc import Sequence
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.breadth import BreadthReading

__all__ = [
    "existing_minutes",
    "exchange_id_for",
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
    "   AND market_id IN (SELECT m.id FROM markets m JOIN exchanges e ON e.id = m.exchange_id "
    "                      WHERE e.code = :exchange AND m.is_monitored "
    "                        AND m.status = 'active' AND m.market_type = 'perpetual')"
)
"""Every final 1m close of the universe inside ``[first_minute, cut)``.

The universe is a sub-select rather than an expanding ``IN`` list of 200 uuids
for one reason worth stating: a pass folds hundreds of minutes at once, and a
statement whose text changes with the size of the universe is a **new statement**
— a new parse and a new plan — every time a market is listed or delisted. The
sub-select keeps the SQL text constant for the life of the process, so the same
text is reused for every minute of a 90-day backfill.

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

_INSERT = text(
    "INSERT INTO market_breadth (id, exchange_id, end_time, window_minutes, breadth_version, "
    "  universe_size, covered, falling, value, coverage, usable, reason, inputs) "
    "VALUES (:id, :exchange_id, :end_time, :window, :version, :universe_size, :covered, "
    "  :falling, :value, :coverage, :usable, :reason, CAST(:inputs AS jsonb)) "
    "ON CONFLICT ON CONSTRAINT uq_market_breadth_reading DO NOTHING RETURNING id"
)
"""``DO NOTHING ... RETURNING id``, which is the whole idempotency story.

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
    """The market ids ``breadth_5m`` is measured over, ordered by symbol."""
    rows = await session.execute(_UNIVERSE, {"exchange": exchange})
    return [row.id for row in rows]


async def window_closes(
    session: AsyncSession, *, exchange: str, first_minute: datetime, cut: datetime
) -> dict[UUID, dict[datetime, Decimal]]:
    """``market -> {open_time: close}`` for every final 1m candle in the window."""
    out: dict[UUID, dict[datetime, Decimal]] = {}
    rows = await session.execute(
        _CLOSES,
        {
            "exchange": exchange,
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
    """
    if not readings:
        return 0
    written = 0
    for row_id, reading in zip(ids, readings, strict=True):
        landed = await session.execute(
            _INSERT,
            {
                "id": row_id,
                "exchange_id": exchange_id,
                "end_time": reading.end_time,
                "window": reading.window_minutes,
                "version": version,
                "universe_size": reading.universe_size,
                "covered": reading.covered,
                "falling": reading.falling,
                "value": reading.value,
                "coverage": reading.coverage,
                "usable": reading.usable,
                "reason": reading.reason,
                "inputs": inputs,
            },
        )
        written += int((landed.first()) is not None)
    return written
