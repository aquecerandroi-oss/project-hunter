"""The size: nine ceilings, the smallest one wins, and it is a ceiling.

    price (every line below)          = max(entry_ref, preco observado) - the worse one
    planned loss per unit of notional = |price - stop| / price + round-trip costs
    risk ceiling                      = equity x risk_per_trade_pct / that
    aggregate ceiling                 = remaining aggregate risk budget / that
    participation ceiling             = 1 % x min(last complete minute, median of 30) - used
    book ceiling                      = deepest walk of the ask side inside max_slippage_pct,
                                        in units, then priced at that price
    per-coin ceiling                  = 10 % x equity - exposure on that coin
    total ceiling                     = 40 % x equity - total exposure
    beta ceiling                      = (50 % x equity - sum|notional x beta|) / |beta|
    cash ceiling                      = (cash - reservas) / ((1 + deslocamento) x (1 + fee))
    requested ceiling                 = what the caller asked for, if it asked

    notional = min(ceilings) x kill_switch_multiplier
    qty      = floor_to_step(notional / max(entry_ref, preco observado))

Four properties that are the point of this module:

- **the multiplier comes last** (``R-KS-1``). The old contract multiplied the
  *risk budget*, so a proposal whose binding ceiling was participation or the
  book came out of ``WARNING`` exactly the same size while the panel claimed
  "half size". Here it scales the winner, whichever it was;
- **a ceiling is never a target** (directive §2). Nothing in this file ever
  raises a size towards the risk budget, and ``stop`` is copied from the
  proposal and never moved. A stop widened to fit a size would be a protection
  the engine invented and then reported;
- **rounding is always down**. Rounding a quantity up to the step is how a
  computed 9.9997 % becomes 10.0004 % of a limit that was just checked;
- **the price is the worse of the two** (review of 2026-09-06, finding 2). Every
  ceiling, the planned loss and the counterfactuals are measured at
  ``max(entry_ref, preco observado)``, so a reference that the market has left
  behind can never make a ceiling more generous than the market itself. Whether
  the proposal is admissible at all, with that gap, is the ``signal_validity``
  check's answer, not this module's.

Costs use the same hypothesis as the shadow lab
(``services/strategy-worker/hunter_strategy_worker/pricing.py``): half the
spread plus slippage on each leg, plus the fee on each leg. They are added to
the *planned loss*, not to ``entry_ref`` - adding them to both would charge the
entry twice.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from hunter_core.domain.types import quantize
from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.numeric import CONTEXT
from hunter_risk.decision import Counterfactual, LimitCap, Sizing
from hunter_risk.exposure import PortfolioState
from hunter_risk.inputs import BetaEstimate, EntryProposal, MarketLiquidity, MarketSpec
from hunter_risk.limits import RiskLimits
from hunter_risk.observations import book_capacity_qty, worst_entry_price

_ZERO = Decimal(0)
_ONE = Decimal(1)
_TWO = Decimal(2)
_BPS = Decimal(10000)

CAP_ORDER = (
    "requested",
    "risk_per_trade",
    "aggregate_risk",
    "market_participation",
    "book_depth",
    "asset_exposure",
    "total_exposure",
    "beta_exposure",
    "cash",
)
"""Declaration order; also the tie-break, so equal ceilings always name the same
winner and two runs of the same case never disagree about ``binding_limit``."""


def round_trip_cost_fraction(costs: AssumedCosts) -> Decimal:
    """Both legs of the declared cost hypothesis, as a fraction of notional."""
    with localcontext(CONTEXT):
        per_leg = costs.spread_bps / _TWO + costs.slippage_bps + costs.fee_bps
        return _TWO * per_leg / _BPS


def entry_cash_multiplier(costs: AssumedCosts) -> Decimal:
    """What one unit of reference notional actually costs the cash balance.

    ``(1 + deslocamento) x (1 + fee)``, not ``1 + deslocamento + fee``. The fee
    is charged on the **executed** price, so the product term is real money:
    with a 1 % displacement and a 1 % fee, the additive form authorises a
    reference notional of 100 against a cash balance of 102 and the order then
    needs 102.01. On spot the cash is the hard limit, so the ceiling is exact
    rather than first-order (Astra, diff review of T3.1).
    """
    with localcontext(CONTEXT):
        displacement = (costs.spread_bps / _TWO + costs.slippage_bps) / _BPS
        fee = costs.fee_bps / _BPS
        return (_ONE + displacement) * (_ONE + fee)


def stop_distance_fraction(entry_ref: Decimal, stop: Decimal) -> Decimal:
    """``(entry_ref - stop) / entry_ref`` for a long. Refuses a stop that is not below."""
    if stop >= entry_ref:
        raise ValueError(
            f"stop {stop} is not below the entry reference {entry_ref}: a long whose stop is "
            "at or above the entry has no risk to divide by"
        )
    with localcontext(CONTEXT):
        return (entry_ref - stop) / entry_ref


def floor_to_step(qty: Decimal, step: Decimal) -> Decimal:
    """Round **down** to a multiple of the exchange's step size."""
    return quantize(qty, step)


