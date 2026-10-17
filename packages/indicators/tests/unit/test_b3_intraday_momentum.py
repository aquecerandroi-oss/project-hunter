"""H-038 pure decision (``hunter_indicators.b3.intraday_momentum``) — synthetic, known values.

Plan: ``docs/plans/MERCADO-TRADICIONAL.md`` §1.2 and §1.6. Every instant is UTC; BRT
(UTC−3, no daylight saving since 2019) appears only in the comments.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hunter_indicators.b3.calendar_2026 import WIN_SPEC, b3_session
from hunter_indicators.b3.contract import (
    IndexReading,
    IndexReadings,
    NoTrade,
    NoTradeReason,
    SessionTimes,
    Side,
    Signal,
)
from hunter_indicators.b3.intraday_momentum import (
    H038_V1,
    R1_DEFINITION,
    decide_intraday_momentum,
    entry_window,
    exit_instant,
    protective_stop,
    r1_log_return,
)

pytestmark = pytest.mark.unit

# Monday 19/10/2026: O = 10:00 BRT = 13:00Z, C = 17:00 BRT = 20:00Z; previous session Fri 16/10.
SESSION = SessionTimes(
    trading_date=date(2026, 10, 19),
    open_at=datetime(2026, 10, 19, 13, 0, tzinfo=UTC),
    close_at=datetime(2026, 10, 19, 20, 0, tzinfo=UTC),
    previous_close_at=datetime(2026, 10, 16, 20, 0, tzinfo=UTC),
)
O30 = SESSION.open_at + timedelta(minutes=30)
O90 = SESSION.open_at + timedelta(minutes=90)


def _close(value: str = "130000.00") -> IndexReading:
    return IndexReading(
        value=Decimal(value),
        event_at=SESSION.previous_close_at,
        received_at=SESSION.previous_close_at + timedelta(minutes=40),
        source="manual:mt5-chart",
    )


def _o30(value: str, received_at: datetime | None = None, event_at: datetime = O30) -> IndexReading:
    return IndexReading(
        value=Decimal(value),
        event_at=event_at,
        received_at=received_at or O30 + timedelta(minutes=12),
        source="manual:mt5-chart",
    )


def _readings(
    o30: IndexReading | None, decision_at: datetime | None = None, close: str = "130000.00"
) -> IndexReadings:
    return IndexReadings(
        previous_close=_close(close),
        first_half_hour=o30,
        decision_at=decision_at or O30 + timedelta(minutes=15),
    )


def _decide(o30: IndexReading | None, **kw: object) -> Signal | NoTrade:
    return decide_intraday_momentum(_readings(o30, **kw), SESSION, H038_V1)  # type: ignore[arg-type]


# ---------------------------------------------------------------- known values


def test_index_above_previous_close_is_a_buy_with_the_known_r1_and_times() -> None:
    out = _decide(_o30("131300.00"))
    assert isinstance(out, Signal)
    assert out.side is Side.BUY
    # ln(131300 / 130000) = ln(1.01) = 0.00995033085316808284821535754426...
    assert abs(out.r1 - Decimal("0.009950330853168082848215357544")) < Decimal("1e-28")
    assert out.entry_window_start == datetime(2026, 10, 19, 19, 30, tzinfo=UTC)  # 16:30 BRT
    assert out.entry_window_end == datetime(2026, 10, 19, 19, 35, tzinfo=UTC)  # 16:35 BRT
    assert out.exit_at == datetime(2026, 10, 19, 20, 0, tzinfo=UTC)  # 17:00 BRT
    assert out.targets == ()
    assert out.expected_holding == timedelta(minutes=30)
    assert out.params_version == H038_V1.version
    assert out.supporting_features[R1_DEFINITION.key] == str(out.r1)


def test_index_below_previous_close_is_a_sell() -> None:
    out = _decide(_o30("128700.00"))
    assert isinstance(out, Signal)
    assert out.side is Side.SELL
    assert out.r1 < 0


def test_unchanged_index_is_no_trade_with_r1_zero() -> None:
    out = _decide(_o30("130000.00"))
    assert isinstance(out, NoTrade)
    assert out.reason is NoTradeReason.ZERO_RETURN
    assert out.r1 == 0


def test_r1_is_registered_as_a_versioned_feature_definition() -> None:
    assert R1_DEFINITION.key == "ibov_r1_open30"
    assert R1_DEFINITION.version == 1
    assert not R1_DEFINITION.is_live
    assert R1_DEFINITION.params["signal_offset_minutes"] == 30


# ---------------------------------------------------------------- stop rounding


def test_stop_is_rounded_to_tick_by_side_with_known_values() -> None:
    # 207150 × 0.995 = 206114.25 → down to 206110; 207150 × 1.005 = 208185.75 → up to 208190
    assert protective_stop(Decimal("207150"), Side.BUY, H038_V1, WIN_SPEC) == Decimal("206110")
    assert protective_stop(Decimal("207150"), Side.SELL, H038_V1, WIN_SPEC) == Decimal("208190")


def test_stop_already_on_tick_is_not_moved() -> None:
    # 200000 × 0.995 = 199000 (on tick) and × 1.005 = 201000 (on tick)
    assert protective_stop(Decimal("200000"), Side.BUY, H038_V1, WIN_SPEC) == Decimal("199000")
    assert protective_stop(Decimal("200000"), Side.SELL, H038_V1, WIN_SPEC) == Decimal("201000")


def test_entry_price_off_tick_is_refused() -> None:
    with pytest.raises(ValueError, match="tick"):
        protective_stop(Decimal("207152"), Side.BUY, H038_V1, WIN_SPEC)


def test_signal_exposes_the_stop_for_an_entry_price() -> None:
    out = _decide(_o30("131300.00"))
    assert isinstance(out, Signal)
    assert out.stop_price(Decimal("207150"), WIN_SPEC) == Decimal("206110")


@settings(max_examples=300, deadline=None)
@given(ticks=st.integers(min_value=10_000, max_value=80_000), side=st.sampled_from(Side))
def test_stop_property_on_tick_beyond_the_fraction_and_within_one_tick(
    ticks: int, side: Side
) -> None:
    tick = WIN_SPEC.tick_size
    entry = tick * ticks
    stop = protective_stop(entry, side, H038_V1, WIN_SPEC)
    assert stop % tick == 0
    if side is Side.BUY:
        raw = entry * (1 - H038_V1.stop_fraction)
        assert stop <= raw < stop + tick
        assert stop < entry
    else:
        raw = entry * (1 + H038_V1.stop_fraction)
        assert stop - tick < raw <= stop
        assert stop > entry


# ---------------------------------------------------------------- sign symmetry

_INDEX = st.decimals(min_value=Decimal("50000"), max_value=Decimal("300000"), places=2)


@settings(max_examples=300, deadline=None)
@given(a=_INDEX, b=_INDEX)
def test_sign_symmetry_swapping_close_and_reading_flips_side_and_r1(a: Decimal, b: Decimal) -> None:
    forward = decide_intraday_momentum(_readings(_o30(str(b)), close=str(a)), SESSION, H038_V1)
    backward = decide_intraday_momentum(_readings(_o30(str(a)), close=str(b)), SESSION, H038_V1)
    assert r1_log_return(a, b) == -r1_log_return(b, a)
    if a == b:
        assert isinstance(forward, NoTrade) and isinstance(backward, NoTrade)
        return
    assert isinstance(forward, Signal) and isinstance(backward, Signal)
    assert forward.side is (Side.BUY if b > a else Side.SELL)
    assert {forward.side, backward.side} == {Side.BUY, Side.SELL}
    assert forward.r1 == -backward.r1
    assert (forward.r1 > 0) == (forward.side is Side.BUY)


# ---------------------------------------------------------------- no look-ahead


@settings(max_examples=200, deadline=None)
@given(early=st.integers(min_value=1, max_value=6 * 3600))
def test_no_decision_before_the_reading_exists(early: int) -> None:
    decision_at = O30 - timedelta(seconds=early)
    out = _decide(_o30("131300.00", received_at=O30), decision_at=decision_at)
    assert isinstance(out, NoTrade)
    assert out.reason is NoTradeReason.NOT_YET_RECEIVED


def test_decision_before_the_reading_was_received_is_refused() -> None:
    received = O30 + timedelta(minutes=20)
    out = _decide(
        _o30("131300.00", received_at=received), decision_at=received - timedelta(seconds=1)
    )
    assert isinstance(out, NoTrade)
    assert out.reason is NoTradeReason.NOT_YET_RECEIVED


def test_reading_received_before_its_event_is_refused() -> None:
    out = _decide(_o30("131300.00", received_at=O30 - timedelta(seconds=1)))
    assert isinstance(out, NoTrade)
    assert out.reason is NoTradeReason.RECEIVED_BEFORE_EVENT


@pytest.mark.parametrize("minutes", [29, 31, 45])
def test_a_reading_of_another_bar_than_the_one_ending_at_o30_is_refused(minutes: int) -> None:
    """The forming or a later bar must never stand in for the O+30 close."""
    event = SESSION.open_at + timedelta(minutes=minutes)
    out = _decide(_o30("131300.00", event_at=event, received_at=O30 + timedelta(minutes=20)))
    assert isinstance(out, NoTrade)
    assert out.reason is NoTradeReason.READING_NOT_AT_SIGNAL_TIME


def test_previous_close_from_an_older_session_or_from_today_is_refused() -> None:
    for event in (SESSION.previous_close_at - timedelta(days=1), SESSION.open_at):
        stale = replace(_close(), event_at=event, received_at=event + timedelta(minutes=1))
        readings = IndexReadings(stale, _o30("131300.00"), O30 + timedelta(minutes=15))
        out = decide_intraday_momentum(readings, SESSION, H038_V1)
        assert isinstance(out, NoTrade)
        assert out.reason is NoTradeReason.PREVIOUS_CLOSE_NOT_PREVIOUS_SESSION


@settings(max_examples=200, deadline=None)
@given(later=st.integers(min_value=0, max_value=8 * 3600))
def test_the_signal_does_not_depend_on_when_it_is_evaluated(later: int) -> None:
    """Panel at 10:45 and robot replay hours later must publish the same signal."""
    first = _decide(_o30("128700.00"))
    again = _decide(_o30("128700.00"), decision_at=O30 + timedelta(minutes=12, seconds=later))
    assert first == again


def test_missing_reading_is_no_trade() -> None:
    out = _decide(None)
    assert isinstance(out, NoTrade)
    assert out.reason is NoTradeReason.READING_MISSING


# ---------------------------------------------------------------- deadline O+90


def test_reading_received_exactly_at_the_deadline_is_accepted() -> None:
    out = _decide(_o30("131300.00", received_at=O90), decision_at=O90)
    assert isinstance(out, Signal)


@settings(max_examples=100, deadline=None)
@given(late=st.integers(min_value=1, max_value=6 * 3600))
def test_reading_received_after_the_deadline_is_refused(late: int) -> None:
    received = O90 + timedelta(seconds=late)
    out = _decide(_o30("131300.00", received_at=received), decision_at=received)
    assert isinstance(out, NoTrade)
    assert out.reason is NoTradeReason.RECEIVED_AFTER_DEADLINE


def test_previous_close_received_after_the_deadline_is_refused() -> None:
    late_close = replace(_close(), received_at=O90 + timedelta(seconds=1))
    readings = IndexReadings(late_close, _o30("131300.00"), O90 + timedelta(minutes=1))
    out = decide_intraday_momentum(readings, SESSION, H038_V1)
    assert isinstance(out, NoTrade)
    assert out.reason is NoTradeReason.RECEIVED_AFTER_DEADLINE


# ---------------------------------------------------------------- session exclusions


@pytest.mark.parametrize(
    "reason",
    [
        NoTradeReason.SHORTENED_SESSION,
        NoTradeReason.WIN_EXPIRY_DAY,
        NoTradeReason.KNOWN_IMPEDIMENT,
    ],
)
def test_excluded_sessions_never_trade_whatever_the_readings(reason: NoTradeReason) -> None:
    session = replace(SESSION, exclusions=(reason,))
    out = decide_intraday_momentum(_readings(_o30("131300.00")), session, H038_V1)
    assert isinstance(out, NoTrade)
    assert out.reason is reason


def test_half_day_with_a_late_open_is_excluded_even_with_valid_late_readings() -> None:
    """A shortened session (e.g. 13:00 BRT open) is excluded before entry (plan §1.2)."""
    late_open = datetime(2026, 10, 19, 16, 0, tzinfo=UTC)
    session = replace(SESSION, open_at=late_open, exclusions=(NoTradeReason.SHORTENED_SESSION,))
    o30 = _o30("131300.00", event_at=late_open + timedelta(minutes=30))
    out = decide_intraday_momentum(
        _readings(o30, decision_at=late_open + timedelta(minutes=50)), session, H038_V1
    )
    assert isinstance(out, NoTrade)
    assert out.reason is NoTradeReason.SHORTENED_SESSION


def test_only_session_level_reasons_can_exclude_a_session() -> None:
    with pytest.raises(ValueError, match="session"):
        replace(SESSION, exclusions=(NoTradeReason.ZERO_RETURN,))


# ---------------------------------------------------------------- 17:00 → 18:00 on 03/11


def test_grid_switch_moves_entry_and_exit_one_hour_later_on_3_november() -> None:
    before = b3_session(date(2026, 10, 30))
    after = b3_session(date(2026, 11, 3))
    assert before is not None and after is not None
    assert exit_instant(before) == datetime(2026, 10, 30, 20, 0, tzinfo=UTC)  # 17:00 BRT
    assert entry_window(before, H038_V1) == (
        datetime(2026, 10, 30, 19, 30, tzinfo=UTC),
        datetime(2026, 10, 30, 19, 35, tzinfo=UTC),
    )
    assert exit_instant(after) == datetime(2026, 11, 3, 21, 0, tzinfo=UTC)  # 18:00 BRT
    assert entry_window(after, H038_V1) == (
        datetime(2026, 11, 3, 20, 30, tzinfo=UTC),  # 17:30 BRT
        datetime(2026, 11, 3, 20, 35, tzinfo=UTC),  # 17:35 BRT
    )


def test_first_session_after_the_switch_reads_the_close_of_the_old_grid() -> None:
    after = b3_session(date(2026, 11, 3))
    assert after is not None
    close = IndexReading(
        Decimal("130000"),
        after.previous_close_at,
        after.previous_close_at + timedelta(hours=1),
        "manual",
    )
    o30 = IndexReading(
        Decimal("129000"),
        after.open_at + timedelta(minutes=30),
        after.open_at + timedelta(minutes=40),
        "manual",
    )
    out = decide_intraday_momentum(
        IndexReadings(close, o30, after.open_at + timedelta(minutes=41)), after, H038_V1
    )
    assert isinstance(out, Signal)
    assert out.side is Side.SELL
    assert out.exit_at == datetime(2026, 11, 3, 21, 0, tzinfo=UTC)


# ---------------------------------------------------------------- input hygiene


def test_naive_datetimes_are_refused() -> None:
    with pytest.raises(ValueError, match="aware"):
        IndexReading(Decimal("1"), datetime(2026, 10, 19, 13, 30), O30, "manual")  # noqa: DTZ001


def test_non_positive_or_non_finite_index_values_are_refused() -> None:
    for bad in ("0", "-1", "NaN", "Infinity"):
        with pytest.raises(ValueError, match="positive"):
            IndexReading(Decimal(bad), O30, O30, "manual")


def test_session_times_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="order"):
        replace(SESSION, close_at=SESSION.open_at)


def test_stop_does_not_depend_on_the_callers_decimal_context() -> None:
    """Astra (b3-intraday-momentum-module, must-fix 5): prec 6 used to give 205970."""
    from decimal import localcontext

    # 207005 × 0.995 = 205969.975 → down to tick = 205965
    with localcontext() as ctx:
        ctx.prec = 6
        low = protective_stop(Decimal("207005"), Side.BUY, H038_V1, WIN_SPEC)
        high = protective_stop(Decimal("207005"), Side.SELL, H038_V1, WIN_SPEC)
    assert low == Decimal("205965")
    assert high == Decimal("208045")  # 207005 × 1.005 = 208040.025 → up to 208045


def test_r1_does_not_depend_on_the_callers_decimal_context() -> None:
    from decimal import localcontext

    expected = r1_log_return(Decimal("130000.00"), Decimal("131300.00"))
    with localcontext() as ctx:
        ctx.prec = 5
        assert r1_log_return(Decimal("130000.00"), Decimal("131300.00")) == expected
