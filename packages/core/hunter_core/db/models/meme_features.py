"""``meme_features_1m`` — one closed minute of one mint (DATABASE.md §33.2/§35,
revisions ``0021_meme_radar`` and ``0023_meme_boards_trades``).

Moved out of ``meme_series.py`` when ``0023`` grew it: the boards of the site
(``/ws/trenches``) and the ``swap-api`` tape fill what ``0021`` left ``NULL``
with a reason, and add the columns the EXP-M1 gate refuses every row without
(``creator_net_seller``, ``curve_volume_1m_sol``). **Every value/reason pair is
a biconditional CHECK**, the ``0021`` rule: no row with a missing number and no
reason, no row with both.

**Non-anticipation is a property of the producer, stated here so the schema
reader knows what a number means**: a value in a row with ``end_time = T`` was
computed only from observations with ``received_at <= T`` — a trade whose
block time is inside the minute but which reached us after ``T`` is *not* in
``buys_1m``; it is in no minute, and the tape's per-minute count is therefore
"what was known at T", never "what happened by T". The Lab reads a closed
minute one minute later, so the gap between the two is exactly the source's
delivery lag (``meme_curve_snapshots.received_at − observed_at`` and the
``swap-api`` pull cadence), declared in ``docs/PIPELINE.md`` §1e.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base
from hunter_core.db.models._common import PERCENT

RATIO = Numeric(18, 8)
SLOPE = Numeric(12, 6)
"""A slope — a growth fraction per minute or SOL per minute (``0026``): six
decimals like a fraction, six integer digits because a market cap in SOL can
move whole units per minute."""
"""A ratio is neither money (``NUMERIC(28,10)``) nor a presentation fraction
(``NUMERIC(9,6)``) — the same slot ``market_betas.beta`` occupies (§18.6). A
buy/sell ratio with no sells is not representable as a number, so it is NULL with
a reason (``no_sells``), never an infinity squeezed into a scale."""

FEATURES_VERSION_V1 = "meme_features_v1"
"""The frozen protocol of ``meme_features_1m``: which inputs, which formula, which
reasons. Changing any of them is a new version — a different row by the primary
key — never an edit of a minute some hypothesis may already have been cut by.
``0023`` adds columns to the same version: a ``NULL`` with a reason in the old
rows and a number in the new ones is the same protocol reading the same minute
with more sources, not a different formula for a number that already existed."""


class MemeFeatures1m(Base):
    """One closed minute of one mint: what the free sources allow, and nothing else."""

    __tablename__ = "meme_features_1m"
    __table_args__ = (
        Index("ix_meme_features_1m_mint_end_time", "mint", "end_time"),
        # Every value/reason pair is a biconditional: NULL if and only if there is
        # a reason. There is no row with a missing number and no reason, and no
        # row that carries both — the ``no_entry_reason`` rule of §16.2, five
        # times, because "absent" read as "zero" is Astra's MUST-FIX 1.
        CheckConstraint(
            "(mcap_sol IS NULL) = (curve_reason IS NOT NULL)",
            name="mcap_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(curve_progress_pct IS NULL) = (progress_reason IS NOT NULL)",
            name="progress_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(unique_buyers IS NULL) = (unique_buyers_reason IS NOT NULL)",
            name="unique_buyers_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(buy_sell_ratio IS NULL) = (buy_sell_ratio_reason IS NOT NULL)",
            name="buy_sell_ratio_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(top10_share IS NULL) = (top10_share_reason IS NOT NULL)",
            name="top10_share_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(creator_sold IS NULL) = (creator_sold_reason IS NOT NULL)",
            name="creator_sold_is_null_with_a_reason",
        ),
        CheckConstraint(
            "coverage >= 0 AND coverage <= 1",
            name="coverage_is_a_fraction",
        ),
        CheckConstraint("age_minutes IS NULL OR age_minutes >= 0", name="age_is_not_negative"),
        CheckConstraint(
            "unique_buyers IS NULL OR unique_buyers >= 0", name="buyers_are_not_negative"
        ),
        CheckConstraint(
            "buy_sell_ratio IS NULL OR buy_sell_ratio >= 0", name="ratio_is_not_negative"
        ),
        CheckConstraint(
            "top10_share IS NULL OR (top10_share >= 0 AND top10_share <= 1)",
            name="top10_share_is_a_fraction",
        ),
        CheckConstraint(
            "char_length(features_version) > 0 AND char_length(mint) > 0",
            name="provenance_is_not_empty",
        ),
        # 0023 — the boards and the tape, each value with its reason.
        CheckConstraint(
            "(holders IS NULL) = (holders_reason IS NOT NULL)",
            name="holders_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(holders IS NULL) = (holders_observed_at IS NULL) "
            "AND (holders IS NULL) = (holders_source IS NULL)",
            name="holders_name_their_reading",
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
            "(buys_1m IS NULL) = (tape_reason IS NOT NULL) "
            "AND (buys_1m IS NULL) = (sells_1m IS NULL) "
            "AND (buys_1m IS NULL) = (net_sol_flow_1m IS NULL) "
            "AND (buys_1m IS NULL) = (curve_volume_1m_sol IS NULL)",
            name="tape_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(creator_net_seller IS NULL) = (creator_net_seller_reason IS NOT NULL)",
            name="creator_net_seller_is_null_with_a_reason",
        ),
        CheckConstraint(
            "(holders IS NULL OR holders >= 0) AND (snipers IS NULL OR snipers >= 0) "
            "AND (buys_1m IS NULL OR buys_1m >= 0) AND (sells_1m IS NULL OR sells_1m >= 0)",
            name="holders_and_snipers_are_not_negative",
        ),
        CheckConstraint(
            "dev_share IS NULL OR (dev_share >= 0 AND dev_share <= 1)",
            name="dev_share_is_a_fraction",
        ),
        CheckConstraint(
            "curve_volume_1m_sol IS NULL OR curve_volume_1m_sol >= 0",
            name="curve_volume_is_not_negative",
        ),
        # 0026 — the lines and the hype (T4.10). Every CHECK is scoped to
        # ``line_points IS NOT NULL``: a row folded before the lines existed
        # carries no count, no line, no hype and no invented reason.
        CheckConstraint(
            "line_points IS NULL OR (support_line_sol IS NULL) = (line_reason IS NOT NULL)",
            name="support_line_is_null_with_a_reason",
        ),
        CheckConstraint(
            "line_points IS NULL OR ((support_line_sol IS NULL) = (support_line_slope IS NULL) "
            "AND (support_line_sol IS NULL) = (higher_lows IS NULL) "
            "AND (support_line_sol IS NULL) = (distance_to_support_pct IS NULL))",
            name="support_group_is_absent_together",
        ),
        CheckConstraint(
            "line_reason IS NULL OR line_reason IN "
            "('too_few_points', 'no_snapshot', 'flat', 'out_of_range')",
            name="line_reason_is_a_known_label",
        ),
        CheckConstraint(
            "(high_15m_sol IS NULL) = (low_15m_sol IS NULL)",
            name="window_extremes_are_absent_together",
        ),
        CheckConstraint(
            "line_points IS NULL OR line_points >= 0", name="line_points_are_not_negative"
        ),
        CheckConstraint(
            "line_points IS NULL OR (hype_score IS NULL) = "
            "coalesce(hype_reason = 'no_tape_no_board', false)",
            name="hype_is_null_without_both_sources",
        ),
        CheckConstraint(
            "hype_reason IS NULL OR hype_reason IN ('no_tape_no_board', 'partial')",
            name="hype_reason_is_a_known_label",
        ),
        CheckConstraint(
            "hype_score IS NULL OR (hype_score >= 0 AND hype_score <= 1)",
            name="hype_score_is_a_fraction",
        ),
        CheckConstraint(
            "(tape_source IS NULL) = (tape_window_s IS NULL) "
            "AND (tape_source IS NULL) = (tape_as_of IS NULL) "
            "AND (tape_source IS NULL OR tape_source IN ('swap_api_trades', 'activity_1m')) "
            "AND (tape_source IS NULL OR buys_1m IS NOT NULL)",
            name="tape_source_is_consistent",
        ),
        {"postgresql_partition_by": "RANGE (end_time)"},
    )

    end_time: Mapped[datetime] = mapped_column(primary_key=True)
    """The instant the minute closed. Partition key, first in the PK (§15.2) —
    and the radar's own read order: ``WHERE end_time = :minute ORDER BY
    curve_progress_pct DESC LIMIT n`` is a prefix scan on this index."""

    mint: Mapped[str] = mapped_column(Text, primary_key=True)

    features_version: Mapped[str] = mapped_column(Text, primary_key=True)
    """In the key, so a second protocol is a second row and never an edit."""

    curve_progress_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    """``1 - real_token_reserves / initial_real_token_reserves`` as a fraction.
    **Not** ``real_sol_reserves`` over an observed SOL threshold — that was the
    original design and Astra corrected it, because the threshold is not a
    confirmed universal constant (T4-MEME-RADAR.md §3)."""

    progress_reason: Mapped[str | None] = mapped_column(Text)
    """``not_polled`` | ``rate_limited`` | ``insufficient_coverage`` |
    ``denominator_unknown``.

    **Separate from ``curve_reason``, and the split is a correction made while
    writing the producer** (``.claude/state/notes-T4.2.md`` §contrato amendment
    1). One shared reason made a real number unrepresentable: a mint whose
    snapshot landed but whose ``initial_real_token_reserves`` was never observed
    has a **known market cap** and an **unknown progress**, and a single
    biconditional would have forced the collector to throw the market cap away to
    stay inside the CHECK. Two absences with two causes get two reasons."""

    mcap_sol: Mapped[Decimal | None]
    """Carried from the snapshot this row was derived from — a *copy of a
    generated value*, on purpose: the minute's row must keep saying what the
    market cap was at that minute even after retention drops the snapshot."""

    curve_reason: Mapped[str | None] = mapped_column(Text)
    """Why there is no market cap: ``not_polled`` | ``rate_limited`` |
    ``insufficient_coverage``. Non-null exactly when the minute saw **no curve
    observation at all** — which is also when ``coverage`` is zero and a row in
    ``meme_ingest_gaps`` names the same window."""

    unique_buyers: Mapped[int | None] = mapped_column(Integer)
    unique_buyers_reason: Mapped[str | None] = mapped_column(Text)
    buy_sell_ratio: Mapped[Decimal | None] = mapped_column(RATIO)
    buy_sell_ratio_reason: Mapped[str | None] = mapped_column(Text)
    """Counts, not notional — declared here because the two are different numbers
    and the column name alone does not say which (T4-MEME-RADAR.md §5). Filled
    since T4.2c from the ``swap-api`` tape of the minute (distinct buyers
    excluding the creator; buys/sells count ratio, ``no_sells`` when nothing was
    sold); ``no_trade_feed`` before the first pull of a mint."""

    top10_share: Mapped[Decimal | None] = mapped_column(PERCENT)
    top10_share_reason: Mapped[str | None] = mapped_column(Text)
    creator_sold: Mapped[bool | None]
    creator_sold_reason: Mapped[str | None] = mapped_column(Text)
    """Since T4.2c: ``top10_share`` is the site's own ``t10`` (board entry or
    risk read — whose aggregation rule the site does not document, which is why
    the source is named beside it in ``holders_source``); ``creator_sold`` is
    *any* sell by ``meme_tokens.creator`` in the tape covered so far.
    ``no_holders_reader`` / ``no_trade_feed`` when neither source has spoken."""

    age_minutes: Mapped[int | None] = mapped_column(Integer)
    """``end_time - meme_tokens.created_at`` in whole minutes. Nullable **without**
    a reason column, and that is a decision: its only cause is
    ``meme_tokens.created_at`` being unobserved, which the token row already
    states. A sixth reason column would be the second truth of §19.3."""

    coverage: Mapped[Decimal] = mapped_column(PERCENT)
    """Fraction of the minute's expected observations that landed: ``1`` when a
    curve snapshot was recorded inside the minute, ``0`` when none was. Never
    NULL — a minute with no coverage is still a minute we accounted for, and the
    matching hole is a row in ``meme_ingest_gaps``."""

    snapshot_observed_at: Mapped[datetime | None]
    snapshot_source: Mapped[str | None] = mapped_column(Text)
    """Which observation the curve numbers came from. This is what lets the T4.3
    screen show source and lag per point instead of a line pretending to be
    continuous."""

    # --- 0023: the boards of the site and the swap-api tape -------------------
    holders: Mapped[int | None] = mapped_column(Integer)
    holders_reason: Mapped[str | None] = mapped_column(Text)
    holders_observed_at: Mapped[datetime | None]
    holders_source: Mapped[str | None] = mapped_column(Text)
    """Holders as the board (``trenches_ws``) or the risk read
    (``indexer_rest:/in-memory-coin``) reported them, with the instant and the
    source of that reading — the newest with ``received_at <= end_time``.
    ``top10_share`` (``0021``) carries the same provenance: it is read from the
    same entry."""

    dev_share: Mapped[Decimal | None] = mapped_column(PERCENT)
    dev_share_reason: Mapped[str | None] = mapped_column(Text)
    snipers: Mapped[int | None] = mapped_column(Integer)
    snipers_reason: Mapped[str | None] = mapped_column(Text)

    buys_1m: Mapped[int | None] = mapped_column(Integer)
    sells_1m: Mapped[int | None] = mapped_column(Integer)
    net_sol_flow_1m: Mapped[Decimal | None]
    curve_volume_1m_sol: Mapped[Decimal | None]
    tape_reason: Mapped[str | None] = mapped_column(Text)
    """The tape of the minute — curve trades with ``block_time`` in
    ``(end_time − 1 min, end_time]`` **and** ``received_at <= end_time``. One
    reason for the four: they come from one source and are absent together
    (``no_trade_feed`` before the first pull, ``rate_limited``,
    ``unsupported_quote``). A pulled tape with no trade in the window is a real
    ``0``, and the module docstring says what that zero means."""

    creator_net_seller: Mapped[bool | None]
    creator_net_seller_reason: Mapped[str | None] = mapped_column(Text)
    """``Σ creator sells − Σ creator buys > 0`` in SOL over the tape covered so
    far (``block_time <= end_time``, ``received_at <= end_time``) — the input of
    the EXP-M1 gate (``hunter_indicators.meme.rules``). Distinct from
    ``creator_sold``: a creator who sold once and bought back more has sold and
    is not a net seller. ``NULL`` when the creator is unknown or the tape is."""

    # --- 0026: the lines and the hype (T4.10, ``meme_features_v3``) ------------
    mcap_slope_5m: Mapped[Decimal | None] = mapped_column(SLOPE)
    mcap_slope_15m: Mapped[Decimal | None] = mapped_column(SLOPE)
    """OLS slope of ``ln(mcap_sol)`` against minutes (a growth fraction per
    minute) over the last 5 / 15 minutes of curve photos received by ``end_time``."""

    high_15m_sol: Mapped[Decimal | None]
    low_15m_sol: Mapped[Decimal | None]
    breakout_15m: Mapped[bool | None]
    """``mcap_sol >= high`` of the **previous** window ``(end_time − 16 min,
    end_time − 1 min]`` — the minute being folded is never its own reference."""

    support_line_sol: Mapped[Decimal | None]
    support_line_slope: Mapped[Decimal | None] = mapped_column(SLOPE)
    higher_lows: Mapped[bool | None]
    distance_to_support_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    """The line through the last two local lows of the window, evaluated at
    ``end_time``; its slope in SOL/min; whether the second low is above the
    first; ``(mcap − support) / support``. ``NULL`` together, with ``line_reason``."""

    line_points: Mapped[int | None] = mapped_column(SmallInteger)
    """Photos used in the window — and the mark of a row a lines-aware fold
    wrote: ``NULL`` exactly on rows folded before ``0026``."""

    line_reason: Mapped[str | None] = mapped_column(Text)
    """``too_few_points`` (< 5 photos) | ``no_snapshot`` | ``flat`` (no two
    local lows) | ``out_of_range`` (a value the column cannot hold)."""

    hype_score: Mapped[Decimal | None] = mapped_column(PERCENT)
    hype_reason: Mapped[str | None] = mapped_column(Text)
    """The documented weighted average of ``hunter_indicators.meme.hype``
    (buys, unique buyers, board standing, social, low snipers). ``NULL`` with
    ``no_tape_no_board`` when neither source spoke; ``partial`` sits next to a
    number when exactly one did."""

    tape_source: Mapped[str | None] = mapped_column(Text)
    tape_window_s: Mapped[int | None] = mapped_column(Integer)
    tape_as_of: Mapped[datetime | None]
    """``0032`` (T4.2g): ``swap_api_trades`` (the per-mint tape, ``tape_as_of =
    end_time``) or ``activity_1m`` (the batch route's ``1m`` window ending at
    ``tape_as_of`` ≤ 60 s before the close, only when the per-mint tape did not
    cover; buyers count the creator, who sold is unknown). ``NULL`` before ``0032``."""
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
