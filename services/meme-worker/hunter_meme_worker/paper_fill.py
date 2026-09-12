"""The fill side of the paper engine — split from :mod:`paper_engine` in T4.10
for the 350-line budget; that module re-exports every name here.

**A fill is priced against a snapshot observed strictly after the decision**
(``observed_at > decided_at``), and it is the *first* such snapshot — which is
why :func:`pick_fill_snapshot` is the only way the loop chooses one, and why
rewriting every later snapshot cannot move an entry. Without one inside the
window the proposal is ``unfilled`` with ``no_later_snapshot``; never a fill
at the price that motivated the decision.

T4.10: the decision may name the bet's ``leg`` (``probe`` | ``scale`` |
``single``) and, for a ``scale`` leg, its ``parent_bet_id`` — the probe it
rides on. The fill copies both onto the bet row; a ``scale`` without a parent
is refused by the schema (``0026``), so it is refused here first, by name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any, Final, Literal

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import quote_buy, quote_sell
from hunter_meme_worker.lab_models import (
    LEGS,
    BetEntry,
    EffectiveParams,
    RuleSetSpec,
    Snapshot,
    SolUsd,
    WalletState,
    effective_params,
    money_str,
)

__all__ = ["FILL_REFUSALS", "FillVerdict", "evaluate_fill", "pick_fill_snapshot"]

ZERO = Decimal(0)

FILL_REFUSALS: Final = frozenset(
    {
        "no_later_snapshot",
        "fill_not_after_intent",
        "migrated_before_fill",
        "curve_complete",
        "exceeds_max_sol_per_bet",
        "size_not_positive",
        "daily_loss_cap",
        "max_open_positions",
        "exposure_per_mint_cap",
        "wallet_balance_insufficient",
        "insufficient_curve_reserves",
        "unknown_leg",
        "scale_without_parent",
    }
)
"""The closed vocabulary of ``meme_proposals.refusal``. A new reason is a code
change and a test, never a string typed at a call site."""


@dataclass(frozen=True, slots=True)
class FillVerdict:
    kind: Literal["wait", "refused", "filled"]
    refusal: str | None = None
    entry: BetEntry | None = None


def pick_fill_snapshot(snapshots: Sequence[Snapshot], decided_at: datetime) -> Snapshot | None:
    """The **first** snapshot observed strictly after the decision, or ``None``.

    Not the latest: the latest would price a decision at whatever the curve did
    while the loop was late, which is the look-ahead in different clothes.
    """
    later = [s for s in snapshots if s.observed_at > decided_at]
    return min(later, key=lambda s: s.observed_at) if later else None


def _leg_of(decision: Mapping[str, Any]) -> tuple[str, str | None] | str:
    """``(leg, parent_bet_id)`` from the decision, or the refusal's name."""
    leg = str(decision.get("leg") or "single")
    parent = decision.get("parent_bet_id")
    if leg not in LEGS:
        return "unknown_leg"
    if leg == "scale" and not parent:
        return "scale_without_parent"
    return leg, None if parent is None else str(parent)


def _refuse_fill(
    spec: RuleSetSpec,
    params: EffectiveParams,
    wallet: WalletState,
    snapshot: Snapshot,
    *,
    decided_at: datetime,
    migrated: bool,
    leg: str,
) -> str | None:
    """First reason this fill must not happen, or ``None``. Order is the contract."""
    if snapshot.observed_at <= decided_at:
        return "fill_not_after_intent"
    if migrated:
        return "migrated_before_fill"
    if snapshot.complete or snapshot.reserves.complete:
        return "curve_complete"
    if wallet.realized_today_sol <= -spec.daily_loss_cap_sol:
        return "daily_loss_cap"
    # A second leg rides on its probe's slot: the ceiling counts probes and singles.
    if leg != "scale" and wallet.open_positions >= spec.max_open_positions:
        return "max_open_positions"
    with localcontext(CONTEXT):
        outflow = params.size_sol + spec.priority_fee_sol
        exposure = wallet.exposure_by_mint.get(snapshot.mint, ZERO) + outflow
        if exposure > spec.max_exposure_per_mint_sol:
            return "exposure_per_mint_cap"
        if outflow > wallet.balance_sol:
            return "wallet_balance_insufficient"
    return None


