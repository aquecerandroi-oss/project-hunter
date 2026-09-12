"""One row per tick of the meme Lab loop (DATABASE.md §42, revision
``0031_meme_lab_ticks``, T4.15).

**Global table** (§1.1), the shape of ``meme_paper_bets``: a tick of the
paper Lab belongs to no organization — no ``organization_id``, no RLS. The
loop appends one row at the end of every tick with the counters
``TickReport`` carries and ``refusals`` — the same ``{rule set name:
{refusal: count}}`` the heartbeat publishes, frozen — so the daily close can
say how much of a finished day the gate saw and why it refused, from rows
alone. Nobody updates or deletes a tick: it is what happened.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base
from hunter_core.db.models._common import JSONB_EMPTY


class MemeLabTick(Base):
    """What one pass of ``lab_tick`` evaluated, proposed, filled, closed and refused."""

    __tablename__ = "meme_lab_ticks"
    __table_args__ = (
        CheckConstraint(
            "minutes_evaluated >= 0 AND rows_evaluated >= 0 AND rule_sets_active >= 0 "
            "AND proposals >= 0 AND expired >= 0 AND cancelled >= 0 AND fills >= 0 "
            "AND unfilled >= 0 AND closes >= 0 AND bets_open >= 0",
            name="counters_are_not_negative",
        ),
        CheckConstraint("jsonb_typeof(refusals) = 'object'", name="refusals_is_an_object"),
    )

    ticked_at: Mapped[datetime] = mapped_column(primary_key=True)
    """The tick's own ``now`` — the instant the loop finished the pass."""

    tick_minute: Mapped[datetime | None]
    """The newest closed minute the gate evaluated; ``NULL`` when none."""

    minutes_evaluated: Mapped[int] = mapped_column(Integer)
    rows_evaluated: Mapped[int] = mapped_column(Integer)
    rule_sets_active: Mapped[int] = mapped_column(Integer)
    proposals: Mapped[int] = mapped_column(Integer)
    expired: Mapped[int] = mapped_column(Integer)
    cancelled: Mapped[int] = mapped_column(Integer)
    fills: Mapped[int] = mapped_column(Integer)
    unfilled: Mapped[int] = mapped_column(Integer)
    closes: Mapped[int] = mapped_column(Integer)
    bets_open: Mapped[int] = mapped_column(Integer)
    refusals: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """``{rule set name: {refusal: count}}`` over the minutes of this tick."""
