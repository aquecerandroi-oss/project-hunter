"""Pure fold over one mint's in-memory series (T4.67a): when the +1 s entry
price is available, whether the mint was "born full" before it, and which of
the pre-registered exits fires — reusing
:class:`~hunter_meme_worker.event_state.MintEventState` exactly as the event
gate does (module docstring of ``launch_lane.py``), never a second series.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Final, Literal

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import (
    INITIAL_REAL_TOKEN_RESERVES,
    INITIAL_VIRTUAL_SOL_RESERVES,
    INITIAL_VIRTUAL_TOKEN_RESERVES,
    CurveReserves,
)
from hunter_indicators.meme.drawdown import DEFAULT_MAX_GAP_S, DEFAULT_WINDOW_S
from hunter_meme_worker.features import curve_progress_pct

if TYPE_CHECKING:
    from collections.abc import Collection

    from hunter_meme_worker.event_state import CurvePoint, MintEventState
    from hunter_meme_worker.features_tape import TapeTrade

__all__ = [
    "EXIT_FIRST_THIRD_PARTY_SELL",
    "EXIT_MAX_DRAWDOWN_FROM_PEAK",
    "EXIT_TIME_STOP",
    "ExitDecision",
    "born_full",
    "entry_point",
    "exit_trigger",
    "standard_reserves",
]

EXIT_TIME_STOP: Final = "time_stop"
EXIT_FIRST_THIRD_PARTY_SELL: Final = "first_third_party_sell"
EXIT_MAX_DRAWDOWN_FROM_PEAK: Final = "max_drawdown_from_peak"

HUNDRED: Final = Decimal(100)

_VIRTUAL_MINUS_REAL_OFFSET: Final = INITIAL_VIRTUAL_TOKEN_RESERVES - INITIAL_REAL_TOKEN_RESERVES
_CONSTANT_PRODUCT: Final = INITIAL_VIRTUAL_SOL_RESERVES * INITIAL_VIRTUAL_TOKEN_RESERVES
"""Both invariant for the life of a *standard* curve: every buy/sell moves the
real and the virtual token reserve by the same quantity (asserted against
``reserves_after_buy``/``reserves_after_sell`` by test), so their difference
never changes; and ``S*T=k`` is the formula's own identity (``curve.py``'s
own proof, ``quote_buy``/``quote_sell`` preserve it exactly)."""


def standard_reserves(point: CurvePoint) -> CurveReserves:
    """The virtual reserves at ``point`` — reconstructed from the real token
    reserve alone, since the launch lane only ever prices a curve the gate
    already confirmed standard (``evaluate_launch`` refuses ``mayhem``/
    ``mayhem_unknown`` before a subscription ever opens, so this is the only
    reconstruction the lane needs)."""
    with localcontext(CONTEXT):
        virtual_token = point.real_token + _VIRTUAL_MINUS_REAL_OFFSET
        virtual_sol = _CONSTANT_PRODUCT / virtual_token
    return CurveReserves(
        virtual_sol_reserves=virtual_sol,
        virtual_token_reserves=virtual_token,
        real_token_reserves=point.real_token,
        initial_real_token_reserves=INITIAL_REAL_TOKEN_RESERVES,
        complete=False,
    )


def entry_point(
    state: MintEventState, *, created_at: datetime, entry_delay_s: int, as_of: datetime
) -> CurvePoint | None:
    """The first observed point at or after ``created_at + entry_delay_s`` that
    had reached us by ``as_of`` — never a later, cheaper-looking one (the same
    non-anticipation rule ``pick_fill_snapshot`` applies to the Lab's own fill)."""
    deadline = created_at + timedelta(seconds=entry_delay_s)
    candidates = [p for p in state.points if p.observed_at >= deadline and p.received_at <= as_of]
    return min(candidates, key=lambda p: p.observed_at) if candidates else None


def born_full(
    state: MintEventState,
    *,
    created_at: datetime,
    initial_real_token_reserves: Decimal | None,
    window_s: int,
    threshold_pct: int,
    as_of: datetime,
) -> bool:
    """KB-0123's "nasce cheia": progress at or above ``threshold_pct`` at any
    point observed within ``window_s`` of ``created_at`` and received by
    ``as_of``. ``False`` (never "unknown") without a denominator — the caller
    already refused a launch it could not reconstruct, so this only runs once
    that reconstruction exists."""
    if initial_real_token_reserves is None:
        return False
    horizon = created_at + timedelta(seconds=window_s)
    for point in state.points:
        if point.received_at > as_of or point.observed_at > horizon:
            continue
        progress = curve_progress_pct(point.real_token, initial_real_token_reserves)
        if progress is not None and progress * HUNDRED >= threshold_pct:
            return True
    return False


@dataclass(frozen=True, slots=True)
class ExitDecision:
    reason: Literal["time_stop", "first_third_party_sell", "max_drawdown_from_peak"]
    point: CurvePoint


def exit_trigger(
    state: MintEventState,
    *,
    entered_at: datetime,
    time_stop_s: int,
    exit_on_first_third_party_sell: bool,
    max_drawdown_from_peak_pct: Decimal,
    creation_buyers: Collection[str],
    latest_trade: TapeTrade | None,
    as_of: datetime,
) -> ExitDecision | None:
    """The first pre-registered exit that fires — checked once per incoming
    notification (``latest_trade`` = the trade that notification carried, or
    ``None`` for the orchestrator's own periodic time-stop sweep of a mint
    that has gone quiet). ``None`` when nothing in ``state`` prices an exit
    yet: the caller never sells into a mint it has not observed."""
    point = state.newest_point
    if point is None:
        return None
    if as_of >= entered_at + timedelta(seconds=time_stop_s):
        return ExitDecision(EXIT_TIME_STOP, point)
    if (
        exit_on_first_third_party_sell
        and latest_trade is not None
        and latest_trade.side == "sell"
        and latest_trade.trader not in creation_buyers
        and latest_trade.block_time >= entered_at
    ):
        return ExitDecision(EXIT_FIRST_THIRD_PARTY_SELL, point)
    drawdown = state.recent_drawdown(as_of, window_s=DEFAULT_WINDOW_S, max_gap_s=DEFAULT_MAX_GAP_S)
    if (
        drawdown.drawdown_pct is not None
        and drawdown.drawdown_pct * HUNDRED >= max_drawdown_from_peak_pct
    ):
        return ExitDecision(EXIT_MAX_DRAWDOWN_FROM_PEAK, point)
    return None
