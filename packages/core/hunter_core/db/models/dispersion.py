"""``market_dispersion`` — one immutable, minute-anchored reading of BTC × alts.

T3.90 / H-P18 (``docs/PIPELINE.md`` §4b item 16). The median 24 h return of the
alts of one venue's shadow universe minus the reference's own 24 h return, at the
minute ``end_time``, written once per minute by the scanner's producer and read at
decision time by :mod:`hunter_strategy_worker.dispersion_gate`.

**Why a second table and not a column on ``market_breadth``.** The obvious
alternative was rejected after reading ``0019``'s shape rather than its name.
``market_breadth`` has no generic ``series``/``value`` pair: it has
``falling``/``covered`` with ``CHECK falling <= covered``, a ``value`` constrained
to ``[0, 1]`` and ``window_minutes`` in its unique key. A dispersion is **signed**
(the whole point is that it is negative when the alts are below the BTC), is made
of four numbers rather than one (``btc_r24h``, ``median_alt_r24h``,
``dispersion``, ``share_below_btc``), has no ``falling`` count and needs no
window column, since its horizon is part of its version string. Widening
``market_breadth`` would have meant dropping two CHECKs that protect every row
already in it — the constraints would stop describing the rows they were written
for. A sibling table with the same conventions (global, immutable,
``end_time``-anchored, privileges by subtraction, a downgrade that refuses to lose
rows) keeps both series exactly as strict as they can each afford to be.

**Global, not tenant** (DATABASE.md §1.1): the universe is the exchange's, not an
organization's. No ``organization_id``, therefore no RLS — the shape
``market_regimes``, ``market_betas``, ``fx_observations`` and ``market_breadth``
already have.

**Immutable, and the key is what makes a retry a no-op.**
``uq_market_dispersion_reading`` on ``(exchange_id, dispersion_version,
end_time)``: the producer re-running the same minute collides and writes nothing.
No ``input_digest`` revision axis as in ``market_betas``: a reading is a fold over
candles that are already ``is_final``, so a second pass over the same minute
either finds the same candles or finds candles a backfill added — and in the
second case the honest answer is a **new** ``dispersion_version``, not a silent
second row for the same minute.

**The horizon is not in the key, and that is the T3.88 lesson applied.**
``market_breadth`` carries ``window_minutes`` in its unique key because T3.77
believed a second window would be the same series with a parameter; T3.88 then had
to write ``breadth_v2`` anyway, because a different universe is a different
series. A different horizon is a different series for the same reason, so it lives
where the universe and the reference live: inside ``dispersion_version``, with the
numbers themselves in ``inputs`` for an auditor.

**Not partitioned, and here is the count.** One row per minute per exchange per
version is ``60 × 24 × 365 = 525 600`` rows/year; with a second venue live it is
1 051 200. The threshold the brief sets is 1 M rows/year, so one venue sits at
53 % of it — the same arithmetic, and the same declared consequence, as
``market_breadth`` (DATABASE.md §31): the day a second exchange produces, this
table is a partitioning candidate, and the unique key is already ordered so a
``RANGE (end_time)`` partitioning would not change a single query.

**One index, and it is the unique key's.** The only read the gate makes pins
venue + series and lands on one ``end_time`` — three equality predicates against
exactly the three columns of ``uq_market_dispersion_reading``, in its order — and
the foreign key's ``RESTRICT`` check probes ``exchange_id``, that index's leading
column. So the FK column carries no ``index=True``: DATABASE.md §1 asks that every
foreign key be indexed, and a composite that *leads* with the FK column **is**
that index (the rule ``market_breadth`` states, kept).

**Unusable is a row, not a gap.** ``dispersion IS NULL`` with a ``reason`` is the
producer saying "the universe did not answer" or "the reference did not", which is
a fact about that minute and must survive; a missing row means "nobody ran", and
the two are different operator problems.
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


class MarketDispersion(Base, UUIDPrimaryKeyMixin):
    """One ``dispersion_24h`` reading for one venue at one closed minute."""

    __tablename__ = "market_dispersion"
    __table_args__ = (
        UniqueConstraint(
            "exchange_id",
            "dispersion_version",
            "end_time",
            name="uq_market_dispersion_reading",
        ),
        # The column order is the gate's read, not alphabetical: pin venue +
        # series, then land on one ``end_time``.
        CheckConstraint("usable = (reason IS NULL)", name="reason_states_unusability"),
        CheckConstraint(
            "NOT usable OR (dispersion IS NOT NULL AND btc_r24h IS NOT NULL "
            "AND median_alt_r24h IS NOT NULL AND share_below_btc IS NOT NULL)",
            name="a_usable_reading_has_every_value",
        ),
        # The identity the series is defined by, enforced by the database rather
        # than trusted: the producer quantizes the reference and the median to six
        # decimals *before* subtracting, so this is exact and not approximate.
        CheckConstraint(
            "dispersion IS NULL OR dispersion = median_alt_r24h - btc_r24h",
            name="dispersion_is_the_difference",
        ),
        CheckConstraint(
            "covered >= 0 AND alts_covered >= 0 AND alts_below_btc >= 0 AND universe_size >= 0",
            name="counts_not_negative",
        ),
        CheckConstraint("covered <= universe_size", name="covered_within_universe"),
        CheckConstraint("alts_covered <= covered", name="alts_within_covered"),
        CheckConstraint("alts_below_btc <= alts_covered", name="below_within_alts"),
        CheckConstraint("horizon_minutes > 0", name="horizon_is_positive"),
        CheckConstraint(
            "share_below_btc IS NULL OR (share_below_btc >= 0 AND share_below_btc <= 1)",
            name="share_is_a_fraction",
        ),
        CheckConstraint("coverage >= 0 AND coverage <= 1", name="coverage_is_a_fraction"),
        CheckConstraint("char_length(dispersion_version) > 0", name="version_not_empty"),
    )

    exchange_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exchanges.id", ondelete="RESTRICT"))
    """The venue whose universe was measured. ``RESTRICT``: deleting an exchange
    would silently orphan the only record of what its alts were doing — and the
    check that enforces it reads ``uq_market_dispersion_reading``'s leading
    column, which is why there is no index of its own here."""

    end_time: Mapped[datetime]
    """The instant the window closes — and the instant a decision must match
    **exactly** to be gated by this row. The two candles folded into it opened at
    ``end_time - 1 min`` and ``end_time - 24 h - 1 min``; nothing that opened at
    ``end_time`` entered."""

    dispersion_version: Mapped[str] = mapped_column(Text)
    """``dispersion_24h_v1`` — the frozen protocol: horizon, two-endpoint rule,
    median, coverage floor, **the universe** and **the reference market**
    (:data:`hunter_indicators.dispersion.SPECS`). Changing any of them is a new
    version by construction, never an edit of these rows."""

    horizon_minutes: Mapped[int] = mapped_column(SmallInteger)
    """1 440 today. **Not** in the unique key — unlike ``market_breadth``'s
    ``window_minutes`` — because a different horizon is a different series and
    already has a different ``dispersion_version``. It is stored so a row can be
    read without resolving the version string against a build."""

    universe_size: Mapped[int] = mapped_column(Integer)
    """Markets the series' universe declared **at the moment of the pass**.
    ``markets.is_monitored`` is overwritten in place by every refresh, so a
    backfilled minute carries today's universe and says so by carrying the
    number: it is evidence about the fold, not about that historical minute."""

    covered: Mapped[int] = mapped_column(Integer)
    """Markets with both endpoint closes, the reference included."""

    alts_covered: Mapped[int] = mapped_column(Integer)
    """Covered markets other than the reference: the median's own ``n``."""

    alts_below_btc: Mapped[int] = mapped_column(Integer)
    """Covered alts strictly below the reference's 24 h return. ``0`` when there
    is no reference return, because nobody is below a number that does not
    exist — a count, never a verdict."""

    btc_r24h: Mapped[Decimal | None] = mapped_column(PERCENT)
    """The reference's 24 h close-to-close return, ``NULL`` when unusable. A
    fraction (``-0.015`` is -1,5 %), so ``NUMERIC(9,6)`` is the repo's percentage
    contract (DATABASE.md §1) and not a stretched one. The per-market returns are
    **never** stored, which is also why the type is safe: the only numbers here
    are the reference's and a median, both bounded by the middle of a
    distribution of established perpetuals."""

    median_alt_r24h: Mapped[Decimal | None] = mapped_column(PERCENT)
    """Median 24 h return of the covered alts, ``NULL`` when unusable."""

    dispersion: Mapped[Decimal | None] = mapped_column(PERCENT)
    """``median_alt_r24h - btc_r24h``, ``NULL`` when unusable — never zero, which
    would read as "the alts and the BTC agree". **Negative is the discordância**
    H-P18 is about."""

    share_below_btc: Mapped[Decimal | None] = mapped_column(PERCENT)
    """``alts_below_btc / alts_covered``, ``NULL`` when unusable. Carried next to
    the dispersion because the two disagree in an informative way: a median well
    below the BTC with a share near 1 is the whole universe sinking, and the same
    median with a share near 0,5 is a split tape."""

    coverage: Mapped[Decimal] = mapped_column(PERCENT)
    usable: Mapped[bool]
    reason: Mapped[str | None] = mapped_column(Text)
    """``insufficient_coverage`` | ``btc_missing`` | ``empty_universe`` |
    ``no_alts``. Non-null exactly when ``usable`` is false, enforced by
    ``reason_states_unusability``."""

    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    """Wall clock of the fold. Never a cut: every cut in this row is
    ``end_time``."""

    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """The knobs next to the result — horizon, coverage floor, exchange code,
    reference symbol, universe rule and the instant membership was judged at — so
    a row can be audited without knowing which build wrote it."""
