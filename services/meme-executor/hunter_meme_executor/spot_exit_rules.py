"""T4.74-4 — the pure rules of the ``spot/1`` desk's exits (design §4) and of
its lane state (design §8): no clock, no network, no database. ``spot_exits``
(T4.74-5) and ``spot_entries`` call these with what they read.

Exit order, fixed: ``emergency`` > ``sell_requested`` > ``stop`` > ``target``
> ``time``. ``r_now = (mark − spent) ÷ r_unit``; the stop is ``r_now ≤ −1``,
the target is ``r_now ≥ target_frac ÷ stop_frac`` (1,5 R for the v14
geometry), the time stop is ``age ≥ horizon_s``. No trailing in v1. A
``TRADING_DISABLED``/``WARNING`` switch never blocks an exit; ``EMERGENCY``
sells only with ``MEME_AUTO_CLOSE_ON_EMERGENCY`` (engine §14.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

from hunter_core.domain.enums import KillSwitchState

if TYPE_CHECKING:
    from hunter_meme_executor.spot_repo_positions import ClosedStats, SpotPosition

__all__ = [
    "BACKOFF_S",
    "EXIT_REASONS",
    "MAX_EXIT_ATTEMPTS",
    "PANIC_FROM_ATTEMPT",
    "PANIC_REASONS",
    "LaneState",
    "backoff_s",
    "decide_exit",
    "lane_state",
    "r_now",
    "slippage_for",
    "target_r",
]

LAMPORTS: Final = Decimal(1_000_000_000)
EXIT_REASONS: Final[tuple[str, ...]] = ("emergency", "sell_requested", "stop", "target", "time")
"""In evaluation order — the first that holds wins."""
BACKOFF_S: Final[tuple[int, ...]] = (2, 4, 8, 16, 32, 60)
"""``exit_common.BACKOFF_S``, repeated here so this module stays import-light."""
MAX_EXIT_ATTEMPTS: Final = 6
"""Past this the position is ``blocked_exits[id]`` (design §4) — still marked."""
PANIC_FROM_ATTEMPT: Final = 3
PANIC_REASONS: Final[frozenset[str]] = frozenset({"stop", "emergency"})
_ZERO = Decimal(0)
_MINUS_ONE = Decimal(-1)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except ArithmeticError:
        return None
    return parsed if parsed.is_finite() else None


def r_now(position: SpotPosition, mark_sol: Decimal | None) -> Decimal | None:
    """``(mark − spent) ÷ r_unit`` — ``None`` without a mark or a positive R unit."""
    if mark_sol is None or position.initial_risk_sol <= _ZERO:
        return None
    spent = Decimal(position.sol_spent_lamports) / LAMPORTS
    return (mark_sol - spent) / position.initial_risk_sol


def target_r(params: dict[str, Any]) -> Decimal | None:
    """``target_frac ÷ stop_frac`` from the geometry written at the entry."""
    stop_frac, target_frac = _decimal(params.get("stop_frac")), _decimal(params.get("target_frac"))
    if stop_frac is None or target_frac is None or stop_frac <= _ZERO or target_frac <= _ZERO:
        return None
    return target_frac / stop_frac


def decide_exit(
    position: SpotPosition,
    mark_sol: Decimal | None,
    now: datetime,
    kill: KillSwitchState,
    *,
    auto_close_on_emergency: bool = False,
) -> str | None:
    """The reason to sell the whole lot now, or ``None``. A missing mark skips
    ``stop``/``target`` (never a guess); a missing ``horizon_s`` skips ``time``."""
    if kill is KillSwitchState.EMERGENCY and auto_close_on_emergency:
        return "emergency"
    if position.sell_requested_at is not None:
        return "sell_requested"
    r = r_now(position, mark_sol)
    if r is not None:
        if r <= _MINUS_ONE:
            return "stop"
        goal = target_r(position.params)
        if goal is not None and r >= goal:
            return "target"
    horizon = position.params.get("horizon_s")
    if isinstance(horizon, int | float | str) and not isinstance(horizon, bool):
        try:
            horizon_s = int(Decimal(str(horizon)))
        except ArithmeticError:
            horizon_s = None
        if horizon_s is not None and (now - position.entry_at).total_seconds() >= horizon_s:
            return "time"
    return None


def slippage_for(attempt: int, reason: str, *, normal_bps: int = 50, panic_bps: int = 300) -> int:
    """Design §4: the panic tolerance from the 3rd attempt, or from the 1st for a
    stop or an emergency; the normal one otherwise."""
    if attempt >= PANIC_FROM_ATTEMPT or reason in PANIC_REASONS:
        return panic_bps
    return normal_bps


def backoff_s(attempt: int) -> int:
    """Seconds to wait after the failed ``attempt`` (1-based); the last value repeats."""
    return BACKOFF_S[min(max(attempt, 1), len(BACKOFF_S)) - 1]


@dataclass(frozen=True, slots=True)
class LaneState:
    state: str
    """``on`` | ``refuted`` | ``cooldown``."""
    reason: str | None
    refusal: str | None
    """What an entry is refused with while not ``on`` (``spot1_refuted``/``spot1_cooldown``)."""
    cooldown_until: datetime | None = None


def lane_state(
    stats: ClosedStats,
    *,
    now: datetime,
    refute_min_trades: int,
    refute_max_loss_sol: Decimal,
    consecutive_stops_pause_s: int,
) -> LaneState:
    """Design §8, in code: ``n ≥ min_trades`` with expectancy ≤ 0 R, **or**
    ``Σ pnl ≤ −max_loss`` at any count ⇒ ``refuted``; ``≥ 3`` stops in a row
    ⇒ ``cooldown`` for ``pause_s`` after the last exit. Refutation is checked
    first: a cooldown never hides it."""
    # T4.74-5 (Astra): the worst prefix decides, so a later win never re-opens
    # a refuted lane — only ``SPOT1_REFUTATION_RESET_AT`` does (design §8).
    worst_pnl = stats.sum_pnl_sol
    if stats.min_run_pnl_sol is not None:
        worst_pnl = min(worst_pnl, stats.min_run_pnl_sol)
    if worst_pnl <= -refute_max_loss_sol:
        reason = f"sum_pnl_sol={worst_pnl}<=-{refute_max_loss_sol}"
        return LaneState("refuted", reason, "spot1_refuted")
    expectancy = stats.expectancy_r_net
    if stats.n >= refute_min_trades and expectancy is not None:
        if stats.min_expectancy_r_net is not None:
            expectancy = min(expectancy, stats.min_expectancy_r_net)
        if expectancy <= _ZERO:
            reason = f"n={stats.n} expectancy_r_net={expectancy}<=0"
            return LaneState("refuted", reason, "spot1_refuted")
    if stats.consecutive_stops >= 3 and stats.last_exit_at is not None:
        elapsed = (now - stats.last_exit_at).total_seconds()
        if elapsed < consecutive_stops_pause_s:
            until = stats.last_exit_at + timedelta(seconds=consecutive_stops_pause_s)
            reason = f"consecutive_stops={stats.consecutive_stops} until={until.isoformat()}"
            return LaneState("cooldown", reason, "spot1_cooldown", until)
    return LaneState("on", None, None)
