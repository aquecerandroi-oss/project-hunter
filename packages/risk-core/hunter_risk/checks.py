"""The checks of ``docs/RISK_ENGINE.md`` v2 §3, as pure functions.

Two rules govern every function here.

**Fail closed** (``R-OPS-1``). A check that cannot be evaluated returns
``unavailable``, and an ``unavailable`` check rejects an entry exactly like a
``failed`` one. In the strategy layer a missing input means "do not evaluate";
here it has to mean "do not open". The failure this prevents is specific: the
market goes into stress, the websocket drops, the book disappears, and the
proposal is approved without the only per-size cost estimate there is -
precisely when slippage explodes.

**Say which fact was missing.** ``unavailable`` and ``failed`` are different
states because they are different facts, and an operator who cannot tell "the
limit was breached" from "the limit could not be measured" will eventually treat
a dead feed as a healthy market.

Ages are measured against ``portfolio.as_of``: the engine has no clock, so the
instant of the evaluation is part of the state it was given (``R-OPS-2``).
"""

from __future__ import annotations

from decimal import Decimal

from hunter_core.domain.enums import MarketType, TradeDirection
from hunter_risk.decision import RiskCheck, check, unavailable
from hunter_risk.exposure import PortfolioState
from hunter_risk.inputs import BetaEstimate, EntryProposal, MarketLiquidity, MarketSpec
from hunter_risk.kill_switch import KillSwitchAssessment
from hunter_risk.limits import RiskLimits
from hunter_risk.observations import (
    book_capacity_qty,
    entry_deviation,
    entry_zone_ok,
    observed_price,
    stale_volume_reason,
    stop_below_market,
    worst_entry_price,
)
from hunter_risk.sizing import stop_distance_fraction

_ZERO = Decimal(0)
_ONE = Decimal(1)


def gate_checks(
    *,
    proposal: EntryProposal,
    portfolio: PortfolioState,
    limits: RiskLimits,
    liquidity: MarketLiquidity,
    spec: MarketSpec,
    beta: BetaEstimate,
    assessment: KillSwitchAssessment,
) -> tuple[RiskCheck, ...]:
    """Admissibility - everything decidable before a size exists (v2 §3.1)."""
    equity = portfolio.equity
    price_age = portfolio.age_s(liquidity.price_ts)
    spread = liquidity.spread_pct
    aggregate_limit = equity * limits.max_aggregate_planned_risk_pct

    return (
        check(
            "market_identity",
            proposal.market == liquidity.market == spec.market,
            message=(
                f"proposta {proposal.market.exchange}:{proposal.market.symbol}; "
                f"livro {liquidity.market.exchange}:{liquidity.market.symbol}; "
                f"regras {spec.market.exchange}:{spec.market.symbol}"
            ),
        ),
        check(
            "kill_switch",
            not assessment.blocks_entries,
            message=f"estado efetivo {assessment.effective}",
        ),
        _portfolio_status(proposal, portfolio),
        check(
            "modality",
            proposal.direction is TradeDirection.LONG
            and proposal.market.market_type is MarketType.SPOT
            and limits.max_leverage == _ONE,
            limit=limits.max_leverage,
            message=f"{proposal.direction} em {proposal.market.market_type}",
        ),
        _data_quality(limits, liquidity, price_age),
        (
            unavailable("market_gap", "continuidade da coleta desconhecida")
            if liquidity.gap_state is None
            else check(
                "market_gap",
                liquidity.gap_state == "ok",
                message=f"continuidade da janela: {liquidity.gap_state}",
            )
        ),
        (
            unavailable("market_in_universe", "estado do universo desconhecido")
            if liquidity.in_universe is None
            else check(
                "market_in_universe",
                liquidity.in_universe,
                message="mercado ainda monitorado entre o sinal e a proposta",
            )
        ),
        _signal_validity(proposal, limits, liquidity),
        _stop_distance(proposal, limits, liquidity),
        _liquidity_24h(portfolio, limits, liquidity),
        (
            unavailable("spread", "bid/ask nao observados", limit=limits.max_spread_pct)
            if spread is None
            else check(
                "spread",
                spread <= limits.max_spread_pct,
                value=spread,
                limit=limits.max_spread_pct,
                message="spread relativo ao mid",
            )
        ),
        _book_depth(portfolio, limits, liquidity),
        _beta_validity(portfolio, limits, beta),
        check(
            "concurrent_positions",
            portfolio.slots_used < limits.max_concurrent_positions,
            value=Decimal(portfolio.slots_used),
            limit=Decimal(limits.max_concurrent_positions),
            message="posicoes abertas mais entradas pendentes",
        ),
        check(
            "duplicate_position",
            proposal.market.base_asset not in portfolio.assets_held,
            message=f"{proposal.market.base_asset} ja na carteira ou reservado (D3)",
        ),
        check(
            "aggregate_risk_budget",
            portfolio.committed_planned_risk < aggregate_limit,
            value=portfolio.committed_planned_risk,
            limit=aggregate_limit,
            message="risco planejado ja comprometido, aberto e pendente",
        ),
        check(
            "daily_loss",
            portfolio.daily_loss_pct < limits.kill_switch_blocked.daily_loss_pct,
            value=portfolio.daily_loss_pct,
            limit=limits.kill_switch_blocked.daily_loss_pct,
            message="perda do dia sobre o patrimonio do inicio do dia (America/Sao_Paulo)",
        ),
        check(
            "drawdown",
            portfolio.drawdown_pct < limits.kill_switch_blocked.drawdown_pct,
            value=portfolio.drawdown_pct,
            limit=limits.kill_switch_blocked.drawdown_pct,
            message="queda desde o pico historico monotonico",
        ),
    )


