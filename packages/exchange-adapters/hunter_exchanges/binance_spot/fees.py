"""Binance **SPOT** trading fees: the rate, its source, and the policy.

``docs/plans/M3.md`` T3.0: "fee SPOT com fonte e política declaradas, nunca
herdada de futuros". The two schedules are genuinely different and the spot
one is the expensive one, so inheriting the USDS-M numbers would understate
every simulated cost:

============================  ========  ========  ==================================
Schedule                        Maker     Taker    Source
============================  ========  ========  ==================================
Spot, VIP 0, no BNB            0.1000%   0.1000%  Binance spot fee schedule (VIP 0)
Spot, VIP 0, BNB deduction     0.0750%   0.0750%  25% BNB discount on the above
USDS-M Futures, VIP 0          0.0200%   0.0500%  a *different* product - never here
============================  ========  ========  ==================================

**Policy (declared, T3.0a).** The paper wallet's default is
:data:`SPOT_VIP0` - 0.1% both sides, **no BNB deduction**: the portfolio
holds no BNB, and assuming a discount we do not have would make every
simulated result better than reality. :data:`SPOT_VIP0_BNB` exists so the
choice is explicit if BNB is ever funded, never as a silent default. A VIP
level above 0 is not assumed either: the wallet's volume is R$100.000, far
below any tier.

**This is not the Lab's ``AssumedCosts``.** ``hunter_core.strategies.envelope.AssumedCosts``
(``spread_bps``/``slippage_bps``/``fee_bps``/``max_entry_delay_s``) is the
*declared hypothesis* of a shadow experiment, frozen with the strategy
version so a hypothetical R stays comparable over time. What is here is the
exchange's **published fee** for the venue the paper wallet actually
executes on. They must not be conflated: T3.4 may read this rate to *choose*
a ``fee_bps``, but an experiment's frozen hypothesis never changes because
Binance updated a fee schedule (and vice versa).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal

__all__ = ["SPOT_VIP0", "SPOT_VIP0_BNB", "SpotFeeSchedule", "fee_for"]


@dataclass(frozen=True)
class SpotFeeSchedule:
    """One fee schedule, with the provenance that makes it auditable."""

    maker_rate: Decimal
    taker_rate: Decimal
    bnb_deduction: bool
    source: str
    as_of: date

    @property
    def taker_bps(self) -> Decimal:
        return self.taker_rate * 10_000

    @property
    def maker_bps(self) -> Decimal:
        return self.maker_rate * 10_000


SPOT_VIP0 = SpotFeeSchedule(
    maker_rate=Decimal("0.001"),
    taker_rate=Decimal("0.001"),
    bnb_deduction=False,
    source="Binance spot trading fee schedule, VIP 0 (Regular User), no BNB deduction",
    as_of=date(2026, 9, 6),
)

SPOT_VIP0_BNB = SpotFeeSchedule(
    maker_rate=Decimal("0.00075"),
    taker_rate=Decimal("0.00075"),
    bnb_deduction=True,
    source="Binance spot trading fee schedule, VIP 0 with the 25% BNB deduction",
    as_of=date(2026, 9, 6),
)

#: What the paper wallet uses unless someone changes it deliberately.
DEFAULT_SCHEDULE = SPOT_VIP0


def fee_for(
    notional: Decimal,
    *,
    liquidity: str = "taker",
    schedule: SpotFeeSchedule = DEFAULT_SCHEDULE,
    quote_precision: int = 8,
) -> Decimal:
    """Fee in quote currency (USDT) for ``notional``, rounded **up**.

    ``ROUND_CEILING``, not half-up (Astra diff review): a cost rounded to the
    nearest cent is a cost that is sometimes cheaper than reality, and this
    number feeds a simulated result. Sub-cent either way, but the direction
    is the point.

    ``liquidity`` is ``"taker"`` (a MARKET order, the only kind the paper
    wallet sends) or ``"maker"``.
    """
    if liquidity not in ("taker", "maker"):
        raise ValueError(f"liquidity must be 'taker' or 'maker', got {liquidity!r}")
    rate = schedule.taker_rate if liquidity == "taker" else schedule.maker_rate
    quantum = Decimal(1).scaleb(-quote_precision)
    return (notional * rate).quantize(quantum, rounding=ROUND_CEILING)
