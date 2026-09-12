"""Run one mint's snapshot series through the paper wallet and report the outcome.

The loop is deliberately boring, and every interesting decision in it is a rule
about **time**:

- the gate is evaluated on snapshot ``i`` and the fill is priced on snapshot
  ``i + fill_delay_snapshots``. A series that ends before that snapshot exists
  produces ``no_fill_snapshot`` — never a fill at the decision's own price;
- the same delay applies to the exit, so an exit rule that fires on the last
  snapshot leaves the position **censored** (``open_at_series_end``) with the
  rule that fired recorded in ``unfilled_exit_reason``. Closing it at the price
  that triggered it would be the same look-ahead wearing different clothes;
- the marks that drive the exit rules come from the observed reserves, which do
  **not** contain our own paper trade: a paper buy never happened on-chain, so
  the market after it is the market without us. The assumption only holds while
  our size is small against the curve — which is exactly what the gate's
  participation cap is there to enforce, and why an arm that widens that cap has
  to say so.

R is in SOL terms: the initial risk is the declared maximum loss of the position
(``cost_basis * max_loss_pct``, capped by the doctrine's ``max_loss_cap_sol``
when there is one), because a bonding curve has no book to place a stop in and a
"stop distance in price" here would be a number the venue cannot honour.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import curve_input_from_budget, curve_progress_pct, tokens_for_sol
from hunter_indicators.meme.models import PaperWalletLimits, utc_day
from hunter_indicators.meme.paper import Fill, PaperCurveWallet
from hunter_indicators.meme.rules import (
    EntryFeatures,
    EntryGate,
    ExitState,
    evaluate_entry,
    evaluate_exit,
)
from hunter_indicators.meme.series import (
    CurveSnapshot,
    MintOutcome,
    MintSeries,
    ReplayPlan,
    ReplayResult,
    SkippedMint,
    snapshot_from_mapping,
)

__all__ = [
    "CurveSnapshot",
    "MintOutcome",
    "MintSeries",
    "PaperWalletLimits",
    "ReplayPlan",
    "ReplayResult",
    "SkippedMint",
    "entry_features",
    "replay_mint",
    "replay_mints",
    "snapshot_from_mapping",
]


def entry_features(
    series: MintSeries, snapshot: CurveSnapshot, size_sol: Decimal, gate: EntryGate
) -> EntryFeatures:
    """The gate's row at one snapshot, built from that snapshot and nothing later."""
    del gate  # the gate reads the row; it never chooses what the row contains
    age = int((snapshot.observed_at - series.created_at).total_seconds())
    return EntryFeatures(
        mint=series.mint,
        age_s=age,
        progress_pct=curve_progress_pct(snapshot.reserves),
        creator_net_seller=snapshot.creator_net_seller,
        curve_volume_1m_sol=snapshot.curve_volume_1m_sol,
        intended_size_sol=size_sol,
        curve_complete=snapshot.reserves.complete,
        migrated=snapshot.migrated,
    )


def _exit_state(
    snapshot: CurveSnapshot,
    mark: Decimal,
    cost_basis: Decimal,
    peak: Decimal,
    entry_ts: datetime,
) -> ExitState:
    return ExitState(
        mark_sol=mark,
        cost_basis_sol=cost_basis,
        peak_mark_sol=peak,
        held_s=int((snapshot.observed_at - entry_ts).total_seconds()),
        curve_complete=snapshot.reserves.complete,
        migrated=snapshot.migrated,
        rug_suspected=snapshot.rug_suspected,
        creator_net_seller=snapshot.creator_net_seller,
    )


def _initial_risk(cost_basis: Decimal, cap: Decimal | None) -> Decimal:
    """The initial risk of a curve position is **everything we paid**.

    ``docs/RISK_ENGINE_MEME.md`` §5: "o risco de uma compra na curva é o valor
    gasto inteiro, não a distância até um stop" — the creator can dump, the sell
    can fail on slippage and the plausible outcome of a buy is −100 %. The exit
    rule ``max_loss_pct`` is a *sell order*, not a guarantee, so using it as the
    denominator of R would promise a protection the chain does not offer.
    ``cap`` (the doctrine's ``MEME_MAX_SOL_PER_TRADE``) only ever lowers it.
    """
    return cost_basis if cap is None or cap >= cost_basis else cap