def _portfolio_status(proposal: EntryProposal, portfolio: PortfolioState) -> RiskCheck:
    if not portfolio.marks_complete:
        return unavailable(
            "portfolio_status",
            "posicao sem marcacao valida ou ancora do dia nao reconstruida apos restart",
        )
    return check(
        "portfolio_status",
        portfolio.is_active and proposal.agent_enabled,
        message=f"portfolio ativo={portfolio.is_active}, agente ativo={proposal.agent_enabled}",
    )


def _data_quality(limits: RiskLimits, liquidity: MarketLiquidity, price_age: Decimal) -> RiskCheck:
    """v2 §3.1 check 4: degraded market data **or** a price older than the limit."""
    if liquidity.data_quality != "ok":
        return check("data_quality", False, message=f"market data {liquidity.data_quality}")
    return check(
        "data_quality",
        _ZERO <= price_age <= Decimal(limits.max_price_age_s),
        value=price_age,
        limit=Decimal(limits.max_price_age_s),
        message="idade do ultimo preco, em segundos",
    )


def _signal_validity(
    proposal: EntryProposal, limits: RiskLimits, liquidity: MarketLiquidity
) -> RiskCheck:
    """v2 §3.1 check 7 - the three things that make a signal still tradable.

    The signal is active, the stop is on the right side (of the reference **and**
    of the market the order will meet), and the reference is still inside the
    declared entry zone around the observed price. The three travel together
    because they answer one question: is this proposal about the market that
    exists now? The review of 2026-09-06 found the last two missing:
    ``entry_ref = 100`` with the market at 110 was approved with a real planned
    loss of 1,18 % of the equity, and a long whose stop sat above the market was
    approved as well.
    """
    deviation = entry_deviation(proposal, liquidity)
    geometry_ok = _ZERO < proposal.stop < proposal.entry_ref
    return check(
        "signal_validity",
        proposal.signal_valid
        and geometry_ok
        and stop_below_market(proposal, liquidity)
        and entry_zone_ok(proposal, liquidity, limits),
        value=deviation,
        limit=limits.max_entry_deviation_pct,
        message=(
            f"sinal ativo={proposal.signal_valid}; stop {proposal.stop} abaixo da referencia "
            f"{proposal.entry_ref} e do preco observado {observed_price(liquidity)}; desvio da "
            f"zona de entrada {deviation}"
        ),
    )