def evaluate_fill(
    spec: RuleSetSpec,
    decision: Mapping[str, Any],
    wallet: WalletState,
    snapshot: Snapshot | None,
    *,
    decided_at: datetime,
    now: datetime,
    migrated: bool,
    fill_window_s: int,
    sol_usd: SolUsd | None,
) -> FillVerdict:
    """Wait, refuse by name, or fill against ``snapshot`` — never the decision's price."""
    if snapshot is None:
        if now - decided_at >= timedelta(seconds=fill_window_s):
            return FillVerdict("refused", "no_later_snapshot")
        return FillVerdict("wait")
    params = effective_params(spec, decision)
    if isinstance(params, str):
        return FillVerdict("refused", params)
    leg = _leg_of(decision)
    if isinstance(leg, str):
        return FillVerdict("refused", leg)
    reason = _refuse_fill(
        spec, params, wallet, snapshot, decided_at=decided_at, migrated=migrated, leg=leg[0]
    )
    if reason is not None:
        return FillVerdict("refused", reason)
    try:
        entry = _build_entry(
            spec, params, snapshot, decided_at=decided_at, sol_usd=sol_usd, leg=leg
        )
    except ValueError:
        # ``quote_buy`` refuses a buy larger than what the curve still sells.
        return FillVerdict("refused", "insufficient_curve_reserves")
    return FillVerdict("filled", entry=entry)


def _build_entry(
    spec: RuleSetSpec,
    params: EffectiveParams,
    snapshot: Snapshot,
    *,
    decided_at: datetime,
    sol_usd: SolUsd | None,
    leg: tuple[str, str | None],
) -> BetEntry:
    quote = quote_buy(snapshot.reserves, params.size_sol, spec.fee_pct)
    with localcontext(CONTEXT):
        spent = quote.total_sol + spec.priority_fee_sol
        first_mark = quote_sell(quote.reserves_after, quote.tokens, spec.fee_pct).net_sol
        first_mark -= spec.priority_fee_sol
        high_water = first_mark / spent
    entry: dict[str, Any] = {
        "snapshot": snapshot.as_json(),
        "decided_at": decided_at.isoformat(),
        "decision_to_fill_s": int((snapshot.observed_at - decided_at).total_seconds()),
        "fill_delay_snapshots": 1,
        "marginal_price_before_sol": money_str(
            snapshot.reserves.virtual_sol_reserves / snapshot.reserves.virtual_token_reserves
        ),
        "marginal_price_after_sol": money_str(quote.marginal_price_after_sol),
        "average_price_sol": money_str(quote.average_price_sol),
        "curve_cost_sol": money_str(quote.curve_cost_sol),
        "fee_sol": money_str(quote.fee_sol),
        "fee_pct": money_str(spec.fee_pct),
        "priority_fee_sol": money_str(spec.priority_fee_sol),
        "sol_spent": money_str(spent),
        "tokens": money_str(quote.tokens),
        "participation_pct": None,
        "participation_reason": "curve_volume_1m_unknown",
        "sol_usd": None if sol_usd is None else sol_usd.as_json(),
        "sol_usd_source": None if sol_usd is None else sol_usd.source,
        "sol_usd_reason": None if sol_usd is not None else "quote_unavailable",
        "leg": leg[0],
        "parent_bet_id": leg[1],
    }
    return BetEntry(
        entry_at=snapshot.observed_at,
        entry=entry,
        tokens=quote.tokens,
        sol_spent=spent,
        initial_risk_sol=spent,
        params=params,
        mark_sol=first_mark,
        high_water_x=high_water,
        sol_usd_at_entry=None if sol_usd is None else sol_usd.price_usd,
        leg=leg[0],
        parent_bet_id=leg[1],
    )
