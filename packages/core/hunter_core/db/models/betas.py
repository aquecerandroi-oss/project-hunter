"""``market_betas`` — immutable, versioned beta revisions against the reference.

RISK_ENGINE.md §6 and the T3.7 protocol note (``.claude/state/notes-T3.7-beta.md``
§6). The directive's rule is *"sem beta validado, manter o ativo apenas em
shadow"*, so beta is not a convenience number: it gates admission, and every
decision has to be able to name the exact revision it consumed.

**Global, not tenant.** Beta is computed by the scanner-worker from global
candles against a global reference market; nothing about it belongs to one
organization (DATABASE.md §1.1). The T3.7 note sketched an ``organization_id``
"like the rest of the schema" — carrying it would have meant either a copy per
tenant or a column that is always the same lie. Recorded as a deviation from
that sketch in DATABASE.md §18.6.

**Revisions, not a projection.** A backfill produces *another* beta for the same
market and the same cut under the same ``beta_version``; either both revisions
are kept or the earlier evidence is destroyed. So the row has its own ``id``,
and ``uq_market_betas_revision`` ends in ``input_digest`` — the same doctrine
``feature_baselines.input_fingerprint`` states (§17.2): a byte-identical **retry**
collides and is a no-op, a real **recomputation** lands as a new revision.
``computed_at``, which the T3.7 sketch put in the key, would have made every
retry a new revision.

**Which revision is in force is decided by the schema, not by a reading
convention.** ``uq_market_betas_current`` is unique on
``(market_id, as_of, beta_version) WHERE superseded_at IS NULL``: writing a new
revision without retiring the old one in the same transaction is refused by the
database. A partial index on ``WHERE valid`` could not do this — Astra's
scenario is a later revision that records *invalidity*, where filtering on
``valid`` resurrects the earlier one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, PERCENT

_MARKET_FK = "markets.id"

COEFFICIENT = Numeric(18, 8)
"""``NUMERIC(18,8)`` for ``beta`` and ``alpha``.