def _cap(name: str, notional: Decimal | None, limit: Decimal | None, detail: str) -> LimitCap:
    floored = None if notional is None else max(_ZERO, notional)
    return LimitCap(name=name, notional=floored, limit=limit, detail=detail)


def _ceilings(
    *,
    proposal: EntryProposal,
    portfolio: PortfolioState,
    limits: RiskLimits,
    liquidity: MarketLiquidity,
    beta: BetaEstimate,
    loss_per_unit: Decimal,
    cash_multiplier: Decimal,
) -> tuple[LimitCap, ...]:
    equity = portfolio.equity
    price = worst_entry_price(proposal, liquidity)
    reference = liquidity.participation_reference
    mid = liquidity.reference_mid
    beta_used = portfolio.beta_exposure()
    if reference is None or mid is None or beta_used is None:
        raise ValueError(
            "size_entry needs a participation reference, a mid price and a known beta "
            "aggregate; evaluate() must reject before sizing when any of them is missing"
        )

    available_cash = portfolio.available_cash

    with localcontext(CONTEXT):
        risk_budget = equity * limits.risk_per_trade_pct
        aggregate_room = (
            equity * limits.max_aggregate_planned_risk_pct - portfolio.committed_planned_risk
        )
        participation = limits.max_participation_pct * reference
        abs_beta = abs(beta.value)
        book_qty = book_capacity_qty(liquidity.asks, mid, limits.max_slippage_pct)
        beta_room = equity * limits.max_beta_btc_exposure - beta_used
        caps = [
            _cap(
                "requested",
                proposal.requested_notional,
                proposal.requested_notional,
                "teto pedido pelo chamador",
            ),
            _cap(
                "risk_per_trade",
                risk_budget / loss_per_unit,
                limits.risk_per_trade_pct,
                f"risco {risk_budget} / (stop + custos {loss_per_unit})",
            ),
            _cap(
                "aggregate_risk",
                aggregate_room / loss_per_unit,
                limits.max_aggregate_planned_risk_pct,
                f"orcamento agregado restante {aggregate_room}",
            ),
            _cap(
                "market_participation",
                participation - liquidity.participation_used_quote,
                limits.max_participation_pct,
                f"1% de {reference} menos {liquidity.participation_used_quote} ja reservado",
            ),
            _cap(
                "book_depth",
                None if book_qty is None else book_qty * price,
                limits.max_slippage_pct,
                f"walk do book ate o slippage maximo: {book_qty} unidades",
            ),
            _cap(
                "asset_exposure",
                equity * limits.max_asset_exposure_pct
                - portfolio.exposure_for_asset(proposal.market.base_asset),
                limits.max_asset_exposure_pct,
                f"teto por moeda de {proposal.market.base_asset}",
            ),
            _cap(
                "total_exposure",
                equity * limits.max_total_exposure_pct - portfolio.total_exposure,
                limits.max_total_exposure_pct,
                "teto de exposicao total",
            ),
            _cap(
                "beta_exposure",
                None if abs_beta == _ZERO else beta_room / abs_beta,
                limits.max_beta_btc_exposure,
                f"beta {beta.value}; exposicao em beta ja usada {beta_used}",
            ),
            _cap(
                "cash",
                available_cash / cash_multiplier,
                available_cash,
                f"caixa {portfolio.cash} menos {portfolio.cash - available_cash} ja reservado, "
                "dividido pelo custo de entrada com taxa",
            ),
        ]
    return tuple(caps)