def _liquidity_24h(
    portfolio: PortfolioState, limits: RiskLimits, liquidity: MarketLiquidity
) -> RiskCheck:
    """v2 §3.1 check 9, with the age the profile declares (``R-OPS-2``).

    ``max_volume_age_s`` (120 s in ``paper_v1``) existed and was never read: a
    volume photographed 45 minutes earlier passed the floor and sized the
    participation ceiling as if it were now (review of 2026-09-06, finding 3).
    """
    stale = stale_volume_reason(portfolio, limits, liquidity)
    if stale is not None:
        return unavailable("liquidity_24h", stale, limit=limits.min_liquidity_usd_24h)
    if liquidity.quote_volume_24h is None:
        return unavailable(
            "liquidity_24h", "volume de 24 h nao observado", limit=limits.min_liquidity_usd_24h
        )
    return check(
        "liquidity_24h",
        liquidity.quote_volume_24h >= limits.min_liquidity_usd_24h,
        value=liquidity.quote_volume_24h,
        limit=limits.min_liquidity_usd_24h,
        message="piso de liquidez no venue de execucao",
    )


def _stop_distance(
    proposal: EntryProposal, limits: RiskLimits, liquidity: MarketLiquidity
) -> RiskCheck:
    """The band, measured at the same price the sizing uses - the worse of the two."""
    if not _ZERO < proposal.stop < proposal.entry_ref:
        return unavailable("stop_distance", "geometria do stop invalida: distancia nao calculavel")
    # max(entry_ref, observed) is never below entry_ref, which the guard above
    # already put strictly over the stop, so the division is always defined.
    distance = stop_distance_fraction(worst_entry_price(proposal, liquidity), proposal.stop)
    return check(
        "stop_distance",
        limits.min_stop_distance_pct <= distance <= limits.max_stop_distance_pct,
        value=distance,
        limit=limits.max_stop_distance_pct,
        message=f"banda [{limits.min_stop_distance_pct}, {limits.max_stop_distance_pct}]",
    )


def _book_depth(
    portfolio: PortfolioState, limits: RiskLimits, liquidity: MarketLiquidity
) -> RiskCheck:
    if not liquidity.asks or liquidity.book_ts is None or liquidity.reference_mid is None:
        return unavailable("book_depth", "livro de ofertas nao observado")
    age = portfolio.age_s(liquidity.book_ts)
    if not _ZERO <= age <= Decimal(limits.max_book_age_s):
        return check(
            "book_depth",
            False,
            value=age,
            limit=Decimal(limits.max_book_age_s),
            message="livro vencido: idade em segundos",
        )
    capacity = book_capacity_qty(liquidity.asks, liquidity.reference_mid, limits.max_slippage_pct)
    return check(
        "book_depth",
        capacity is not None and capacity > _ZERO,
        value=capacity,
        limit=limits.max_slippage_pct,
        message="capacidade do livro, em unidades, dentro do slippage maximo",
    )


def _beta_validity(portfolio: PortfolioState, limits: RiskLimits, beta: BetaEstimate) -> RiskCheck:
    """v2 §6: the candidate's beta **and** every held or reserved beta must be valid."""
    if not beta.validated:
        return unavailable("beta_validity", "beta nao validado; ativo segue apenas em shadow")
    age = portfolio.age_s(beta.as_of)
    if not _ZERO <= age <= Decimal(limits.max_beta_age_s):
        return unavailable(
            "beta_validity",
            f"beta com {age} s, acima de {limits.max_beta_age_s} s; ativo segue em shadow",
            limit=Decimal(limits.max_beta_age_s),
        )
    if portfolio.beta_exposure() is None:
        return unavailable(
            "beta_validity",
            "posicao aberta ou pendente sem beta valido: o agregado em beta e desconhecido",
        )
    return check("beta_validity", True, value=beta.value, message="beta validado contra o BTC")
