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
    assert set(EXIT_REASONS) >= {
        "sell_now",
        "target",
        "trailing",
        "time_stop",
        "migrated",
        "third_party_sell",
    }


def test_third_party_sell_fires_after_a_creator_dump_and_before_the_venue_rules() -> None:
    """T4.67b (launch lane): the first sell by someone who is neither the creator
    nor a creation-slot buyer. The creator's own sell is still ``creator_dump``;
    the flag alone, with no mark, fires (it needs no mark); a quiet position with
    the flag off is untouched."""
    assert decide_exit(position(), None, AS_OF, PARAMS, third_party_sell=True) == "third_party_sell"
    assert (
        decide_exit(
            position(), Decimal("0.05"), AS_OF, PARAMS, creator_dump=True, third_party_sell=True
        )
        == "creator_dump"
    )
    migrated = position(migrated=True)
    assert (
        decide_exit(migrated, Decimal("1"), AS_OF, PARAMS, third_party_sell=True)
        == "third_party_sell"
    )
    assert decide_exit(position(), Decimal("0.05"), AS_OF, PARAMS, third_party_sell=False) is None


def test_the_time_stop_is_in_seconds_so_a_six_second_launch_stop_fires_at_six() -> None:
    six = ExitParams(
        target_multiple=Decimal("2"), trailing_from_peak_pct=Decimal("0.20"), time_stop_s=6
    )
    young = position(entry_at=AS_OF - timedelta(seconds=5, milliseconds=900))
    assert decide_exit(young, Decimal("0.05"), AS_OF, six) is None
    assert (
        decide_exit(position(entry_at=AS_OF - timedelta(seconds=6)), Decimal("0.05"), AS_OF, six)
        == "time_stop"
    )


def test_a_twenty_pct_drawdown_from_the_peak_fires_trailing_with_the_launch_params() -> None:
    six = ExitParams(
        target_multiple=Decimal("2"), trailing_from_peak_pct=Decimal("0.20"), time_stop_s=6
    )
    peaked = position(peak_mark_sol=Decimal("0.10"), entry_at=AS_OF - timedelta(seconds=2))
    assert decide_exit(peaked, Decimal("0.0801"), AS_OF, six) is None
    assert decide_exit(peaked, Decimal("0.08"), AS_OF, six) == "trailing"


def test_route_is_pumpswap_only_after_the_migration() -> None:
    assert exit_route(position()) == "curve"
    assert exit_route(position(migrated=True)) == "pumpswap"