def size_entry(
    *,
    proposal: EntryProposal,
    portfolio: PortfolioState,
    limits: RiskLimits,
    liquidity: MarketLiquidity,
    spec: MarketSpec,
    beta: BetaEstimate,
    size_multiplier: Decimal,
) -> Sizing:
    """The size of one entry, with every ceiling and the winner recorded."""
    price = worst_entry_price(proposal, liquidity)
    cost_pct = round_trip_cost_fraction(proposal.assumed_costs)
    stop_distance = stop_distance_fraction(price, proposal.stop)
    loss_per_unit = stop_distance + cost_pct

    caps = _ceilings(
        proposal=proposal,
        portfolio=portfolio,
        limits=limits,
        liquidity=liquidity,
        beta=beta,
        loss_per_unit=loss_per_unit,
        cash_multiplier=entry_cash_multiplier(proposal.assumed_costs),
    )
    binding = _winner(caps)
    tied = tuple(
        cap.name
        for cap in caps
        if cap.notional == binding.notional
        and cap.name != binding.name
        and cap.notional is not None
    )
    before = binding.notional
    assert before is not None

    with localcontext(CONTEXT):
        after = before * size_multiplier
        qty = floor_to_step(after / price, spec.step_size)
        notional = qty * price
        planned_risk = notional * loss_per_unit
        planned_risk_pct = planned_risk / portfolio.equity

    return Sizing(
        entry_ref=proposal.entry_ref,
        sizing_price=price,
        stop=proposal.stop,
        stop_distance_pct=stop_distance,
        cost_pct=cost_pct,
        caps=caps,
        binding_limit=binding,
        binding_constraint=binding.name,
        tied_limits=tied,
        notional_before_multiplier=before,
        kill_switch_multiplier=size_multiplier,
        notional_after_multiplier=after,
        qty=qty,
        notional=notional,
        planned_risk_quote=planned_risk,
        planned_risk_pct=planned_risk_pct,
        size_without_multipliers=_counterfactual(
            "size_without_multipliers", before, price, spec.step_size
        ),
        size_without_participation=_counterfactual(
            "size_without_participation",
            _cheapest_excluding(caps, "market_participation"),
            price,
            spec.step_size,
            multiplier=size_multiplier,
        ),
    )


def _winner(caps: tuple[LimitCap, ...]) -> LimitCap:
    bounded = [cap for cap in caps if cap.notional is not None]
    return min(bounded, key=lambda cap: (cap.notional or _ZERO, CAP_ORDER.index(cap.name)))


def _cheapest_excluding(caps: tuple[LimitCap, ...], excluded: str) -> Decimal | None:
    values = [cap.notional for cap in caps if cap.notional is not None and cap.name != excluded]
    return min(values) if values else None


def _counterfactual(
    name: str,
    notional: Decimal | None,
    entry_ref: Decimal,
    step: Decimal,
    *,
    multiplier: Decimal = _ONE,
) -> Counterfactual:
    """One "what if" size. ``None`` with a reason, never a zero standing in for it."""
    if notional is None:
        return Counterfactual(
            name=name, unavailable_reason="teto indisponivel para o contrafactual"
        )
    with localcontext(CONTEXT):
        scaled = notional * multiplier
        qty = floor_to_step(scaled / entry_ref, step)
        return Counterfactual(name=name, qty=qty, notional=qty * entry_ref)
