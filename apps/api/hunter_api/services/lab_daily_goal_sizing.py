"""Value of 1R, real and label — pure arithmetic (brief T3.78, item 1).

Reuses ``hunter_risk``'s own thresholds and cost formula rather than
re-declaring them: ``PAPER_V1.max_participation_pct`` and
``PAPER_V1.risk_per_trade_pct`` are the frozen profile
(``packages/risk-core/hunter_risk/limits.py``), and
``round_trip_cost_fraction`` is the same function ``size_entry`` calls.

**What is deliberately *not* reused.**
``hunter_risk.sizing.stop_distance_fraction`` assumes a long (it raises when
``stop >= entry_ref``); a day's bets are a mix of longs and shorts, so this
module measures the distance itself, direction-agnostically
(``abs(entry - stop) / entry``) — the formula is arithmetic, not a threshold,
and nothing here overrides what the engine decided a ceiling *is*.

**One ceiling pair, not the whole engine.** The brief asks for "real 1-minute
volumes ... under ``max_participation_pct``" — the ceiling T3.60 found
binding in 164/176 markets — plus the ``risk_per_trade`` budget the
participation ceiling is compared against. Book depth, aggregate risk,
per-asset/total exposure and beta are portfolio-state ceilings that need the
day's whole concurrent-position history to evaluate (``t360/carteira.py``'s
job, not a per-request read endpoint's); leaving them out only ever makes
``real_brl`` an *upper* bound on the money a full simulation would find,
consistent with T3.60 §9's own "os números são teto superior" caveat. Declared
in ``notes-T3.78.md`` CONCERN 2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, localcontext

from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.numeric import CONTEXT
from hunter_risk.limits import PAPER_V1
from hunter_risk.sizing import round_trip_cost_fraction

__all__ = [
    "LABEL_REFERENCE_EQUITY_BRL",
    "BetPricingInput",
    "BetPricingResult",
    "label_brl",
    "percentile",
    "price_bet",
    "sum_priced_bets",
    "usdt_to_brl",
]

LABEL_REFERENCE_EQUITY_BRL = Decimal("100000")
"""The onboarding label's reference capital (``docs/PRODUCT.md`` §3: "R$100.000
convertidos em USDT") — fixed, independent of any organization's real equity."""

_ZERO = Decimal(0)


def sum_priced_bets(bets: list[tuple[Decimal | None, Decimal | None]]) -> Decimal | None:
    """Sum each r_net outcome at its own size; never report a partial total.

    Funding-null outcomes remain excluded, exactly as in the R axis. A
    missing size for an evaluable outcome makes the total unavailable.
    """
    with localcontext(CONTEXT):
        total = _ZERO
        for r, value_1r in bets:
            if r is None:
                continue
            if value_1r is None:
                return None
            total += r * value_1r
        return total


@dataclass(frozen=True, slots=True)
class BetPricingInput:
    virtual_entry: Decimal | None
    virtual_stop: Decimal | None
    assumed_costs_raw: dict[str, object] | None
    """``signal_outcomes.meta["assumed_costs"]`` — validated here, not at the
    repository, so a malformed envelope becomes a priced-``None`` reason
    instead of a 500."""
    quote_volume: Decimal | None
    """1-minute ``candles.quote_volume`` at/just before entry."""


@dataclass(frozen=True, slots=True)
class BetPricingResult:
    value_1r_usdt: Decimal | None
    reason: str | None
    binding: str | None = None
    """``"market_participation"`` or ``"risk_per_trade"`` — which ceiling
    capped the notional, when priced."""


def _stop_distance_fraction(entry: Decimal, stop: Decimal) -> Decimal:
    """``|entry - stop| / entry`` — see the module docstring for why this is
    not ``hunter_risk.sizing.stop_distance_fraction``."""
    with localcontext(CONTEXT):
        return abs(entry - stop) / entry


def price_bet(inputs: BetPricingInput, *, equity_usdt: Decimal) -> BetPricingResult:
    """The money value of 1R for one bet, or ``None`` with why not."""
    if inputs.virtual_entry is None or inputs.virtual_stop is None or inputs.virtual_entry <= 0:
        return BetPricingResult(None, "no_entry_or_stop")
    if inputs.quote_volume is None:
        return BetPricingResult(None, "no_volume")
    if inputs.assumed_costs_raw is None:
        return BetPricingResult(None, "no_cost_assumption")
    try:
        costs = AssumedCosts.model_validate(inputs.assumed_costs_raw)
    except ValueError:
        return BetPricingResult(None, "invalid_cost_assumption")
    with localcontext(CONTEXT):
        loss_fraction = _stop_distance_fraction(
            inputs.virtual_entry, inputs.virtual_stop
        ) + round_trip_cost_fraction(costs)
        if loss_fraction <= _ZERO:
            return BetPricingResult(None, "non_positive_loss_fraction")
        participation_notional = PAPER_V1.max_participation_pct * inputs.quote_volume
        risk_budget_notional = equity_usdt * PAPER_V1.risk_per_trade_pct / loss_fraction
        if participation_notional <= risk_budget_notional:
            value_1r_usdt, binding = participation_notional * loss_fraction, "market_participation"
        else:
            value_1r_usdt, binding = equity_usdt * PAPER_V1.risk_per_trade_pct, "risk_per_trade"
    return BetPricingResult(value_1r_usdt, None, binding)


def usdt_to_brl(value_usdt: Decimal, rate: Decimal) -> Decimal:
    """A USDT amount converted by one observed ``fx_observations.rate``
    (brief T3.78b, Everton 2026-09-10: profit is real in USDT first, then in
    BRL by the *observed* rate — never a guessed one). Exact ``Decimal``
    multiplication; no rounding to the cent here — that is the caller's
    display concern, not this module's arithmetic."""
    with localcontext(CONTEXT):
        return value_usdt * rate


def label_brl() -> Decimal:
    """``risk_per_trade_pct x R$100.000`` — the onboarding promise, never the
    real money (``docs/RISK_ENGINE.md`` §4)."""
    return PAPER_V1.risk_per_trade_pct * LABEL_REFERENCE_EQUITY_BRL


def percentile(values: list[Decimal], pct: Decimal) -> Decimal:
    """Nearest-rank percentile over a non-empty ``Decimal`` population.

    Deterministic and dependency-free (no NumPy for a handful of values):
    ``rank = ceil(pct x n)``, clamped to ``[1, n]`` — the population
    percentile, not an interpolated one, matching what a client reading "p50
    of 5 numbers" expects to be able to recompute by hand.
    """
    if not values:
        raise ValueError("percentile of an empty population is undefined")
    ordered = sorted(values)
    n = len(ordered)
    rank = max(1, min(n, math.ceil(pct * n)))
    return ordered[rank - 1]
