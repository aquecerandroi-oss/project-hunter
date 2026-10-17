"""H-038 — market intraday momentum on the WIN, as one pure decision.

The rule (``docs/plans/MERCADO-TRADICIONAL.md`` §1.2, frozen in the Fila de Hipóteses as
H-038 on 2026-10-17 17:56:30Z): ``r1 = ln(I / F)`` with I the Ibovespa at the close of the
bar ending at O+30 and F the previous official close. r1 > 0 → buy, r1 < 0 → sell, r1 = 0 →
no trade. Enter between C−30 and C−25, catastrophic stop 0.5 % rounded to tick by side, no
target, exit at C, one signal per session.

The manual panel and the future MT5 robot call these same functions. Nothing here reads a
clock or does IO: the readings carry ``event_at`` (the instant the number refers to),
``received_at`` (when we got it) and the explicit ``decision_at``; the decision refuses
anything that would let a later or unseen number decide (``event_at ≤ received_at ≤
decision_at``, the O+30 bar and nothing else, both numbers in by O+90).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Context, Decimal, localcontext

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.b3.contract import (
    IndexReading,
    IndexReadings,
    InstrumentSpec,
    IntradayMomentumParams,
    NoTrade,
    NoTradeReason,
    SessionTimes,
    Side,
    Signal,
    stop_level,
)
from hunter_indicators.features.definitions import FeatureDefinition

H038_V1 = IntradayMomentumParams(
    version="intraday_momentum_win/1",
    signal_offset=timedelta(minutes=30),
    deadline_offset=timedelta(minutes=90),
    entry_before_close=timedelta(minutes=30),
    entry_tolerance=timedelta(minutes=5),
    stop_fraction=Decimal("0.005"),
)
"""The parameters frozen with H-038. Any change is ``intraday_momentum_win/2``."""

R1_DEFINITION = FeatureDefinition(
    key="ibov_r1_open30",
    version=1,
    category=FeatureCategory.MOMENTUM,
    inputs=("ibov:official_close:previous_session", "ibov:bar_close:open+30m"),
    params={"signal_offset_minutes": 30},
    description=(
        "ln of the Ibovespa at the close of the bar ending 30 minutes after the cash-market "
        "open over the previous session's official close (H-038)"
    ),
)

_LN_PRECISION = 34
_R1_PRECISION = 28
"""Logs at 34 digits, the difference rounded once to 28 in an explicit context: r1 does not
depend on the caller's decimal context, and ``r1(a, b) == -r1(b, a)`` holds exactly (a
symmetric rounding of a difference; a 28-digit value negates without rounding)."""

_INVALIDATIONS = (
    "catastrophic stop touched (no re-entry that session)",
    "time exit at C",
    "entry outside [C-30, C-25] is not executed",
)


def r1_log_return(previous_close: Decimal, first_half_hour: Decimal) -> Decimal:
    """``ln(first_half_hour) − ln(previous_close)``, exact antisymmetry under swap."""
    with localcontext(Context(prec=_LN_PRECISION)):
        upper, lower = first_half_hour.ln(), previous_close.ln()
    with localcontext(Context(prec=_R1_PRECISION)):
        return upper - lower


def entry_window(
    session: SessionTimes, params: IntradayMomentumParams
) -> tuple[datetime, datetime]:
    """``[C − entry_before_close, C − entry_before_close + entry_tolerance]``."""
    start = session.close_at - params.entry_before_close
    return start, start + params.entry_tolerance


def exit_instant(session: SessionTimes) -> datetime:
    """The time exit is C itself — the closing settlement window is not an exit price."""
    return session.close_at


def protective_stop(
    entry_price: Decimal, side: Side, params: IntradayMomentumParams, spec: InstrumentSpec
) -> Decimal:
    """The catastrophic stop for a fill at ``entry_price``, rounded to tick by side."""
    return stop_level(entry_price, side, params.stop_fraction, spec)


def _reading_problem(
    reading: IndexReading, decision_at: datetime, deadline: datetime
) -> NoTradeReason | None:
    if reading.received_at < reading.event_at:
        return NoTradeReason.RECEIVED_BEFORE_EVENT
    if reading.received_at > decision_at:
        return NoTradeReason.NOT_YET_RECEIVED
    if reading.received_at > deadline:
        return NoTradeReason.RECEIVED_AFTER_DEADLINE
    return None


def decide_intraday_momentum(
    readings: IndexReadings, session: SessionTimes, params: IntradayMomentumParams
) -> Signal | NoTrade:
    """The H-038 decision for one session, or the counted reason there is none.

    Checks, in order: calendar exclusions (shortened session, WIN expiry, known impediment);
    a missing O+30 reading; a previous close that is not the previous session's; an O+30
    reading of any other bar; then, for both numbers, causality (``event_at ≤ received_at ≤
    decision_at``) and the O+90 deadline; finally r1 = 0.
    """
    day = session.trading_date
    if session.exclusions:
        return NoTrade(day, session.exclusions[0])
    current = readings.first_half_hour
    if current is None:
        return NoTrade(day, NoTradeReason.READING_MISSING)
    previous = readings.previous_close
    if not session.previous_close_at <= previous.event_at < session.open_at:
        return NoTrade(day, NoTradeReason.PREVIOUS_CLOSE_NOT_PREVIOUS_SESSION)
    if current.event_at != session.open_at + params.signal_offset:
        return NoTrade(day, NoTradeReason.READING_NOT_AT_SIGNAL_TIME)
    deadline = session.open_at + params.deadline_offset
    for reading in (previous, current):
        problem = _reading_problem(reading, readings.decision_at, deadline)
        if problem is not None:
            return NoTrade(day, problem)

    r1 = r1_log_return(previous.value, current.value)
    if current.value == previous.value:
        return NoTrade(day, NoTradeReason.ZERO_RETURN, r1=r1)
    side = Side.BUY if current.value > previous.value else Side.SELL
    start, end = entry_window(session, params)
    exit_at = exit_instant(session)
    return Signal(
        trading_date=day,
        side=side,
        r1=r1,
        entry_window_start=start,
        entry_window_end=end,
        exit_at=exit_at,
        stop_fraction=params.stop_fraction,
        params_version=params.version,
        reason="r1_positive" if side is Side.BUY else "r1_negative",
        supporting_features={
            R1_DEFINITION.key: str(r1),
            "ibov_previous_close": str(previous.value),
            "ibov_open30_close": str(current.value),
            "ibov_open30_event_at": current.event_at.isoformat(),
            "ibov_open30_source": current.source,
            "ibov_previous_close_source": previous.source,
        },
        invalidations=_INVALIDATIONS,
        expected_holding=exit_at - start,
    )