def _find_entry(
    series: MintSeries, plan: ReplayPlan, wallet: PaperCurveWallet
) -> tuple[int, int, Fill] | SkippedMint:
    """Scan for the first snapshot the gate allows and fill ``delay`` snapshots later."""
    snapshots = series.snapshots
    delay = plan.limits.fill_delay_snapshots
    refusals: list[str] = []
    for index, snapshot in enumerate(snapshots):
        decision = evaluate_entry(
            entry_features(series, snapshot, plan.size_sol, plan.gate), plan.gate
        )
        if not decision.allowed:
            refusals.extend(decision.refusals)
            continue
        fill_index = index + delay
        if fill_index >= len(snapshots):
            return SkippedMint(series.mint, "no_fill_snapshot", ("no_fill_snapshot",))
        fill = wallet.buy(
            series.mint,
            plan.size_sol,
            snapshots[fill_index].reserves,
            ts=snapshots[fill_index].observed_at,
            intent_ts=snapshot.observed_at,
            priority_fee_sol=plan.priority_fee_sol,
        )
        if fill.accepted:
            return index, fill_index, fill
        refusals.append(fill.reason or "refused")
        return SkippedMint(series.mint, fill.reason or "refused", _unique(refusals))
    return SkippedMint(series.mint, "never_allowed", _unique(refusals))


