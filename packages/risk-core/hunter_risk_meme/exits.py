"""Exit rules (§6): always allowed; what they decide is *when* and *by which route*.

Pure: a position, its honest mark, the instant and the parameters in; the name
of the rule that fires (or ``None``) out. Precedence, highest first: the
operator's ``sell_now`` (a human order is not a rule to be outranked), a rug
signal, a creator dump, the curve leaving the venue (complete/migrated), the
target, the trailing stop, the time stop. The kill switch is **not** a rule
here — ``TRADING_DISABLED``/``EMERGENCY`` never close a position by themselves
(§7); the executor's optional ``auto_close_on_emergency`` is a separate,
owner-decided trigger it names as such.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Final, Literal

from pydantic import Field

from hunter_risk_meme.base import MemeModel

__all__ = ["EXIT_REASONS", "ExitParams", "PositionForExit", "decide_exit", "exit_route"]

EXIT_REASONS: Final[tuple[str, ...]] = (
    "sell_now",
    "rug_signal",
    "creator_dump",
    "migrated",
    "curve_complete",
    "target",
    "trailing",
    "time_stop",
    "emergency_auto_close",
)


class ExitParams(MemeModel):
    target_multiple: Decimal = Field(gt=1)
    trailing_from_peak_pct: Decimal = Field(gt=0, lt=1)
    time_stop_s: int = Field(ge=1)


class PositionForExit(MemeModel):
    position_id: str = Field(min_length=1)
    mint: str = Field(min_length=32)
    entry_at: datetime
    sol_spent: Decimal = Field(gt=0)
    token_amount: int = Field(gt=0)
    peak_mark_sol: Decimal = Field(ge=0)
    migrated: bool = False
    curve_complete: bool = False


def decide_exit(
    position: PositionForExit,
    mark_sol: Decimal | None,
    now: datetime,
    params: ExitParams,
    *,
    sell_now: bool = False,
    rug_signal: bool = False,
    creator_dump: bool = False,
    emergency_auto_close: bool = False,
) -> str | None:
    """The exit reason that fires now, or ``None``. ``mark_sol`` ``None`` (no usable
    curve state) fires only the rules that do not need a mark: the sale itself
    then waits, degraded, never priced by a fabricated mark (§6)."""
    if sell_now:
        return "sell_now"
    if emergency_auto_close:
        return "emergency_auto_close"
    if rug_signal:
        return "rug_signal"
    if creator_dump:
        return "creator_dump"
    if position.migrated:
        return "migrated"
    if position.curve_complete:
        return "curve_complete"
    held_s = (now - position.entry_at).total_seconds()
    if mark_sol is not None:
        if mark_sol >= params.target_multiple * position.sol_spent:
            return "target"
        peak = max(position.peak_mark_sol, mark_sol)
        if peak > 0 and mark_sol <= peak * (1 - params.trailing_from_peak_pct):
            return "trailing"
    if held_s >= params.time_stop_s:
        return "time_stop"
    return None


def exit_route(position: PositionForExit) -> Literal["curve", "pumpswap"]:
    """After the migration the only way out is the PumpSwap pool (§1, §6)."""
    return "pumpswap" if position.migrated else "curve"
