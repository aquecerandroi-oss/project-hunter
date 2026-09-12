"""The paper engine of the Lab: fills, marks, exits — pure, and every rule is
about **time** (T4.5's replay, rewritten for durable rows).

Three rules this module exists to enforce, each a named refusal or a named exit
rather than a silent default:

1. **A fill is priced against a snapshot observed strictly after the decision**
   (``observed_at > decided_at``), and it is the *first* such snapshot — which
   is why :func:`pick_fill_snapshot` is the only way the loop chooses one, and
   why rewriting every later snapshot cannot move an entry. Without one inside
   the window the proposal is ``unfilled`` with ``no_later_snapshot``; never a
   fill at the price that motivated the decision. (The fill side lives in
   :mod:`hunter_meme_worker.paper_fill` since T4.10 and is re-exported here.)
2. **A sale is priced the same way**: the rule fires on snapshot *k* (recorded
   as ``exit_intent``) and the sale is priced on the next one. No later snapshot
   inside the window means ``rug_no_snapshot``: the tokens are worth what a
   sell can realise, and when nothing can be observed to sell into, that is
   zero — ``docs/RISK_ENGINE_MEME.md`` §5's "the plausible outcome of a buy on
   a curve is −100 %" written as arithmetic, never as a fabricated fill.
3. **The mark is what a full sell would net now, fees included** (§6) — the
   ``mark_sol`` on the row and the number every exit rule reads.

The arithmetic is ``hunter_indicators.meme.curve`` and the exit precedence is
``hunter_indicators.meme.rules.evaluate_exit`` (rug signal, creator dump, the
curve's own events, the loss floor, **the broken line** (T4.10), the target,
the trailing, the time stop); the operator's ``sell_now`` sits above all of
them, because an explicit human order is not a rule to be outranked.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Any, Final

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import quote_sell
from hunter_indicators.meme.rules import ExitState, evaluate_exit
from hunter_meme_worker.lab_models import BetExit, BetState, Snapshot, SolUsd, money_str
from hunter_meme_worker.paper_fill import (
    FILL_REFUSALS,
    FillVerdict,
    evaluate_fill,
    pick_fill_snapshot,
)

__all__ = [
    "EXIT_REASONS",
    "FILL_REFUSALS",
    "FillVerdict",
    "Mark",
    "close_bet",
    "close_without_snapshot",
    "decide_exit",
    "evaluate_fill",
    "mark_bet",
    "pick_fill_snapshot",
]

ZERO = Decimal(0)

EXIT_REASONS: Final = frozenset(
    {
        "target",
        "trailing",
        "time_stop",
        "migrated",
        "creator_dump",
        "sell_now",
        "rug_no_snapshot",
        "max_loss",
        "line_broken",
    }
)

_RULE_TO_REASON: Final[Mapping[str, str]] = {
    "target_multiple": "target",
    "trailing_from_peak": "trailing",
    "time_stop": "time_stop",
    "migrated": "migrated",
    "curve_complete": "migrated",
    "creator_dump": "creator_dump",
    "max_loss": "max_loss",
    "line_broken": "line_broken",
    "rug_signal": "rug_no_snapshot",
}
"""T4.5's rule names → the contract's ``exit.reason``. Completion and migration
both mean "the curve stopped being the venue" (``exit.trigger`` keeps which)."""


@dataclass(frozen=True, slots=True)
class Mark:
    mark_sol: Decimal
    high_water_x: Decimal


def mark_bet(bet: BetState, snapshot: Snapshot) -> Mark:
    """The honest mark and the high water it may raise, never lower."""
    with localcontext(CONTEXT):
        mark = quote_sell(snapshot.reserves, bet.tokens, bet.fee_pct).net_sol - bet.priority_fee_sol
        return Mark(mark_sol=mark, high_water_x=max(bet.high_water_x, mark / bet.sol_spent))


def decide_exit(
    bet: BetState,
    snapshot: Snapshot,
    mark: Mark,
    *,
    migrated: bool,
    creator_net_seller: bool | None,
    sell_now: bool,
    below_support_streak: int | None = None,
) -> str | None:
    """The contract's ``exit.reason`` that fires on this snapshot, or ``None``.

    ``below_support_streak`` is the caller's count of consecutive snapshots
    (this one included) closed below the support line projected to their
    instant (``lines_exit.py``); ``None`` = no line known, which a rule set
    that watches the line reports as ``support_line_unknown``.
    """
    if sell_now:
        return "sell_now"
    with localcontext(CONTEXT):
        peak = mark.high_water_x * bet.sol_spent
    state = ExitState(
        mark_sol=mark.mark_sol,
        cost_basis_sol=bet.sol_spent,
        peak_mark_sol=peak,
        held_s=int((snapshot.observed_at - bet.entry_at).total_seconds()),
        curve_complete=snapshot.complete or snapshot.reserves.complete,
        migrated=migrated,
        rug_suspected=None,
        creator_net_seller=creator_net_seller,
        below_support_streak=below_support_streak,
    )
    decision = evaluate_exit(state, bet.params.exit_rules())
    if not decision.should_exit or decision.reason is None:
        return None
    return _RULE_TO_REASON[decision.reason]


def close_bet(
    bet: BetState,
    snapshot: Snapshot,
    reason: str,
    sol_usd: SolUsd | None,
    *,
    intent_snapshot_at: datetime | None,
) -> BetExit:
    """Sell everything against ``snapshot`` — the one after the rule fired."""
    quote = quote_sell(snapshot.reserves, bet.tokens, bet.fee_pct)
    with localcontext(CONTEXT):
        received = quote.net_sol - bet.priority_fee_sol
        pnl = received - bet.sol_spent
        r_multiple = pnl / bet.initial_risk_sol
    exit_payload: dict[str, Any] = {
        "reason": reason,
        "snapshot": snapshot.as_json(),
        "intent_snapshot_at": None
        if intent_snapshot_at is None
        else intent_snapshot_at.isoformat(),
        "curve_proceeds_sol": money_str(quote.curve_proceeds_sol),
        "fee_sol": money_str(quote.fee_sol),
        "priority_fee_sol": money_str(bet.priority_fee_sol),
        "sol_received": money_str(received),
        "marginal_price_after_sol": money_str(quote.marginal_price_after_sol),
        "sol_usd": None if sol_usd is None else sol_usd.as_json(),
        "sol_usd_source": None if sol_usd is None else sol_usd.source,
        "sol_usd_reason": None if sol_usd is not None else "quote_unavailable",
    }
    return BetExit(
        exit_at=snapshot.observed_at,
        exit=exit_payload,
        pnl_sol=pnl,
        r_multiple=r_multiple,
        sol_usd_at_exit=None if sol_usd is None else sol_usd.price_usd,
    )


def close_without_snapshot(bet: BetState, *, now: datetime, pending_reason: str | None) -> BetExit:
    """No snapshot to sell into inside the window: the position is worth zero.

    Not a fabricated fill at the last mark — a curve nobody observes any more is
    a curve nobody is buying from, and the doctrine's plausible outcome of a
    curve position is the whole stake (RISK_ENGINE_MEME §5).
    """
    with localcontext(CONTEXT):
        pnl = -bet.sol_spent
        r_multiple = pnl / bet.initial_risk_sol
    return BetExit(
        exit_at=now,
        exit={
            "reason": "rug_no_snapshot",
            "pending_reason": pending_reason,
            "snapshot": None,
            "sol_received": "0",
            "sol_usd": None,
            "sol_usd_source": None,
            "sol_usd_reason": "no_sale_to_price",
        },
        pnl_sol=pnl,
        r_multiple=r_multiple,
        sol_usd_at_exit=None,
    )
