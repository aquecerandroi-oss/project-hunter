"""``market_breadth`` — one immutable, minute-anchored reading of ``breadth_5m``.

T3.77 / H-P8 (``docs/PIPELINE.md`` §4b item 14). The share of the monitored perpetuals
of one venue whose close fell over the five completed minutes ending at
``end_time``, written once per minute by the scanner's producer and read at
decision time by :mod:`hunter_strategy_worker.breadth_gate`.

**Why a table and not a computation inside the gate.** The gate runs inside the
strategy-worker, per version, per bar; the number is a fold over ~200 markets ×
6 minutes. Computing it there would put a universe-wide scan on the decision
path — and, worse, would make the replay recompute from *today's* candles a
number the live decision took from *that* minute's. A persisted series is the
only shape in which the replay and the live bar can be shown to have read the
same value. Same argument, same conclusion, same shape as ``market_regimes``
(T3.43) and ``market_betas`` (T3.7b).

**Global, not tenant** (DATABASE.md §1.1): the universe is the exchange's, not an
organization's. No ``organization_id``, therefore no RLS — the shape
``market_regimes``, ``market_betas`` and ``fx_observations`` already have.

**Immutable, and the key is what makes a retry a no-op.**
``uq_market_breadth_reading`` on ``(exchange_id, breadth_version, window_minutes,
end_time)``: the producer re-running the same minute collides and writes nothing.
There is deliberately **no** ``input_digest`` revision axis as in
``market_betas``: a reading is a fold over candles that are already ``is_final``,
so a second pass over the same minute either finds the same candles or finds
candles that a backfill added — and in the second case the honest answer is a
**new** ``breadth_version``, not a silent second row for the same minute that
readers would have to disambiguate.

**Not partitioned, and here is the count.** One row per minute per exchange is
``60 × 24 × 365 = 525 600`` rows/year; with a second venue live it is 1 051 200.
The threshold the brief sets is 1 M rows/year, so a single venue is comfortably
under it and two venues sit on it. Declared
rather than hidden: the day a second exchange starts producing, this table is the
next partitioning candidate, and the unique key below is already ordered so that a
``RANGE (end_time)`` partitioning would not change a single query.

**One index, and it is the unique key's.** There is no second index here on
purpose. The only read the gate makes pins venue + protocol + window and lands on
one ``end_time`` — four equality predicates against exactly the four columns of
``uq_market_breadth_reading``, in its order — and the foreign key's ``RESTRICT``
check probes ``exchange_id``, that index's leading column. So the FK column
carries no ``index=True``: DATABASE.md §1 asks that every foreign key be indexed,
and a composite that *leads* with the FK column **is** that index (the rule the
tenant tables' ``organization_id``-leading composites already state). A copy of
the unique's columns and a standalone index on its prefix existed in the first
draft of ``0019`` and were dropped before it shipped: three btrees to maintain on
a write path of one row per minute, where one answers every reader
(``docs/DATABASE.md`` §31).

**Unusable is a row, not a gap.** ``value IS NULL`` with ``reason =
'insufficient_coverage'`` is the producer saying "the universe did not answer",
which is a fact about that minute and must survive; a missing row means "nobody
ran", and the two are different operator problems (the same distinction
``regime_gate`` keeps between ``no_row`` and ``stale``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, PERCENT


class MarketBreadth(Base, UUIDPrimaryKeyMixin):
    """One ``breadth_5m`` reading for one venue at one closed minute."""

    __tablename__ = "market_breadth"
    __table_args__ = (
        UniqueConstraint(
            "exchange_id",
            "breadth_version",
            "window_minutes",
            "end_time",
            name="uq_market_breadth_reading",
        ),
        # The column order is the gate's read, not alphabetical: pin venue +
        # protocol + window, then land on one ``end_time``. Leading with the
        # three pinned columns is what makes the probe an equality lookup
        # instead of a range scan over a year — and it is why this constraint's
        # index is the only one the table needs.
        CheckConstraint("usable = (reason IS NULL)", name="reason_states_unusability"),
        CheckConstraint("NOT usable OR value IS NOT NULL", name="a_usable_reading_has_a_value"),
        CheckConstraint(
            "falling >= 0 AND covered >= 0 AND universe_size >= 0", name="counts_not_negative"
        ),
        CheckConstraint("falling <= covered", name="falling_within_covered"),
        CheckConstraint("covered <= universe_size", name="covered_within_universe"),
        CheckConstraint("window_minutes > 0", name="window_is_positive"),
        CheckConstraint("value IS NULL OR (value >= 0 AND value <= 1)", name="value_is_a_fraction"),
        CheckConstraint("coverage >= 0 AND coverage <= 1", name="coverage_is_a_fraction"),
        CheckConstraint("char_length(breadth_version) > 0", name="breadth_version_not_empty"),
    )

    exchange_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exchanges.id", ondelete="RESTRICT"))
    """The venue whose universe was measured. ``RESTRICT``: deleting an exchange
    would silently orphan the only record of what its universe was doing — and
    the check that enforces it reads ``uq_market_breadth_reading``'s leading
    column, which is why there is no index of its own here."""

    end_time: Mapped[datetime]
    """The instant the window closes — and the instant a decision must match
    **exactly** to be gated by this row. The last candle folded into it opened at
    ``end_time - 1 min``; nothing that opened at ``end_time`` entered."""

    window_minutes: Mapped[int] = mapped_column(SmallInteger)
    """Five today. In the key because a second window is a second series, never a
    reinterpretation of this one."""

    breadth_version: Mapped[str] = mapped_column(Text)
    """``breadth_v1`` — the frozen numeric protocol
    (:data:`hunter_indicators.breadth.BREADTH_VERSION`). Relaxing the coverage
    floor, changing the completeness rule or moving the strict ``<`` is a new
    version by construction."""

    universe_size: Mapped[int] = mapped_column(Integer)
    """Monitored active perpetuals of the venue **at the moment of the pass**.
    ``markets.is_monitored`` is overwritten in place by every refresh, so a
    backfilled minute carries today's universe and says so by carrying the
    number: it is evidence about the fold, not about that historical minute."""

    covered: Mapped[int] = mapped_column(Integer)
    falling: Mapped[int] = mapped_column(Integer)

    value: Mapped[Decimal | None] = mapped_column(PERCENT)
    """``falling / covered``, ``NULL`` when unusable — never zero, which would
    read as "nothing is falling"."""

    coverage: Mapped[Decimal] = mapped_column(PERCENT)
    usable: Mapped[bool]
    reason: Mapped[str | None] = mapped_column(Text)
    """``insufficient_coverage`` | ``empty_universe``. Non-null exactly when
    ``usable`` is false, enforced by ``reason_states_unusability``."""

    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    """Wall clock of the fold. Never a cut: every cut in this row is
    ``end_time``."""

    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """The knobs next to the result — window, coverage floor, the exchange code
    — so a row can be audited without knowing which build wrote it."""
