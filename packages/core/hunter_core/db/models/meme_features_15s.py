"""``meme_features_15s`` — one instant of one coin younger than five minutes
(DATABASE.md §43, revision ``0030_meme_gate_v2``, T4.16).

**A separate series, not a finer ``meme_features_1m``.** The minute stays the
official series (``meme_features_v3``); this one (``meme_features_15s_v1``)
is what the 15-second chain clock writes for the mints the fast lane
photographs (``services/meme-worker/hunter_meme_worker/fast_lane.py``), and
it is the row the flow gate (EXP-M5) judges **per photo** instead of per
closed minute — the decision the study of 12/09 asked for (entries at 99–289 s
of age, with the dev already gone in 5 of 8 probes).

``as_of`` is the instant judged: every number in the row was computed only
from observations with ``received_at <= as_of`` — photos of the curve, trades
of the tape, readings of holders — the rule ``meme_features_1m`` states for
``end_time``. The columns are the instantaneous features of
``hunter_indicators.meme.fast`` (the 60 s delta and slope, the progress delta,
the holders trend) beside the tape of the last 60 s and the holders reading
the instant already had, **every value/reason pair a biconditional CHECK**.

**Global** (§1.1), monthly ``RANGE`` on ``as_of`` (§1.3) with a **7-day
retention** (``partition_retention.py``): four rows a minute per young mint is
a series worth keeping for the diary of the week, not for the quarter; a
month's partition is dropped once its end is more than seven days old.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base
from hunter_core.db.models._common import PERCENT
from hunter_core.db.models.meme_features import SLOPE

FEATURES_15S_VERSION_V1 = "meme_features_15s_v1"
"""The frozen protocol of this series. A different window or formula is a
different version — a different row by the primary key — never an edit."""


class MemeFeatures15s(Base):
    """One instant of one young mint: what the 15-second clock knew at ``as_of``."""

    __tablename__ = "meme_features_15s"
    __table_args__ = (
        Index("ix_meme_features_15s_mint_as_of", "mint", "as_of"),
        CheckConstraint(
            "(mcap_sol IS NULL) = (snapshot_observed_at IS NULL) "
            "AND (mcap_sol IS NULL) = (snapshot_source IS NULL)",
            name="a_market_cap_names_its_photo",
        ),
        CheckConstraint(
            "(mcap_delta_60s IS NULL) = (window_reason IS NOT NULL) "
            "AND (mcap_delta_60s IS NULL) = (mcap_slope_60s IS NULL)",
            name="window_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(progress_delta_60s IS NULL) = (progress_reason IS NOT NULL) "
            "AND (progress_delta_60s IS NULL) = (progress_rising IS NULL)",
            name="progress_delta_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(holders_rising IS NULL) = (holders_reason IS NOT NULL) "
            "AND (holders_rising IS NULL) = (holders_prev IS NULL)",
            name="holders_trend_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(buys_60s IS NULL) = (tape_reason IS NOT NULL) "
            "AND (buys_60s IS NULL) = (sells_60s IS NULL) "
            "AND (buys_60s IS NULL) = (unique_buyers_60s IS NULL) "
            "AND (buys_60s IS NULL) = (net_sol_flow_60s IS NULL) "
            "AND (buys_60s IS NULL) = (curve_volume_60s_sol IS NULL)",
            name="tape_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(creator_net_seller IS NULL) = (creator_net_seller_reason IS NOT NULL)",
            name="creator_net_seller_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(dev_share IS NULL) = (dev_share_reason IS NOT NULL)",
            name="dev_share_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(snipers IS NULL) = (snipers_reason IS NOT NULL)",
            name="snipers_is_null_with_a_reason",
        ),
        CheckConstraint(
            "snapshots_120s >= 0 AND (age_s IS NULL OR age_s >= 0) "
            "AND (holders IS NULL OR holders >= 0) AND (holders_prev IS NULL OR holders_prev >= 0) "
            "AND (snipers IS NULL OR snipers >= 0) AND (buys_60s IS NULL OR buys_60s >= 0) "
            "AND (sells_60s IS NULL OR sells_60s >= 0) "
            "AND (unique_buyers_60s IS NULL OR unique_buyers_60s >= 0) "
            "AND (curve_volume_60s_sol IS NULL OR curve_volume_60s_sol >= 0)",
            name="counts_are_not_negative",
        ),
        CheckConstraint(
            "dev_share IS NULL OR (dev_share >= 0 AND dev_share <= 1)",
            name="dev_share_is_a_fraction",
        ),
        CheckConstraint(
            "char_length(features_version) > 0 AND char_length(mint) > 0",
            name="provenance_is_not_empty",
        ),
        {"postgresql_partition_by": "RANGE (as_of)"},
    )

    as_of: Mapped[datetime] = mapped_column(primary_key=True)
    """The instant judged — the tick of the fast lane, ``received_at``-bounded.
    Partition key, first in the PK (§15.2), and the gate's read order."""

    mint: Mapped[str] = mapped_column(Text, primary_key=True)
    features_version: Mapped[str] = mapped_column(Text, primary_key=True)

    snapshot_observed_at: Mapped[datetime | None]
    snapshot_source: Mapped[str | None] = mapped_column(Text)
    """The newest photo received by ``as_of`` — what ``mcap_sol`` and the quote
    come from (``observed_at`` = the slot's block time for ``solana_rpc``)."""

    snapshots_120s: Mapped[int] = mapped_column(SmallInteger)
    """Photos received by ``as_of`` in the 120 s before the newest one."""

    age_s: Mapped[int | None] = mapped_column(Integer)
    """``as_of − meme_tokens.created_at`` in seconds; ``NULL`` without a creation time."""

    mcap_sol: Mapped[Decimal | None]
    mcap_delta_60s: Mapped[Decimal | None]
    mcap_slope_60s: Mapped[Decimal | None] = mapped_column(SLOPE)
    window_reason: Mapped[str | None] = mapped_column(Text)
    """``no_snapshot`` | ``too_few_points`` (no photo at least 60 s older than
    the newest) | ``out_of_range``."""

    curve_progress_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    progress_delta_60s: Mapped[Decimal | None] = mapped_column(PERCENT)
    progress_rising: Mapped[bool | None]
    progress_reason: Mapped[str | None] = mapped_column(Text)
    """``denominator_unknown`` | ``too_few_points`` | ``no_snapshot``."""

    holders: Mapped[int | None] = mapped_column(Integer)
    holders_prev: Mapped[int | None] = mapped_column(Integer)
    holders_rising: Mapped[bool | None]
    holders_reason: Mapped[str | None] = mapped_column(Text)
    """``no_holders_reader`` | ``too_few_readings`` (one reading is not a trend)."""

    buys_60s: Mapped[int | None] = mapped_column(Integer)
    sells_60s: Mapped[int | None] = mapped_column(Integer)
    unique_buyers_60s: Mapped[int | None] = mapped_column(Integer)
    net_sol_flow_60s: Mapped[Decimal | None]
    curve_volume_60s_sol: Mapped[Decimal | None]
    tape_reason: Mapped[str | None] = mapped_column(Text)
    """The tape's trades with ``block_time`` in ``(as_of − 60 s, as_of]`` and
    ``received_at <= as_of``; absent together, with the tape's own reason."""

    creator_net_seller: Mapped[bool | None]
    creator_net_seller_reason: Mapped[str | None] = mapped_column(Text)
    dev_share: Mapped[Decimal | None] = mapped_column(PERCENT)
    dev_share_reason: Mapped[str | None] = mapped_column(Text)
    snipers: Mapped[int | None] = mapped_column(Integer)
    snipers_reason: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())


__all__ = ["FEATURES_15S_VERSION_V1", "MemeFeatures15s"]
