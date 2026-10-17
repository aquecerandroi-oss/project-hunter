"""OHLC 1-minute trade simulator of the WIN family — synthetic bars with known results (tests only).

Session 04/03/2024, OPEN = 13:00Z. Long plan decided at OPEN+32 with stop 119 900; entry bar at
OPEN+32 opens 120 100 → fill 120 105 (1 tick of slippage); B3 fee 1.28 pt per leg.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.b3.bars import Bar
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.intraday_plan import TradePlan
from infra.research.b3.simulate import WIN_COSTS, Costs, ExitReason, Status, simulate

pytestmark = pytest.mark.unit

OPEN = datetime(2024, 3, 4, 13, 0, tzinfo=UTC)
DECIDED = OPEN + timedelta(minutes=32)
EXIT = OPEN + timedelta(minutes=390)
FEES = Decimal("2.56")


def b(minute: int, o: int, h: int, low: int, c: int) -> Bar:
    return Bar(
        OPEN + timedelta(minutes=minute), 1, Decimal(o), Decimal(h), Decimal(low), Decimal(c)
    )


def path(
    overrides: dict[int, Bar] | None = None, drop: set[int] | None = None, exit_open: int = 120300
) -> list[Bar]:
    bars = {m: b(m, 120100, 120120, 120050, 120100) for m in range(32, 390)}
    bars[390] = b(390, exit_open, exit_open + 10, exit_open - 10, exit_open)
    bars.update(overrides or {})
    return [bars[m] for m in sorted(bars) if m not in (drop or set())]


def plan(
    side: Side = Side.BUY,
    stop_level: Decimal | None = Decimal(119900),
    stop_fraction: Decimal | None = None,
    target_r: Decimal | None = None,
    exit_at: datetime = EXIT,
) -> TradePlan:
    return TradePlan(
        strategy="test/1",
        trading_date=date(2024, 3, 4),
        side=side,
        decided_at=DECIDED,
        exit_at=exit_at,
        stop_level=stop_level,
        stop_fraction=stop_fraction,
        target_r=target_r,
        reason="synthetic",
    )


def bp(points: Decimal, entry: Decimal) -> Decimal:
    return points / entry * Decimal(10000)


def test_time_exit_pays_slippage_on_both_legs_and_the_fees() -> None:
    out = simulate(plan(), path())
    assert out.status is Status.OK and out.exit_reason is ExitReason.TIME
    assert (out.entry_price, out.exit_price) == (Decimal(120105), Decimal(120295))
    assert out.net_points == Decimal(190) - FEES
    assert out.net_bp == bp(Decimal(190) - FEES, Decimal(120105))
    assert out.gross_raw_points == Decimal(200)  # 120 300 − 120 100, no cost, no slippage
    assert out.stress_bp == out.net_bp


def test_stop_touch_exits_at_the_level_minus_a_tick() -> None:
    out = simulate(plan(), path({40: b(40, 120000, 120010, 119900, 119950)}))
    assert out.exit_reason is ExitReason.STOP
    assert out.exit_price == Decimal(119895)
    assert out.net_points == Decimal(119895 - 120105) - FEES


def test_gap_beyond_the_stop_exits_at_the_open() -> None:
    out = simulate(plan(), path({40: b(40, 119800, 119850, 119700, 119820)}))
    assert out.exit_reason is ExitReason.STOP_GAP and out.exit_price == Decimal(119795)


def test_target_and_stop_in_the_same_bar_is_a_stop() -> None:
    both = b(40, 120100, 121000, 119800, 120000)
    out = simulate(plan(target_r=Decimal(2)), path({40: both}))
    assert out.exit_reason is ExitReason.STOP


def test_target_is_r_multiples_of_the_fill_rounded_away_and_exits_without_improvement() -> None:
    # R = 120 105 − 119 900 = 205; 2R → 120 515; bar opens above it → still filled at the level
    out = simulate(plan(target_r=Decimal(2)), path({40: b(40, 120600, 120700, 120550, 120650)}))
    assert out.exit_reason is ExitReason.TARGET and out.target_price == Decimal(120515)
    assert out.exit_price == Decimal(120510)
    out15 = simulate(plan(target_r=Decimal("1.5")), path())  # 120 412.5 → 120 415
    assert out15.target_price == Decimal(120415)


def test_stop_on_the_wrong_side_of_the_fill_exits_at_the_entry_bar_open() -> None:
    out = simulate(plan(), path({32: b(32, 119895, 119900, 119890, 119895)}))
    assert out.exit_reason is ExitReason.STOP_AT_ENTRY
    assert (out.entry_price, out.exit_price) == (Decimal(119900), Decimal(119890))
    assert out.net_points == Decimal(-10) - FEES


def test_entry_needs_a_bar_within_five_minutes() -> None:
    late = path(drop={32, 33, 34, 35, 36, 37})
    assert simulate(plan(), late).status is Status.NO_ENTRY
    ok = simulate(plan(), path(drop={32, 33, 34, 35, 36}))  # bar at OPEN+37 = decided + 5 min
    assert ok.status is Status.OK and ok.entry_time == OPEN + timedelta(minutes=37)


def test_a_hole_after_entry_censors_even_after_a_stop_and_stresses_to_the_worst() -> None:
    out = simulate(plan(), path({40: b(40, 119800, 119850, 119700, 119820)}, drop={100}))
    assert out.status is Status.CENSORED and out.net_bp is None
    # worst of stop (119 900) and the lowest observed low (119 700), minus a tick
    assert out.stress_bp == bp(Decimal(119695 - 120105) - FEES, Decimal(120105))
    quiet = simulate(plan(), path(drop={100}))
    assert quiet.stress_bp == bp(Decimal(119895 - 120105) - FEES, Decimal(120105))


def test_missing_exit_bar_censors() -> None:
    out = simulate(plan(), path(drop={390}))
    assert out.status is Status.CENSORED


def test_flip_mirrors_the_stop_around_the_raw_entry_open() -> None:
    out = simulate(plan(), path(), flip=True)
    assert out.side is Side.SELL
    assert out.entry_price == Decimal(120095)
    assert out.stop_price == Decimal(120300)  # 2 × 120 100 − 119 900
    assert out.exit_reason is ExitReason.TIME and out.exit_price == Decimal(120305)
    assert out.net_points == Decimal(120095 - 120305) - FEES


def test_fraction_stop_is_rounded_by_side_from_the_fill() -> None:
    out = simulate(plan(Side.SELL, stop_level=None, stop_fraction=Decimal("0.005")), path())
    assert out.entry_price == Decimal(120095)
    assert out.stop_price == Decimal(120700)  # 120 095 × 1.005 = 120 695.475 → up to 120 700


def test_two_tick_sensitivity() -> None:
    out = simulate(
        plan(), path(), costs=Costs(fee_points_per_leg=Decimal("1.28"), slippage_ticks=2)
    )
    assert (out.entry_price, out.exit_price) == (Decimal(120110), Decimal(120290))
    assert WIN_COSTS.slippage_ticks == 1 and WIN_COSTS.fee_points_per_leg == Decimal("1.28")


def test_flip_mirrors_a_fraction_stop_of_the_rule_side() -> None:
    # Astra's case: raw open 100 000; the buy's stop is 0.5 % under 100 005 → 99 500, so the
    # mirrored sell's stop is 100 500 — not 0.5 % over the sell's own fill (100 495).
    bars = [b(m, 100000, 100010, 99990, 100000) for m in range(32, 391)]
    out = simulate(plan(stop_level=None, stop_fraction=Decimal("0.005")), bars, flip=True)
    assert out.side is Side.SELL and out.entry_price == Decimal(99995)
    assert out.stop_price == Decimal(100500)


def test_raw_entry_is_kept_for_the_gross_descriptive() -> None:
    out = simulate(plan(), path())
    assert out.raw_entry == Decimal(120100)
