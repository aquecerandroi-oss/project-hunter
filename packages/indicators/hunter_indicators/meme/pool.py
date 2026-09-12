"""Pricing a paper position **after the migration** — against the PumpSwap
pool's tape, not the curve (T4.11, EXP-M4: "colocar valores mais altos para
sair num mega ROI, meme coin é diferente").

Once a mint migrates, ``meme_curve_snapshots`` stop being the venue: the curve
is emptied and the token trades on the canonical PumpSwap pool. The only free
observation of that pool this project has is the ``swap-api`` tape
(``meme_trades`` rows with ``program = 'pump_amm'``), so the honest mark of a
position that held through the migration is **the last trade's price, minus
what our own sale would cost**:

1. **Impact by participation.** Our size (tokens × last price) divided by the
   pool's SOL volume of the last five minutes, capped at ``IMPACT_CAP_PCT``
   (1 %). A window with no volume does not make the impact zero: it is the
   cap, and the quote says why (``impact_reason = no_volume_5m``).
2. **The fee of the PumpSwap tier the market cap is in right now** —
   ``pump.fun/docs/fees`` ("Last Updated: 20 May 2026", ``docs/PUMPFUN.md``
   §4.1): 1,25 % just after graduation, falling by market-cap band down to
   0,30 % at ≥ 98 240 SOL. Never the flat 0,30 % of a non-canonical pool, and
   never a tier read off yesterday's cap.
3. **The path's own fee on top** (``path_fee_pct``): the doctrine's "o papel
   nunca simula um caminho mais barato do que o live vai usar"
   (``docs/RISK_ENGINE_MEME.md`` §10.2) — the PumpPortal local path charges
   0,5 % on the pool exactly as on the curve.

Everything here is pure ``Decimal`` under ``CONTEXT``; nothing reads a clock
or a table. Non-anticipation belongs to the caller **and** to
:func:`trades_known_by`: a trade received after the instant being judged is
not a trade that instant could see.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Final

from hunter_core.domain.enums import FeatureCategory
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.definitions import FeatureDefinition

__all__ = [
    "IMPACT_CAP_PCT",
    "NO_VOLUME_5M",
    "POOL_DEFINITIONS",
    "POOL_FEE_FLOOR_PCT",
    "POOL_FEE_TIERS_SOL",
    "VOLUME_WINDOW",
    "PoolSellQuote",
    "PoolTrade",
    "last_trade_at_or_before",
    "participation_impact_pct",
    "pool_fee_pct",
    "quote_pool_sell",
    "trades_known_by",
    "volume_sol",
]

HUNDRED: Final = Decimal(100)

POOL_FEE_TIERS_SOL: Final[tuple[tuple[Decimal, Decimal], ...]] = (
    (Decimal(420), Decimal("1.250")),
    (Decimal(1470), Decimal("1.200")),
    (Decimal(2460), Decimal("1.150")),
    (Decimal(3440), Decimal("1.100")),
    (Decimal(4420), Decimal("1.050")),
    (Decimal(9820), Decimal("1.000")),
    (Decimal(14740), Decimal("0.950")),
    (Decimal(19650), Decimal("0.900")),
    (Decimal(24560), Decimal("0.850")),
    (Decimal(29470), Decimal("0.800")),
    (Decimal(34380), Decimal("0.750")),
    (Decimal(39300), Decimal("0.700")),
    (Decimal(44210), Decimal("0.650")),
    (Decimal(49120), Decimal("0.600")),
    (Decimal(54030), Decimal("0.550")),
    (Decimal(58940), Decimal("0.525")),
    (Decimal(63860), Decimal("0.500")),
    (Decimal(68770), Decimal("0.475")),
    (Decimal(73681), Decimal("0.450")),
    (Decimal(78590), Decimal("0.425")),
    (Decimal(83500), Decimal("0.400")),
    (Decimal(88400), Decimal("0.375")),
    (Decimal(93330), Decimal("0.350")),
    (Decimal(98240), Decimal("0.325")),
)
"""``(upper bound of the band in SOL of market cap, exclusive; total fee %)``,
canonical PumpSwap pool with SOL quote — creator + protocol + LP. Copied from
``docs/PUMPFUN.md`` §4.1 (``pump.fun/docs/fees``, 20 May 2026); a fee that
ever disagrees with a real fill is a **new version** of this table."""

POOL_FEE_FLOOR_PCT: Final = Decimal("0.300")
"""At or above 98 240 SOL of market cap: 0,05 creator + 0,05 protocol + 0,20 LP."""

IMPACT_CAP_PCT: Final = Decimal(1)
VOLUME_WINDOW: Final = timedelta(minutes=5)
NO_VOLUME_5M: Final = "no_volume_5m"

_INPUTS: Final = (
    "meme_trades.block_time",
    "meme_trades.received_at",
    "meme_trades.sol_lamports",
    "meme_trades.token_amount",
    "meme_trades.program",
    "meme_tokens.total_supply",
)

POOL_DEFINITIONS: Final[tuple[FeatureDefinition, ...]] = (
    FeatureDefinition(
        key="pool_fee_tier_pct",
        version=1,
        category=FeatureCategory.MICROSTRUCTURE,
        inputs=_INPUTS,
        description=(
            "Total PumpSwap canonical-pool fee (%) of the market-cap band the last trade's "
            "price × total_supply falls in (pump.fun/docs/fees, 2026-05-20)."
        ),
        params={"bands": len(POOL_FEE_TIERS_SOL) + 1, "floor_pct": str(POOL_FEE_FLOOR_PCT)},
    ),
    FeatureDefinition(
        key="pool_impact_pct",
        version=1,
        category=FeatureCategory.MICROSTRUCTURE,
        inputs=_INPUTS,
        description=(
            "Estimated price impact (%) of selling the position: min(size_sol / SOL volume of "
            "the last 5 minutes × 100, cap); the cap with a reason when the window has no volume."
        ),
        params={"window_minutes": 5, "cap_pct": str(IMPACT_CAP_PCT)},
    ),
    FeatureDefinition(
        key="pool_mark_sol",
        version=1,
        category=FeatureCategory.PRICE,
        inputs=_INPUTS,
        description=(
            "What a full sell would net now on the pool: tokens × last trade price × (1 − "
            "impact) × (1 − tier fee − path fee). Only trades received by the instant judged."
        ),
        params={"window_minutes": 5, "cap_pct": str(IMPACT_CAP_PCT)},
    ),
)


@dataclass(frozen=True, slots=True)
class PoolTrade:
    """One pool trade as the mark reads it: the two clocks, the side, the size."""

    block_time: datetime
    received_at: datetime
    side: str
    sol: Decimal
    tokens: Decimal

    def __post_init__(self) -> None:
        if self.sol < 0:
            raise ValueError("sol cannot be negative")
        if self.tokens <= 0:
            raise ValueError("tokens must be positive")

    @property
    def price_sol(self) -> Decimal:
        """SOL per token of this fill — recomputed from the exact amounts, never
        read from the source's rounded price column."""
        with localcontext(CONTEXT):
            return self.sol / self.tokens