def _unique(names: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def replay_mint(
    series: MintSeries, plan: ReplayPlan, *, wallet: PaperCurveWallet | None = None
) -> MintOutcome | SkippedMint:
    """Replay one mint. Returns the trade, or the named reason there was none."""
    wallet = wallet or PaperCurveWallet(
        limits=plan.limits,
        balance_sol=plan.opening_balance_sol,
        opened_at=series.snapshots[0].observed_at,
    )
    found = _find_entry(series, plan, wallet)
    if isinstance(found, SkippedMint):
        return found
    decision_index, entry_index, fill = found
    budget = curve_input_from_budget(plan.size_sol, plan.limits.fee_pct)
    with localcontext(CONTEXT):
        slippage = tokens_for_sol(series.snapshots[decision_index].reserves, budget) - fill.tokens
    return _hold(series, plan, wallet, decision_index, entry_index, fill, slippage)


def _hold(
    series: MintSeries,
    plan: ReplayPlan,
    wallet: PaperCurveWallet,
    decision_index: int,
    entry_index: int,
    fill: Fill,
    slippage: Decimal,
) -> MintOutcome:
    """Walk the snapshots after the entry until a rule fires and its fill exists."""
    snapshots = series.snapshots
    delay = plan.limits.fill_delay_snapshots
    entry_ts = fill.ts
    position = wallet.position(series.mint)
    if position is None:
        raise RuntimeError("the wallet accepted a buy and holds no position: impossible state")
    cost_basis = position.cost_basis_sol
    mark = position.peak_mark_sol
    unknown: tuple[str, ...] = ()
    pending: str | None = None
    for index in range(entry_index + 1, len(snapshots)):
        snapshot = snapshots[index]
        held = wallet.position(series.mint)
        if held is None:
            break
        mark = wallet.record_mark(series.mint, snapshot.reserves, ts=snapshot.observed_at) or mark
        held = wallet.position(series.mint) or held
        decision = evaluate_exit(
            _exit_state(snapshot, mark, cost_basis, held.peak_mark_sol, entry_ts), plan.exits
        )
        unknown = _unique(unknown + decision.unknown)
        if not decision.should_exit:
            continue
        pending = decision.reason
        exit_index = index + delay
        if exit_index >= len(snapshots):
            break
        sale = wallet.sell(
            series.mint,
            held.tokens,
            snapshots[exit_index].reserves,
            ts=snapshots[exit_index].observed_at,
            intent_ts=snapshot.observed_at,
            priority_fee_sol=plan.priority_fee_sol,
        )
        if sale.accepted:
            return _outcome(
                series,
                plan,
                fill,
                decision_index=decision_index,
                entry_index=entry_index,
                slippage=slippage,
                cost_basis=cost_basis,
                mark=mark,
                peak=held.peak_mark_sol,
                unknown=unknown,
                sale=sale,
                exit_index=exit_index,
                reason=decision.reason or "exit",
            )
        pending = sale.reason
        break
    return _outcome(
        series,
        plan,
        fill,
        decision_index=decision_index,
        entry_index=entry_index,
        slippage=slippage,
        cost_basis=cost_basis,
        mark=mark,
        peak=(wallet.position(series.mint) or position).peak_mark_sol,
        unknown=unknown,
        pending=pending,
    )


def _outcome(
    series: MintSeries,
    plan: ReplayPlan,
    fill: Fill,
    *,
    decision_index: int,
    entry_index: int,
    slippage: Decimal,
    cost_basis: Decimal,
    mark: Decimal,
    peak: Decimal,
    unknown: tuple[str, ...],
    sale: Fill | None = None,
    exit_index: int | None = None,
    reason: str | None = None,
    pending: str | None = None,
) -> MintOutcome:
    """The one place an outcome is built, closed or censored.

    Censored (``sale is None``) means the data ran out while the position was
    open: the PnL is the **mark**, the rule that had fired stays in
    ``unfilled_exit_reason``, and ``closed`` is ``False`` so a reader can count
    censoring instead of mistaking it for a realised trade.
    """
    last_ts = series.snapshots[-1].observed_at
    with localcontext(CONTEXT):
        proceeds = sale.sol_delta if sale is not None else None
        pnl = (proceeds if proceeds is not None else mark) - cost_basis
        risk = _initial_risk(cost_basis, plan.max_loss_cap_sol)
        return MintOutcome(
            mint=series.mint,
            day=utc_day(fill.ts),
            decision_index=decision_index,
            entry_index=entry_index,
            entry_ts=fill.ts,
            entry_size_sol=cost_basis,
            tokens=fill.tokens,
            slippage_tokens=slippage,
            entry_price_sol=cost_basis / fill.tokens,
            exit_index=exit_index if sale is not None else None,
            exit_ts=sale.ts if sale is not None else None,
            exit_reason=(reason or "exit") if sale is not None else "open_at_series_end",
            unfilled_exit_reason=None if sale is not None else pending,
            exit_proceeds_sol=proceeds,
            mark_at_exit_sol=mark,
            peak_mark_sol=peak,
            pnl_sol=pnl,
            initial_risk_sol=risk,
            r_multiple=pnl / risk,
            holding_s=int(((sale.ts if sale is not None else last_ts) - fill.ts).total_seconds()),
            closed=sale is not None,
            unknown=unknown,
        )


def replay_mints(
    series: Sequence[MintSeries], plan: ReplayPlan, *, opened_at: datetime
) -> ReplayResult:
    """Replay several mints **sequentially** on one shared wallet.

    Sequential, not interleaved: the balance and the daily loss latch are shared,
    the simultaneity is not. Two positions that would really have been open at
    the same instant are replayed one after the other here, so
    ``max_open_positions`` binds less than it would in production. Declared,
    because a portfolio simulation is a different task and pretending this one
    is it would overstate what the caps proved.
    """
    wallet = PaperCurveWallet(
        limits=plan.limits, balance_sol=plan.opening_balance_sol, opened_at=opened_at
    )
    outcomes: list[MintOutcome] = []
    skipped: list[SkippedMint] = []
    for one in series:
        result = replay_mint(one, plan, wallet=wallet)
        if isinstance(result, MintOutcome):
            outcomes.append(result)
        else:
            skipped.append(result)
    return ReplayResult(tuple(outcomes), tuple(skipped), wallet.ledger)
