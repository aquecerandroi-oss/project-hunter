"""Open and close a ``meme_paper_bets`` row priced by chain events (T4.67a) —
"entry/exit JSON like the Lab writes" (the brief's own words), reusing the
Lab's own value objects and repository functions rather than a second
insert/close path: :class:`~hunter_meme_worker.lab_models.BetEntry`/
:class:`~hunter_meme_worker.lab_models.BetExit`/
:class:`~hunter_meme_worker.lab_models.BetState`,
:func:`~hunter_meme_worker.lab_repo_bets.mark_filled`/
:func:`~hunter_meme_worker.lab_repo_bets.close_bet_row` for the two writes,
and :func:`~hunter_meme_worker.paper_engine.close_bet` for the sale
arithmetic — only the *snapshot* is built here, from
:func:`~hunter_meme_worker.launch_lane_pricing.standard_reserves` rather than
a ``meme_curve_snapshots`` row, because none exists this early.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import CURVE_TRADE_FEE_PCT, quote_buy, quote_sell
from hunter_meme_worker.lab_models import BetEntry, BetState, EffectiveParams, Snapshot, money_str
from hunter_meme_worker.lab_repo_bets import close_bet_row, mark_filled
from hunter_meme_worker.lab_rows import ApprovedProposal
from hunter_meme_worker.launch_lane_pricing import standard_reserves
from hunter_meme_worker.paper_engine import close_bet

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.event_state import CurvePoint
    from hunter_meme_worker.lab_models import BetExit
    from hunter_meme_worker.launch_lane_repo import LaunchRuleSpec

__all__ = ["close_launch_bet", "open_launch_bet"]

MARK_SOURCE = "solana_ws"
"""``meme_paper_bets.mark_source`` for both the fill and the close — the
lane's own read of the chain, never the curve poller's ``meme_curve_snapshots``."""

TOTAL_SUPPLY = Decimal(1_000_000_000)
"""pump.fun's own fixed total supply — every standard mint's, launch lane's
sanity check on ``initial_real_token_reserves`` already refused anything else."""

_TARGET_X_SENTINEL = Decimal(1000)
"""Never the practical exit path — an orphaned launch bet the process
crashed under still closes on ``max_hold_s`` (below, ``spec.time_stop_s``) if
the ordinary Lab tick ever has to pick it up (``EffectiveParams`` is the same
shape ``paper_engine.py`` already reads); a fixed target this high never
fires first."""


def _snapshot(mint: str, point: CurvePoint) -> Snapshot:
    return Snapshot(
        mint=mint,
        observed_at=point.observed_at,
        source=MARK_SOURCE,
        reserves=standard_reserves(point),
        real_sol_reserves=point.real_sol,
        total_supply=TOTAL_SUPPLY,
        complete=False,
        mcap_sol=point.mcap_sol,
        mayhem_enabled=False,
    )


def _effective_params(spec: LaunchRuleSpec) -> EffectiveParams:
    return EffectiveParams(
        size_sol=spec.size_sol,
        target_x=_TARGET_X_SENTINEL,
        trailing_pct=spec.max_drawdown_from_peak_pct,
        max_hold_s=spec.time_stop_s,
        max_loss_pct=Decimal(100),
        exit_on_migration=True,
    )


def _entry(spec: LaunchRuleSpec, snapshot: Snapshot) -> BetEntry:
    quote = quote_buy(snapshot.reserves, spec.size_sol, CURVE_TRADE_FEE_PCT)
    with localcontext(CONTEXT):
        first_mark = quote_sell(quote.reserves_after, quote.tokens, CURVE_TRADE_FEE_PCT).net_sol
        high_water = first_mark / quote.total_sol
    entry: dict[str, Any] = {
        "snapshot": snapshot.as_json(),
        "reason": "launch_lane_entry_plus_1s",
        "marginal_price_after_sol": money_str(quote.marginal_price_after_sol),
        "average_price_sol": money_str(quote.average_price_sol),
        "curve_cost_sol": money_str(quote.curve_cost_sol),
        "fee_sol": money_str(quote.fee_sol),
        "fee_pct": money_str(CURVE_TRADE_FEE_PCT),
        "priority_fee_sol": "0",
        "sol_spent": money_str(quote.total_sol),
        "tokens": money_str(quote.tokens),
        "sol_usd": None,
        "sol_usd_source": None,
        "sol_usd_reason": "quote_unavailable",
        "leg": "single",
        "parent_bet_id": None,
    }
    return BetEntry(
        entry_at=snapshot.observed_at,
        entry=entry,
        tokens=quote.tokens,
        sol_spent=quote.total_sol,
        initial_risk_sol=quote.total_sol,
        params=_effective_params(spec),
        mark_sol=first_mark,
        high_water_x=high_water,
        sol_usd_at_entry=None,
        leg="single",
        parent_bet_id=None,
    )


async def open_launch_bet(
    session: AsyncSession,
    *,
    proposal_id: str,
    rule_set_id: str,
    mint: str,
    spec: LaunchRuleSpec,
    entry_point: CurvePoint,
) -> tuple[str, BetEntry]:
    """Buy ``spec.size_sol`` against the reconstructed curve at
    ``entry_point`` and fill the proposal — ``mark_filled`` is the exact
    function ``paper_fill.py``'s own fills call."""
    snapshot = _snapshot(mint, entry_point)
    entry = _entry(spec, snapshot)
    proposal = ApprovedProposal(
        id=proposal_id,
        mint=mint,
        rule_set_id=rule_set_id,
        decision={},
        decided_at=entry.entry_at,
        migrated=False,
    )
    bet_id = await mark_filled(session, proposal, entry)
    return bet_id, entry


async def close_launch_bet(
    session: AsyncSession,
    *,
    bet_id: str,
    mint: str,
    rule_set_id: str,
    entry: BetEntry,
    exit_point: CurvePoint,
    reason: str,
) -> BetExit:
    """Sell everything against the reconstructed curve at ``exit_point`` —
    ``paper_engine.close_bet`` is the exact function every other exit uses,
    handed a :class:`BetState` built from the entry this lane itself wrote."""
    bet_state = BetState(
        id=bet_id,
        proposal_id="",
        rule_set_id=rule_set_id,
        mint=mint,
        entry_at=entry.entry_at,
        tokens=entry.tokens,
        sol_spent=entry.sol_spent,
        initial_risk_sol=entry.initial_risk_sol,
        params=entry.params,
        high_water_x=entry.high_water_x,
        mark_sol=entry.mark_sol,
        mark_at=entry.entry_at,
        exit_intent=None,
        fee_pct=CURVE_TRADE_FEE_PCT,
        priority_fee_sol=Decimal(0),
        leg="single",
        parent_bet_id=None,
        mark_source=MARK_SOURCE,
        mark_stale_s=None,
        is_mayhem=False,
    )
    snapshot = _snapshot(mint, exit_point)
    closed = close_bet(
        bet_state, snapshot, reason, sol_usd=None, intent_snapshot_at=exit_point.observed_at
    )
    await close_bet_row(session, bet_id, closed, mark_source=MARK_SOURCE)
    return closed