@dataclass(frozen=True, slots=True)
class PoolSellQuote:
    """What a full sell of ``tokens`` would net on the pool, and every deduction."""

    tokens: Decimal
    price_sol: Decimal
    gross_sol: Decimal
    mcap_sol: Decimal
    volume_5m_sol: Decimal
    impact_pct: Decimal
    impact_reason: str | None
    impact_sol: Decimal
    tier_fee_pct: Decimal
    path_fee_pct: Decimal
    fee_sol: Decimal
    net_sol: Decimal


def pool_fee_pct(mcap_sol: Decimal) -> Decimal:
    """The canonical pool's total fee (%) for a market cap in SOL."""
    if mcap_sol < 0:
        raise ValueError("mcap_sol cannot be negative")
    for upper, fee in POOL_FEE_TIERS_SOL:
        if mcap_sol < upper:
            return fee
    return POOL_FEE_FLOOR_PCT


def trades_known_by(trades: Sequence[PoolTrade], until: datetime) -> list[PoolTrade]:
    """The trades an instant could see: ``received_at <= until``, tape order."""
    return sorted(
        (t for t in trades if t.received_at <= until), key=lambda t: (t.block_time, t.received_at)
    )


def last_trade_at_or_before(trades: Sequence[PoolTrade], at: datetime) -> PoolTrade | None:
    """The newest trade whose ``block_time <= at`` — the price a mark at ``at`` uses."""
    usable = [t for t in trades if t.block_time <= at]
    return max(usable, key=lambda t: t.block_time) if usable else None


def volume_sol(
    trades: Sequence[PoolTrade], *, at: datetime, window: timedelta = VOLUME_WINDOW
) -> Decimal:
    """SOL traded in ``(at − window, at]`` — buys and sells, both sides count."""
    with localcontext(CONTEXT):
        return sum((t.sol for t in trades if at - window < t.block_time <= at), Decimal(0))


def participation_impact_pct(
    size_sol: Decimal, volume_5m_sol: Decimal, *, cap_pct: Decimal = IMPACT_CAP_PCT
) -> tuple[Decimal, str | None]:
    """``min(size / volume × 100, cap)`` and, when the window is empty, the cap **named**."""
    if size_sol < 0:
        raise ValueError("size_sol cannot be negative")
    if volume_5m_sol <= 0:
        return cap_pct, NO_VOLUME_5M
    with localcontext(CONTEXT):
        share = HUNDRED * size_sol / volume_5m_sol
        return min(share, cap_pct), None


def quote_pool_sell(
    tokens: Decimal,
    price_sol: Decimal,
    *,
    volume_5m_sol: Decimal,
    total_supply: Decimal,
    path_fee_pct: Decimal,
) -> PoolSellQuote:
    """Price a full sell of ``tokens`` at the last trade's ``price_sol``.

    ``gross = tokens × price``; the impact is charged on the gross, the fees
    (the market-cap tier of **this** price plus the execution path's) on what
    is left after the impact — the order a real fill deducts them in.
    """
    if tokens <= 0:
        raise ValueError("tokens must be positive")
    if price_sol <= 0:
        raise ValueError("price_sol must be positive")
    if total_supply <= 0:
        raise ValueError("total_supply must be positive")
    if path_fee_pct < 0:
        raise ValueError("path_fee_pct cannot be negative")
    with localcontext(CONTEXT):
        gross = tokens * price_sol
        mcap = price_sol * total_supply
        impact_pct, reason = participation_impact_pct(gross, volume_5m_sol)
        impact_sol = gross * impact_pct / HUNDRED
        after_impact = gross - impact_sol
        tier = pool_fee_pct(mcap)
        fee_sol = after_impact * (tier + path_fee_pct) / HUNDRED
        return PoolSellQuote(
            tokens=tokens,
            price_sol=price_sol,
            gross_sol=gross,
            mcap_sol=mcap,
            volume_5m_sol=volume_5m_sol,
            impact_pct=impact_pct,
            impact_reason=reason,
            impact_sol=impact_sol,
            tier_fee_pct=tier,
            path_fee_pct=path_fee_pct,
            fee_sol=fee_sol,
            net_sol=after_impact - fee_sol,
        )
