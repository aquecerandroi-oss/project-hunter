"""The confirmations of ``docs/RISK_ENGINE.md`` v2 §3.2 - the checks that need a size.

Kept apart from :mod:`hunter_risk.checks` because they answer a different
question. Admissibility asks "may this proposal be considered at all"; these ask
"is the number that came out of the sizing actually tradable, and does the
wallet still fit inside its ceilings **after** it".

``exposure_after`` passes by construction: the sizing already subtracted every
exposure ceiling before choosing the winner. It is recorded anyway, because "it
passes by construction" is a claim that only a written number keeps honest - and
the day a ceiling is added to the sizing and forgotten here, this line is what
notices.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT
from hunter_risk.decision import RiskCheck, Sizing, check, unavailable
from hunter_risk.exposure import PortfolioState
from hunter_risk.inputs import BetaEstimate, EntryProposal, MarketLiquidity, MarketSpec
from hunter_risk.limits import RiskLimits
from hunter_risk.sizing import book_capacity_qty, entry_cash_multiplier

_ZERO = Decimal(0)
_ONE = Decimal(1)


def post_sizing_checks(
    *,
    sizing: Sizing,
    proposal: EntryProposal,
    portfolio: PortfolioState,
    limits: RiskLimits,
    liquidity: MarketLiquidity,
    spec: MarketSpec,
    beta: BetaEstimate,
) -> tuple[RiskCheck, ...]:
    """v2 §3.2 - the confirmations that need the size.

    ``exposure_after`` passes by construction and is recorded anyway, because
    "it passes by construction" is a claim only a written number keeps honest.
    """
    notional = sizing.notional
    equity = portfolio.equity
    reference = liquidity.participation_reference
    beta_used = portfolio.beta_exposure()
    capacity_qty = book_capacity_qty(
        liquidity.asks, liquidity.reference_mid or _ZERO, limits.max_slippage_pct
    )
    with localcontext(CONTEXT):
        asset_after = portfolio.exposure_for_asset(proposal.market.base_asset) + notional
        total_after = portfolio.total_exposure + notional
        beta_after = None if beta_used is None else beta_used + abs(notional * beta.value)
        cash_needed = notional * entry_cash_multiplier(proposal.assumed_costs)

    return (
        check(
            "sizing",
            sizing.qty > _ZERO and notional >= spec.min_notional,
            value=notional,
            limit=spec.min_notional,
            message=(
                f"limitante vencedor: {sizing.binding_constraint}; qty {sizing.qty} "
                f"em passos de {spec.step_size} (nunca arredondado para cima)"
            ),
        ),
        (
            unavailable("participation", "referencia de volume do minuto indisponivel")
            if reference is None
            else check(
                "participation",
                liquidity.participation_used_quote + notional
                <= limits.max_participation_pct * reference,
                value=liquidity.participation_used_quote + notional,
                limit=limits.max_participation_pct * reference,
                message=(
                    f"1% de {reference}, orcamento compartilhado por todos os agentes numa "
                    f"janela de {limits.participation_window_s} s"
                ),
            )
        ),
        (
            unavailable("slippage_estimate", "livro ausente: custo por tamanho nao estimavel")
            if capacity_qty is None
            else check(
                "slippage_estimate",
                sizing.qty <= capacity_qty,
                value=sizing.qty,
                limit=capacity_qty,
                message="quantidade dentro da travessia do book dentro do slippage maximo",
            )
        ),
        check(
            "cash",
            cash_needed <= portfolio.cash,
            value=cash_needed,
            limit=portfolio.cash,
            message="caixa necessario incluindo taxas estimadas (SPOT: caixa e o limite duro)",
        ),
        _exposure_after(limits, equity, asset_after, total_after, beta_after),
    )


def _exposure_after(
    limits: RiskLimits,
    equity: Decimal,
    asset_after: Decimal,
    total_after: Decimal,
    beta_after: Decimal | None,
) -> RiskCheck:
    if beta_after is None:
        return unavailable("exposure_after", "agregado em beta desconhecido")
    asset_limit = equity * limits.max_asset_exposure_pct
    total_limit = equity * limits.max_total_exposure_pct
    beta_limit = equity * limits.max_beta_btc_exposure
    breaches = [
        name
        for name, value, cap in (
            ("moeda", asset_after, asset_limit),
            ("total", total_after, total_limit),
            ("beta", beta_after, beta_limit),
        )
        if value > cap
    ]
    return check(
        "exposure_after",
        not breaches,
        value=total_after,
        limit=total_limit,
        message=(
            f"moeda {asset_after}/{asset_limit}; total {total_after}/{total_limit}; "
            f"beta {beta_after}/{beta_limit}"
            + (f"; estourado: {', '.join(breaches)}" if breaches else "")
        ),
    )


POST_SIZING_CHECKS = ("sizing", "participation", "slippage_estimate", "cash", "exposure_after")
"""Names of the checks above, in order, so they can be emitted as ``unavailable``
when the size could not be computed at all."""


def unavailable_post_sizing(reason: str) -> tuple[RiskCheck, ...]:
    """The post-sizing block when there was no size: every line, all unavailable."""
    return tuple(unavailable(name, reason) for name in POST_SIZING_CHECKS)
