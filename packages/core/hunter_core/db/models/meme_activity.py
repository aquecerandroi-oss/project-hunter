"""``meme_market_activity_1m`` — one coin over one window, as the ``swap-api``
batch route counted it, once a minute (DATABASE.md §44, revision
``0032_meme_activity``, T4.2g).

**Why a second tape.** The per-mint tape (``meme_trades``, ``swap-api
/v2/coins/{mint}/trades``) costs one request per coin per minute, and the
host's real limit is Cloudflare's ~20 requests per 60 s per IP (T4.2f): with
~130 tracked coins the tape could cover ~40 % of the gate's rows a minute,
and the flow gate (``flow_v2/1``, EXP-M5) refused ~100 of ~110 young coins a
tick as ``buyers_unknown``/``sells_ratio_unknown``/``flow_not_polled``. The
batch route (``POST /v1/coins/market-activity/batch``) counts **50 coins per
request**: three requests a minute cover the whole tracked set, and the rows
here are what those requests said — buys, sells, distinct buyers and sellers,
USD volumes per window — with the instant the windows end (``end_time`` = the
response's ``Date``) and the instant we received them.

**What a row does not say, kept honest by construction.** The route gives
volumes in **USD**; the SOL columns are derived with the SOL/USD quote the
worker held (``sol_usd``, ``sol_usd_observed_at``), and are ``NULL`` together
when it held none. A window the route answered ``null`` for is a row with
``empty = true`` and zeros — written **only** when the same cycle's responses
filled that window for some coin (the proof that the window is computed);
otherwise nothing is written and the heartbeat says the window was dark.
The route never says *who* traded: ``unique_buyers`` counts the creator, and
``creator_net_seller`` in the features stays ``no_trade_feed`` when only the
batch spoke.

**Global** (§1.1), monthly ``RANGE`` on ``end_time`` (§1.3), retention
**30 days** (``partition_retention.py``): two windows × ~130 coins × 1 440
minutes is ~375 k rows a day, and the minute's features keep the numbers the
gate judged for the full ``MEME_RETENTION_DAYS``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base
from hunter_core.db.models._common import SQL_FALSE

ACTIVITY_SOURCE = "swap_api:market-activity/batch"
ACTIVITY_WINDOWS: tuple[str, ...] = ("1m", "5m", "1h", "6h", "24h")
"""The intervals the route's validator accepts (T4.2g probe); the worker asks for ``1m`` and ``5m``."""


class MemeMarketActivity1m(Base):
    """One coin over one window at one instant, as the batch route counted it."""

    __tablename__ = "meme_market_activity_1m"
    __table_args__ = (
        Index("ix_meme_market_activity_1m_mint_end_time", "mint", "end_time"),
        CheckConstraint(
            "window_name IN ('1m', '5m', '1h', '6h', '24h')",
            name="window_is_a_known_label",
        ),
        CheckConstraint("window_s > 0", name="window_has_a_length"),
        CheckConstraint(
            "num_txs >= 0 AND buys >= 0 AND sells >= 0 AND unique_users >= 0 "
            "AND unique_buyers >= 0 AND unique_sellers >= 0",
            name="counts_are_not_negative",
        ),
        CheckConstraint(
            "volume_usd >= 0 AND buy_volume_usd >= 0 AND sell_volume_usd >= 0",
            name="volumes_are_not_negative",
        ),
        CheckConstraint(
            "(sol_usd IS NULL) = (sol_usd_observed_at IS NULL) "
            "AND (sol_usd IS NULL) = (buy_volume_sol IS NULL) "
            "AND (sol_usd IS NULL) = (sell_volume_sol IS NULL)",
            name="sol_figures_name_their_quote",
        ),
        CheckConstraint("sol_usd IS NULL OR sol_usd > 0", name="quote_is_positive"),
        CheckConstraint(
            "NOT empty OR (num_txs = 0 AND buys = 0 AND sells = 0 AND volume_usd = 0)",
            name="an_empty_window_is_all_zeros",
        ),
        CheckConstraint(
            "char_length(mint) > 0 AND char_length(source) > 0", name="provenance_is_not_empty"
        ),
        {"postgresql_partition_by": "RANGE (end_time)"},
    )

    end_time: Mapped[datetime] = mapped_column(primary_key=True)
    """The instant the window ends — the response's ``Date`` header, second
    precision (the route carries no timestamp of its own). Partition key,
    first in the PK (§15.2)."""

    mint: Mapped[str] = mapped_column(Text, primary_key=True)
    window_name: Mapped[str] = mapped_column(Text, primary_key=True)
    """``1m`` | ``5m`` | ``1h`` | ``6h`` | ``24h`` — the interval as the route names it."""

    window_s: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime]
    """When the response reached us — what non-anticipation is judged on."""

    source: Mapped[str] = mapped_column(Text, server_default=ACTIVITY_SOURCE)
    empty: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    """``true``: the route answered ``null`` for the window (no trade in it) and
    the same cycle filled that window for another coin — a stated zero."""

    num_txs: Mapped[int] = mapped_column(Integer)
    buys: Mapped[int] = mapped_column(Integer)
    sells: Mapped[int] = mapped_column(Integer)
    unique_users: Mapped[int] = mapped_column(Integer)
    unique_buyers: Mapped[int] = mapped_column(Integer)
    """Distinct buyers, the creator **included** — the route does not say who."""
    unique_sellers: Mapped[int] = mapped_column(Integer)

    volume_usd: Mapped[Decimal]
    buy_volume_usd: Mapped[Decimal]
    sell_volume_usd: Mapped[Decimal]
    """USD, as delivered — the route's own currency."""

    price_change_pct: Mapped[Decimal | None]
    """``priceChangePercent`` as the route says it (a percent, signed); ``NULL``
    on an empty window."""

    sol_usd: Mapped[Decimal | None]
    sol_usd_observed_at: Mapped[datetime | None]
    buy_volume_sol: Mapped[Decimal | None]
    sell_volume_sol: Mapped[Decimal | None]
    """USD ÷ ``sol_usd`` — derived, and the quote that derived them sits beside
    them; ``NULL`` together when the worker held no quote younger than five minutes."""


__all__ = ["ACTIVITY_SOURCE", "ACTIVITY_WINDOWS", "MemeMarketActivity1m"]
