"""``feature_baselines`` — the immutable archive behind every anomaly and score.

Its own module, exactly as ``agents_shadow.py`` is separate from ``agents.py``:
``0003_analysis`` adds one self-contained concept to DATABASE.md §5, and folding
it into ``analysis.py`` pushed that file past the 350-line budget
(``infra/scripts/check_file_size.py``). ``_MARKET_FK`` is repeated rather than
imported so neither module depends on the other.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import PERCENT, pg_enum
from hunter_core.domain.enums import BaselineSampling, BaselineSource

_MARKET_FK = "markets.id"


class FeatureBaseline(Base, UUIDPrimaryKeyMixin):
    """One immutable revision of the median/MAD a detector compares against.

    The joint M2 decision made this an **archive of revisions**, not a current
    projection: one row per (market, feature, UTC hour) would have been enough to
    score *now*, and useless to explain *then*. Recomputing tomorrow has to
    reproduce today's score exactly, so a baseline is written once and never
    updated — a new computation is a new row with a later ``available_at``, and
    the score records the ``id`` it used in its envelope.

    **The causal cut** a consumer must apply is two conditions, not one:
    ``available_at <= as_of`` (we could not have known a baseline before it
    existed) **and** ``window_end < observation_ts`` (a baseline may not contain
    the very observation being judged). Astra's scenario is the reason both are
    needed: a feature of 10:00 processed at 10:02 would pass a single
    ``available_at <= 10:02`` test against a baseline published at 10:01 that
    already includes 10:00.

    **Identity.** ``uq_feature_baselines_revision`` ends in ``input_fingerprint``,
    a canonical digest of the observations and the cut that produced the row.
    That is what separates a *retry* from a *recomputation*: replaying the same
    refresh job collides and is a no-op, while a recomputation after a backfill
    changed the sample has a different fingerprint and lands as a new revision.
    Without it the corrected baseline could not be persisted at all — ``DO
    NOTHING`` would keep the incomplete one and ``UPDATE`` is forbidden.

    Maturity is **not** stored: ``sample_size``, ``expected_size``,
    ``distinct_days`` and ``coverage`` are recorded raw and the usability gate
    (>= 3 distinct days AND >= 120 valid observations) is applied by the reader
    against its own versioned thresholds. A stored boolean would freeze a
    threshold that is meant to be versioned, and would go stale the day it moves.
    A baseline below the gate still exists — "under construction" is a state the
    Radar shows, not a row that is missing.
    """

    __tablename__ = "feature_baselines"
    __table_args__ = (
        UniqueConstraint(
            "market_id",
            "feature",
            "hour_of_day",
            "feature_version",
            "algo_version",
            "window_end",
            "source",
            "input_fingerprint",
            name="uq_feature_baselines_revision",
        ),
        Index(
            "ix_feature_baselines_lookup",
            "market_id",
            "feature",
            "hour_of_day",
            "available_at",
        ),
        CheckConstraint("hour_of_day BETWEEN 0 AND 23", name="hour_of_day_in_range"),
        CheckConstraint(
            "window_start < window_end AND window_end <= available_at",
            name="window_is_ordered_and_causal",
        ),
        CheckConstraint(
            "sample_size >= 0 AND expected_size > 0 AND sample_size <= expected_size "
            "AND distinct_days >= 0",
            name="counts_are_coherent",
        ),
        CheckConstraint("coverage BETWEEN 0 AND 1", name="coverage_is_a_fraction"),
        CheckConstraint("mad >= 0", name="mad_not_negative"),
    )

    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_MARKET_FK, ondelete="CASCADE"))
    feature: Mapped[str] = mapped_column(Text)
    """The feature key, as registered in ``feature_definitions.name``."""

    feature_version: Mapped[int] = mapped_column(Integer, server_default="1")
    algo_version: Mapped[str] = mapped_column(Text)
    """Version of the baseline algorithm itself. A reader selects a *compatible*
    pair of versions: a median computed by another algorithm is another
    population, not a newer value of the same one."""

    hour_of_day: Mapped[int] = mapped_column(SmallInteger)
    """UTC hour bucket, 0-23. Volume at 03:00 UTC is not volume at 15:00 UTC."""

    window_start: Mapped[datetime]
    window_end: Mapped[datetime]
    """Largest observation timestamp included — the second half of the causal cut."""

    available_at: Mapped[datetime]
    """When this revision became usable. Never back-dated, including for
    ``BOOTSTRAP`` rows: a bootstrap baseline computed today may inform decisions
    from today, never a decision that was actually taken last week."""

    median: Mapped[Decimal]
    mad: Mapped[Decimal]
    """Median absolute deviation. ``0`` is legal and meaningful (a constant
    feature); the scorer's ``min_scale``/unavailability rule lives with the
    versioned weights, not here."""

    sample_size: Mapped[int] = mapped_column(Integer)
    expected_size: Mapped[int] = mapped_column(Integer)
    """420 for a full seven-day, per-minute, one-hour bucket."""

    distinct_days: Mapped[int] = mapped_column(Integer)
    coverage: Mapped[Decimal] = mapped_column(PERCENT)
    """``sample_size / expected_size`` as a fraction, stored so a reader never
    has to recompute it from counts that a later revision may have changed."""

    source: Mapped[BaselineSource] = mapped_column(pg_enum("baseline_source"))
    sampling: Mapped[BaselineSampling] = mapped_column(pg_enum("baseline_sampling"))
    input_fingerprint: Mapped[str] = mapped_column(Text)
    """Canonical digest of the observation set and the cut this revision was
    computed from — the difference between a retry and a recomputation."""

    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