Neither money (``NUMERIC(28,10)``) nor a presentation fraction
(``NUMERIC(9,6)``): a regression coefficient. The width is Astra's correction to
the first sketch's ``NUMERIC(12,8)``, which left four integer digits — a
near-constant reference legitimately produces a larger slope, and the loader
must refuse rather than truncate in silence.
"""


class MarketBeta(Base, UUIDPrimaryKeyMixin):
    """One immutable revision of a market's beta against the reference market."""

    __tablename__ = "market_betas"
    __table_args__ = (
        UniqueConstraint(
            "market_id",
            "as_of",
            "beta_version",
            "input_digest",
            name="uq_market_betas_revision",
        ),
        Index(
            "uq_market_betas_current",
            "market_id",
            "as_of",
            "beta_version",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
        # The temporal read of §18.6: pin the version, then walk cuts backwards.
        # Not partial on ``superseded_at IS NULL``, because a historical replay
        # asks for the revision that was in force *then*, and that one may well
        # have been superseded since.
        Index("ix_market_betas_asof", "market_id", "beta_version", "available_at", "as_of"),
        CheckConstraint(
            "input_start < window_start AND window_start < window_end "
            "AND window_end <= as_of AND window_end <= available_at "
            "AND valid_until > window_end",
            name="window_is_ordered_and_causal",
        ),
        CheckConstraint(
            "last_pair_end IS NULL OR "
            "(last_pair_end >= window_start AND last_pair_end <= window_end)",
            name="last_pair_end_within_window",
        ),
        CheckConstraint("valid = (reason IS NULL)", name="reason_states_invalidity"),
        CheckConstraint("NOT valid OR beta IS NOT NULL", name="a_valid_revision_has_a_beta"),
        CheckConstraint("n >= 0 AND contiguous_bars >= 0", name="counts_not_negative"),
        CheckConstraint("contiguous_bars <= n", name="contiguous_bars_within_n"),
        CheckConstraint(
            "superseded_at IS NULL OR superseded_at >= computed_at",
            name="superseded_after_computed",
        ),
        CheckConstraint("char_length(beta_version) > 0", name="beta_version_not_empty"),
        CheckConstraint("char_length(input_digest) > 0", name="input_digest_not_empty"),
    )

    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_MARKET_FK, ondelete="CASCADE"))
    reference_market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="RESTRICT"), index=True
    )
    """The BTC market of the *same* venue and quote currency. For BTC itself this
    is the market's own id: beta is 1 by identity, with the statistical
    diagnostics marked not applicable rather than invented (RISK_ENGINE.md §6)."""

    as_of: Mapped[datetime]
    """The requested cut. A retry keeps the original ``as_of``; recomputing it
    from the clock would defeat the uniqueness that makes a retry a no-op."""

    window_start: Mapped[datetime]
    window_end: Mapped[datetime]
    """Last closed bar in the window — what ``valid_until`` is anchored to."""

    input_start: Mapped[datetime]
    """``window_start`` minus one bar: the anchor the first return needs."""

    last_pair_end: Mapped[datetime | None]
    """Freshness actually observed, which is not ``window_end`` when bars are
    missing at the end of the window."""

    valid_until: Mapped[datetime]
    """Anchored to ``window_end``, never to the clock of the computation — T3.7's
    first declared divergence. Recomputing today a window that ended yesterday
    renews no deadline; the nominal case (job on the hour) is unchanged and the
    late case fails safe."""

    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    available_at: Mapped[datetime] = mapped_column(server_default=func.now())
    """When this revision became consumable. Admission needs all three of
    ``available_at <= as_of_decision``, a window closed by the cut, and a deadline
    still open (RISK_ENGINE.md §6)."""

    beta_version: Mapped[str] = mapped_column(Text)
    """The frozen numeric protocol. Relaxing a threshold is a new
    ``beta_version`` by construction, never an edit."""

    estimator: Mapped[str] = mapped_column(Text)
    """``ols_with_intercept`` for a measured market, ``definition`` for BTC."""

    beta: Mapped[Decimal | None] = mapped_column(COEFFICIENT)
    alpha: Mapped[Decimal | None] = mapped_column(COEFFICIENT)
    r_squared: Mapped[Decimal | None] = mapped_column(PERCENT)
    """Null — not zero, and not invented — where it does not apply, which is the
    BTC identity row."""

    n: Mapped[int] = mapped_column(Integer)
    """Paired **returns**, not closes. The distinction is T3.7's: an unpaired
    close contributes nothing and counting it inflates the coverage claim."""

    contiguous_bars: Mapped[int] = mapped_column(Integer)
    valid: Mapped[bool]
    """Eligible *by the protocol* — never a claim of accuracy. The Risk Engine
    may not read ``valid = true`` as precision (T3.7 §7)."""

    reason: Mapped[str | None] = mapped_column(Text)
    """``btc_missing`` | ``insufficient_history`` | ``gaps`` |
    ``degenerate_variance`` (T3.7 §3), in that precedence. Non-null exactly when
    ``valid`` is false."""

    input_digest: Mapped[str] = mapped_column(Text)
    """Canonical digest of the reference identity, the effective inputs and the
    quality evidence that changes the result — what separates a retry from a
    recomputation. Hashing only the coefficients would make a gap-invalidated
    rerun look identical to the run it corrects."""

    estimate: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """``BetaEstimate.as_wire()`` verbatim — the canonical serialisation is the
    thing that gets stored, so the row and the object cannot drift."""

    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """``spec.as_wire()`` plus the numeric policy: the knobs, next to the result."""

    superseded_at: Mapped[datetime | None]
    """Set once, ``NULL`` -> value, when a later revision replaces this one. The
    only column the immutability trigger lets an ``UPDATE`` touch, and the
    declared exception to §6's "só INSERT" (DATABASE.md §18.6)."""
