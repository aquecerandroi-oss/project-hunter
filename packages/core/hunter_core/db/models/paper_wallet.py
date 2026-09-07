"""The virtual wallet's two durable singletons — DATABASE.md §18.2/§18.3.

``portfolio_currency_anchor`` is the opening: the BRL the directive names, the
FX observation it was converted at, what was actually credited in the operating
currency and the conversion residue, written **once** and never edited. It is
what makes "resultado das operações separado da variação cambial" computable
years later — ``operacional_brl = (E − E0)·F0`` needs an ``E0`` and an ``F0``
that nobody has quietly moved.

``portfolio_risk_state`` is the other side: everything about a wallet that has
to survive a restart *and* be serialised against everything else touching that
wallet. It is deliberately **one row that is four things** — the portfolio lock
of the system -> organization -> portfolio order, the durable FIFO counter, the
trading-day reference in ``America/Sao_Paulo`` and the monotonic peak. Four
tables would be four locks competing over the same wallet for no gain; the joint
M3 decision serialises all four under the same lock anyway.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import org_fk, tenant_scoped_fk

SAO_PAULO = "America/Sao_Paulo"
"""The trading day's zone (RISK_ENGINE.md §5). Stored per row, not assumed."""


class PortfolioCurrencyAnchor(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """The wallet's opening conversion. One row per portfolio, immutable."""

    __tablename__ = "portfolio_currency_anchor"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        # One anchor per wallet — a second one would be a second opening, which
        # is the reset the directive forbids however it is spelled.
        UniqueConstraint("portfolio_id", name="uq_portfolio_currency_anchor_portfolio"),
        CheckConstraint("origin_amount > 0", name="origin_amount_positive"),
        CheckConstraint("credited_amount > 0", name="credited_amount_positive"),
        CheckConstraint("rate > 0", name="rate_positive"),
        CheckConstraint("conversion_residual >= 0", name="conversion_residual_not_negative"),
        # The money identity, proved by the schema: what came in equals what was
        # credited at the anchored rate plus the residue the policy left behind.
        # Rounded to the stored scale because ``credited × rate`` is a 20-decimal
        # product and the columns hold ten.
        CheckConstraint(
            "round(credited_amount * rate + conversion_residual, 10) = round(origin_amount, 10)",
            name="conversion_is_exact",
        ),
        CheckConstraint("char_length(origin_currency) > 0", name="origin_currency_not_empty"),
        CheckConstraint("char_length(operating_currency) > 0", name="operating_currency_not_empty"),
        CheckConstraint("char_length(rounding_policy) > 0", name="rounding_policy_not_empty"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(index=True)
    origin_currency: Mapped[str] = mapped_column(Text, server_default="BRL")
    origin_amount: Mapped[Decimal]
    """R$100.000 — the directive's number, in the currency it was written in.
    Never confused with the operating currency: "não confundir R$100.000 com
    100.000 USDT"."""

    operating_currency: Mapped[str] = mapped_column(Text, server_default="USDT")
    credited_amount: Mapped[Decimal]
    """``E0``: what the wallet actually received in the operating currency, which
    is what every BRL attribution is measured from."""

    fx_observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fx_observations.id", ondelete="RESTRICT"), index=True
    )
    """``RESTRICT``, not ``CASCADE``: the observation is the evidence for the
    opening, and it may not be removed while a wallet stands on it."""

    rate: Mapped[Decimal]
    """``F0``, copied from the observation and verified against it by trigger on
    insert. Duplicated on purpose: the attribution identity is a schema fact
    here (``conversion_is_exact``), and a CHECK cannot reach another table."""

    conversion_residual: Mapped[Decimal]
    """What the rounding policy could not credit, in the *origin* currency. It is
    recorded rather than absorbed, because absorbing it would make the wallet
    start at a number nobody chose."""

    rounding_policy: Mapped[str] = mapped_column(Text)
    """The declared policy that produced ``credited_amount`` from
    ``origin_amount`` and ``rate`` (e.g. ``floor_8dp_v1``)."""

    anchored_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PortfolioRiskState(Base, TenantMixin, TimestampMixin):
    """The wallet's lock row: FIFO counter, day reference and durable peak."""

    __tablename__ = "portfolio_risk_state"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        CheckConstraint("last_admission_seq >= 0", name="admission_seq_not_negative"),
        CheckConstraint("peak_equity >= 0", name="peak_equity_not_negative"),
        CheckConstraint("peak_sampling_interval_s > 0", name="peak_cadence_declared"),
        # The day reference is allowed to be *unknown* — that is a state the
        # engine must be able to represent, because failing to rebuild it blocks
        # entries and preserves protections rather than inventing a midnight
        # equity out of the first price seen after a restart.
        CheckConstraint(
            "(equity_day_start IS NULL) = (day_reference_observed_at IS NULL)",
            name="day_reference_is_all_or_nothing",
        ),
        CheckConstraint(
            "(trading_day IS NULL) = (trading_day_start_utc IS NULL)",
            name="trading_day_is_all_or_nothing",
        ),
        CheckConstraint(
            "equity_day_start IS NULL OR trading_day IS NOT NULL",
            name="day_equity_belongs_to_a_day",
        ),
        CheckConstraint(
            "equity_day_start IS NULL OR equity_day_start >= 0",
            name="day_equity_not_negative",
        ),
        CheckConstraint(
            "char_length(trading_day_timezone) > 0", name="trading_day_timezone_not_empty"
        ),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    """The primary key, so "one row per wallet" is a key and not a convention.
    It is also the row every admission, expiry and kill-switch evaluation takes
    ``FOR UPDATE`` on — a row lock, never a session advisory lock, because the
    transaction pooler makes session state unusable (DATABASE.md §1.2)."""

    last_admission_seq: Mapped[int] = mapped_column(BigInteger, server_default="0")
    """``fifo_v1``. Incremented under the row lock, so it is commit order by
    construction. Deliberately **not** a Postgres ``SEQUENCE``: a sequence has
    gaps on rollback and its order is not commit order — transaction A can take
    10, B take 11 and commit first (the same argument §16.4 makes about
    ``outbox_events.id``), and admission order is a promise to the operator."""

    trading_day: Mapped[date | None] = mapped_column(Date)
    trading_day_timezone: Mapped[str] = mapped_column(Text, server_default=SAO_PAULO)
    """Recorded per row rather than assumed. There is deliberately **no CHECK**
    proving ``trading_day_start_utc`` is midnight of ``trading_day`` in this
    zone: ``timezone(text, timestamp)`` is catalogued IMMUTABLE, but the zone
    database behind it is not frozen, so a tzdata correction could make an
    existing row fail on an unrelated ``UPDATE`` or on restore. The conversion is
    validated once, at the turn of the day, and the resolved instant is what is
    stored (Astra, review of this design)."""

    trading_day_start_utc: Mapped[datetime | None]
    equity_day_start: Mapped[Decimal | None]
    day_reference_observed_at: Mapped[datetime | None]
    """The *real* instant the reference was evaluated. Evaluating at 03:17 does
    not make the equity of 03:17 the equity of midnight, and this column is what
    makes that visible instead of assumed (RISK_ENGINE.md §5)."""

    peak_equity: Mapped[Decimal]
    peak_equity_at: Mapped[datetime]
    peak_sampling_interval_s: Mapped[int] = mapped_column(Integer, server_default="60")
    """The declared cadence. The peak is *sampled*, not the intratick maximum,
    and the contract says so instead of implying a precision we do not have."""
