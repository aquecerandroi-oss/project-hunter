"""Look-ahead check on random synthetic sessions (fixtures only) — and a cheat it must catch."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from hunter_indicators.b3.bars import Bar
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.contraction import CONTRACTION_V1, amplitude_profile, scan_contraction
from hunter_indicators.b3.intraday_plan import IntradayWindow, TradePlan
from hunter_indicators.b3.orb import ORB_V1, scan_orb
from hunter_indicators.b3.reversal15 import REVERSAL15_V1, scan_reversal
from infra.research.b3.leakage import lookahead_violations

pytestmark = pytest.mark.unit

DAY = date(2024, 3, 4)
OPEN = datetime(2024, 3, 4, 13, 0, tzinfo=UTC)
WINDOW = IntradayWindow(DAY, open_at=OPEN, exit_at=OPEN + timedelta(minutes=390))


def random_session(seed: int, vol: int = 6) -> list[Bar]:
    """Synthetic random walk on the 5-point grid, 09:00–16:40 BRT (TEST FIXTURE, not data)."""
    rng = np.random.default_rng(seed)
    price = 120000
    bars: list[Bar] = []
    for m in range(-60, 400):
        steps = rng.integers(-vol, vol + 1, size=4) * 5
        path = price + np.cumsum(steps)
        o, c = price, int(path[-1])
        hi = max(o, c, int(path.max())) + 5 * int(rng.integers(0, 3))
        lo = min(o, c, int(path.min())) - 5 * int(rng.integers(0, 3))
        bars.append(
            Bar(OPEN + timedelta(minutes=m), 1, Decimal(o), Decimal(hi), Decimal(lo), Decimal(c))
        )
        price = c
    return bars


def as_list(result: TradePlan | object) -> list[TradePlan]:
    return [result] if isinstance(result, TradePlan) else []


@pytest.mark.parametrize("seed", range(6))
def test_orb_has_no_lookahead(seed: int) -> None:
    def scan(bars: Sequence[Bar]) -> list[TradePlan]:
        return as_list(scan_orb(bars, WINDOW, ORB_V1))

    bars = random_session(seed)
    assert scan(bars), "fixture should produce a breakout"
    assert lookahead_violations(scan, bars) == []


@pytest.mark.parametrize("seed", range(3))
def test_reversal_has_no_lookahead(seed: int) -> None:
    def scan(bars: Sequence[Bar]) -> list[TradePlan]:
        return scan_reversal(bars, WINDOW, REVERSAL15_V1)

    bars = random_session(seed)
    assert len(scan(bars)) > 10
    assert lookahead_violations(scan, bars) == []


@pytest.mark.parametrize("seed", range(4))
def test_contraction_has_no_lookahead(seed: int) -> None:
    wild = random_session(100 + seed, vol=40)
    profiles = [amplitude_profile(wild, WINDOW, CONTRACTION_V1)] * 20

    def scan(bars: Sequence[Bar]) -> list[TradePlan]:
        return as_list(scan_contraction(bars, WINDOW, profiles, CONTRACTION_V1))

    bars = random_session(seed)
    assert scan(bars), "a calm session against wild baselines should arm and break"
    assert lookahead_violations(scan, bars) == []


def cheat_scan(bars: Sequence[Bar]) -> list[TradePlan]:
    """DELIBERATE LOOK-AHEAD (test only): decides at bar i with bar i+1's close."""
    inside = [b for b in bars if WINDOW.open_at <= b.start < WINDOW.exit_at]
    for now, nxt in zip(inside[30:], inside[31:], strict=False):
        if nxt.close > now.close:
            return [
                TradePlan(
                    strategy="cheat/1",
                    trading_date=DAY,
                    side=Side.BUY,
                    decided_at=now.end,
                    exit_at=WINDOW.exit_at,
                    stop_level=now.low,
                    stop_fraction=None,
                    target_r=None,
                    reason="peeks at the next bar",
                )
            ]
    return []


def test_the_check_catches_a_cheat() -> None:
    bars = random_session(1)
    assert cheat_scan(bars)
    assert lookahead_violations(cheat_scan, bars) != []
