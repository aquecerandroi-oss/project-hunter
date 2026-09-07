"""``fx_observations`` — the exchange rates the BRL wallet is anchored to.

Global and immutable (DATABASE.md §1.1/§18.2). The directive says the wallet
starts at R$100.000 and, if the engine operates in USDT, that the opening
conversion records *the rate and its source*; the joint M3 decision turns that
into a rule with teeth: every point of the equity curve names the observation it
used, and **the past is never recomputed with today's rate**. That is only true
if an observation is written once and never edited, which is what the
``fx_observations_immutable`` trigger enforces for every role, owner included.

``available_at`` is the second timestamp and the one that makes replay honest:
``observed_at`` is when the venue says the rate held, ``available_at`` is when
*we* could have acted on it. A decision at 10:00 may not be explained by a rate
that only reached us at 10:02 — the same causal cut ``feature_baselines`` uses
(§17.2).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin


class FxObservation(Base, UUIDPrimaryKeyMixin):
    """One observed FX rate, with its provenance and the raw response behind it."""

    __tablename__ = "fx_observations"
    __table_args__ = (
        # A retry of the same poll collides and is a no-op; a genuinely new
        # observation carries a new ``observed_at``. Source is in the key
        # because two venues quoting the same pair at the same instant are two
        # observations, not a contradiction to be silently resolved.
        UniqueConstraint("pair", "source", "observed_at", name="uq_fx_observations_observation"),
        Index("ix_fx_observations_lookup", "pair", "available_at"),
        CheckConstraint("rate > 0", name="rate_positive"),
        CheckConstraint("observed_at <= available_at", name="observation_is_causal"),
        CheckConstraint("char_length(pair) > 0", name="pair_not_empty"),
        CheckConstraint("char_length(source) > 0", name="source_not_empty"),
    )

    pair: Mapped[str] = mapped_column(Text)
    """``USDTBRL``. Text and not an enum: the set of pairs is open in value."""

    rate: Mapped[Decimal]
    """Units of the quote currency per unit of the base — ``NUMERIC(28,10)``,
    because this multiplies money and a float here would round the wallet."""

    source: Mapped[str] = mapped_column(Text)
    """Who said so, concretely (``binance.spot.ticker``). A rate without a named
    source cannot open the wallet: "fonte inválida não abre" (T3.11)."""

    observed_at: Mapped[datetime]
    available_at: Mapped[datetime]
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """The provider's response as it arrived. Kept because "registrar a cotação e
    a fonte" is only auditable if the thing that was parsed survives too."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
