"""Exit rules (§6): precedence, the three time/price rules, and no mark ⇒ only
the rules that need no mark."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_risk_meme import EXIT_REASONS, ExitParams, PositionForExit, decide_exit, exit_route

from .factories import AS_OF, MINT

pytestmark = pytest.mark.unit

PARAMS = ExitParams(
    target_multiple=Decimal("2"), trailing_from_peak_pct=Decimal("0.30"), time_stop_s=900
)


def position(**over: object) -> PositionForExit:
    base: dict[str, object] = {
        "position_id": "pos",
        "mint": MINT,
        "entry_at": AS_OF - timedelta(seconds=60),
        "sol_spent": Decimal("0.05"),
        "token_amount": 1000,
        "peak_mark_sol": Decimal("0.05"),
    }
    base.update(over)
    return PositionForExit(**base)  # type: ignore[arg-type]


def test_nothing_fires_on_a_quiet_position() -> None:
    assert decide_exit(position(), Decimal("0.05"), AS_OF, PARAMS) is None


def test_target_fires_at_the_multiple() -> None:
    assert decide_exit(position(), Decimal("0.10"), AS_OF, PARAMS) == "target"


def test_trailing_measures_from_the_peak() -> None:
    assert (
        decide_exit(position(peak_mark_sol=Decimal("0.09")), Decimal("0.063"), AS_OF, PARAMS)
        == "trailing"
    )
    assert (
        decide_exit(position(peak_mark_sol=Decimal("0.09")), Decimal("0.064"), AS_OF, PARAMS)
        is None
    )


def test_time_stop_fires_by_age_even_without_a_mark() -> None:
    old = position(entry_at=AS_OF - timedelta(seconds=900))
    assert decide_exit(old, None, AS_OF, PARAMS) == "time_stop"
    assert decide_exit(position(), None, AS_OF, PARAMS) is None


def test_precedence_sell_now_then_emergency_then_rug_then_creator_then_venue() -> None:
    old = position(entry_at=AS_OF - timedelta(seconds=9000), migrated=True)
    assert (
        decide_exit(old, Decimal("1"), AS_OF, PARAMS, sell_now=True, rug_signal=True) == "sell_now"
    )
    assert (
        decide_exit(old, Decimal("1"), AS_OF, PARAMS, emergency_auto_close=True, rug_signal=True)
        == "emergency_auto_close"
    )
    assert (
        decide_exit(old, Decimal("1"), AS_OF, PARAMS, rug_signal=True, creator_dump=True)
        == "rug_signal"
    )
    assert decide_exit(old, Decimal("1"), AS_OF, PARAMS, creator_dump=True) == "creator_dump"
    assert decide_exit(old, Decimal("1"), AS_OF, PARAMS) == "migrated"
    assert (
        decide_exit(position(curve_complete=True), Decimal("0.05"), AS_OF, PARAMS)
        == "curve_complete"
    )


def test_every_reason_is_declared() -> None:
    assert set(EXIT_REASONS) >= {"sell_now", "target", "trailing", "time_stop", "migrated"}


def test_route_is_pumpswap_only_after_the_migration() -> None:
    assert exit_route(position()) == "curve"
    assert exit_route(position(migrated=True)) == "pumpswap"
