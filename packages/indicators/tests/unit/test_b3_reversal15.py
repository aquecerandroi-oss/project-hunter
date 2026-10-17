"""H-040 15-minute reversal on the WIN (``hunter_indicators.b3.reversal15``) — synthetic fixtures.

Session Monday 04/03/2024: OPEN = 10:00 BRT = 13:00Z, time exit 16:30 BRT = 19:30Z.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.b3.bars import Bar
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.intraday_plan import IntradayWindow
from hunter_indicators.b3.reversal15 import BAR_SIGN_DEFINITION, REVERSAL15_V1, scan_reversal

pytestmark = pytest.mark.unit

OPEN = datetime(2024, 3, 4, 13, 0, tzinfo=UTC)
WINDOW = IntradayWindow(date(2024, 3, 4), open_at=OPEN, exit_at=OPEN + timedelta(minutes=390))


def minute_bar(minute: int, o: int, c: int) -> Bar:
    return Bar(
        OPEN + timedelta(minutes=minute),
        1,
        Decimal(o),
        Decimal(max(o, c) + 5),
        Decimal(min(o, c) - 5),
        Decimal(c),
    )


def session(direction_by_bucket: dict[int, int], minutes: int = 15) -> list[Bar]:
    """Each bucket drifts +10 (up), −10 (down) or 0 over its minutes; flat by default."""
    bars: list[Bar] = []
    price = 120000
    for m in range(390):
        j = m // minutes
        step = direction_by_bucket.get(j, 0)
        last = m % minutes == minutes - 1
        close = price + (step if last else 0)
        bars.append(minute_bar(m, price, close))
        price = close
    return bars


def test_frozen_parameters_and_feature_definition() -> None:
    assert REVERSAL15_V1.version == "reversal15_win/1"
    assert REVERSAL15_V1.bar_minutes == 15
    assert REVERSAL15_V1.stop_fraction == Decimal("0.005")
    assert REVERSAL15_V1.max_trades == 25
    assert BAR_SIGN_DEFINITION.key == "win_bar_sign_15m" and BAR_SIGN_DEFINITION.version == 1


def test_up_bar_sells_down_bar_buys_doji_does_nothing() -> None:
    plans = scan_reversal(session({0: 10, 1: -10, 2: 0}), WINDOW, REVERSAL15_V1)
    assert [(p.side, p.decided_at) for p in plans] == [
        (Side.SELL, OPEN + timedelta(minutes=15)),
        (Side.BUY, OPEN + timedelta(minutes=30)),
    ]
    first = plans[0]
    assert first.exit_at == OPEN + timedelta(minutes=30)
    assert first.stop_fraction == Decimal("0.005") and first.stop_level is None
    assert first.target_r is None
    assert first.supporting_features["bar_open"] == "120000"
    assert first.supporting_features["bar_close"] == "120010"


def test_decision_grid_is_open_plus_delta_to_exit_minus_delta() -> None:
    every = {j: (10 if j % 2 == 0 else -10) for j in range(26)}
    plans = scan_reversal(session(every), WINDOW, REVERSAL15_V1)
    assert len(plans) == 25
    assert plans[0].decided_at == OPEN + timedelta(minutes=15)
    assert plans[-1].decided_at == OPEN + timedelta(minutes=375)  # 16:15 BRT
    assert plans[-1].exit_at == WINDOW.exit_at


@pytest.mark.parametrize(("minutes", "expected"), [(10, 38), (30, 12)])
def test_neighbour_bar_lengths_keep_the_same_grid_rule(minutes: int, expected: int) -> None:
    params = replace(REVERSAL15_V1, version=f"reversal15_win/1@bar{minutes}", bar_minutes=minutes)
    assert params.max_trades == expected
    every = {j: 10 for j in range(390 // minutes)}
    plans = scan_reversal(session(every, minutes), WINDOW, params)
    assert len(plans) == expected
    assert plans[-1].exit_at == WINDOW.exit_at
    assert all(p.side is Side.SELL for p in plans)


def test_empty_bucket_gives_no_decision() -> None:
    bars = [
        b for b in session({0: 10, 1: -10}) if not 15 <= (b.start - OPEN).total_seconds() / 60 < 30
    ]
    plans = scan_reversal(bars, WINDOW, REVERSAL15_V1)
    assert [p.decided_at for p in plans] == [OPEN + timedelta(minutes=15)]


def test_changing_bars_after_a_decision_never_changes_it() -> None:
    base = session({0: 10, 3: -10, 7: 10})
    plans = scan_reversal(base, WINDOW, REVERSAL15_V1)
    cut = plans[1].decided_at
    future = [
        b
        if b.end <= cut
        else minute_bar(int((b.start - OPEN).total_seconds() // 60), 100000, 100500)
        for b in base
    ]
    changed = scan_reversal(future, WINDOW, REVERSAL15_V1)
    assert [p for p in changed if p.decided_at <= cut] == [p for p in plans if p.decided_at <= cut]
