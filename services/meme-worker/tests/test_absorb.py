"""``hunter_meme_worker.absorb`` (T4.79, EXP-M22): the per-mint absorption
state machine — a sell ≥ 5 % of the pre-sell real reserve is seen; the price
back at the pre-sell level within 30 s starts the hold; 10 s held confirms;
a late recovery never confirms; a second large sell before the confirmation
restarts the episode and one after it ends the mint's episode; a coverage gap
makes everything unknown — and the two gate criteria refuse by name."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_meme_worker.absorb import (
    CONFIRMATION_EXPIRED,
    COVERAGE_GAP,
    HOLDING,
    NO_LARGE_SELL,
    RECOVERING,
    RECOVERY_LATE,
    SECOND_SELL_AFTER_CONFIRM,
    AbsorbFeatures,
    AbsorbTracker,
    AbsorbTrade,
)
from hunter_meme_worker.absorb_rules import (
    REFUSAL_ABSORB_NOT_CONFIRMED,
    REFUSAL_ABSORB_SELL_NOT_SEEN,
    REFUSAL_ABSORB_UNKNOWN,
    absorb_refusals,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
V_SOL = Decimal("40")
V_TOK = Decimal("800000000")
REAL = Decimal("10")
"""A curve at 40 virtual SOL / 800 M virtual tokens (price 5e-8) with 10 real SOL."""


def _at(s: float) -> datetime:
    return T0 + timedelta(seconds=s)


def _trade(
    s: float,
    side: str,
    sol: str,
    *,
    v_sol: str | Decimal = V_SOL,
    v_tok: str | Decimal = V_TOK,
    real: str | Decimal = REAL,
    tokens: str | None = "1000",
) -> AbsorbTrade:
    """Post-trade reserves are given explicitly: the pre-sell level of a sell is
    derived from the event itself (``v_sol + sol``, ``v_tok − tokens``)."""
    return AbsorbTrade(
        block_time=_at(s),
        received_at=_at(s) + timedelta(milliseconds=500),
        side=side,
        sol=Decimal(sol),
        tokens=None if tokens is None else Decimal(tokens),
        virtual_sol=Decimal(v_sol),
        virtual_token=Decimal(v_tok),
        real_sol=Decimal(real),
    )


def _large_sell(s: float) -> AbsorbTrade:
    """1 SOL out of a curve that held 10 real SOL before it: 1 / (9 + 1) = 10 %.
    Pre-sell price = (39 + 1) / (820 M − 20 M) = 40 / 800 M = 5e-8."""
    return _trade(s, "sell", "1", v_sol="39", v_tok="820000000", real="9", tokens="20000000")


def _buy_back_to(s: float, v_sol: str, v_tok: str) -> AbsorbTrade:
    return _trade(s, "buy", "0.5", v_sol=v_sol, v_tok=v_tok, real="9.5")


AT_LEVEL = ("40", "800000000")
"""Exactly the pre-sell price: 40 / 800 M."""
ABOVE = ("41", "790000000")
BELOW = ("39.5", "810000000")


def _confirmed(f: AbsorbFeatures) -> tuple[bool | None, bool | None, str | None]:
    return f.sell_seen, f.confirmed, f.reason


# -- the state machine -------------------------------------------------------


def test_no_large_sell_means_both_false_by_name() -> None:
    tracker = AbsorbTracker()
    tracker.push(_trade(1, "sell", "0.4", v_sol="39.6", v_tok="808000000", real="9.6"))  # 4 %
    f = tracker.features(_at(2))
    assert _confirmed(f) == (False, False, NO_LARGE_SELL)
    assert f.sells_seen == 0 and f.sell_at is None


def test_sell_seen_then_recovery_then_hold_confirms() -> None:
    tracker = AbsorbTracker()
    tracker.push(_large_sell(0))
    f = tracker.features(_at(1))
    assert _confirmed(f) == (True, False, RECOVERING)
    assert f.sell_at == _at(0) and f.sell_share == Decimal("0.100000")
    tracker.push(_buy_back_to(12, *AT_LEVEL))  # back at the level, 12 s after the sell
    f = tracker.features(_at(15))
    assert _confirmed(f) == (True, False, HOLDING)
    assert f.recovered_at == _at(12)
    f = tracker.features(_at(22))  # 10 s held (silence is not a price move)
    assert _confirmed(f) == (True, True, None)
    assert f.confirmed_at == _at(22)
    f = tracker.features(_at(35))
    assert _confirmed(f) == (False, True, None), (
        "the control's window closes at 30 s; the signal lives"
    )
    f = tracker.features(_at(83))
    assert _confirmed(f) == (False, False, CONFIRMATION_EXPIRED), (
        "the signal is an instant, not a state"
    )


def test_a_late_recovery_never_confirms() -> None:
    tracker = AbsorbTracker()
    tracker.push(_large_sell(0))
    tracker.push(_buy_back_to(31, *ABOVE))
    f = tracker.features(_at(45))
    assert _confirmed(f) == (False, False, RECOVERY_LATE)
    assert f.recovered_at is None


def test_the_hold_broken_before_ten_seconds_can_recover_again_inside_the_window() -> None:
    tracker = AbsorbTracker()
    tracker.push(_large_sell(0))
    tracker.push(_buy_back_to(5, *AT_LEVEL))
    tracker.push(_trade(9, "sell", "0.1", v_sol=BELOW[0], v_tok=BELOW[1], real="9.4"))  # dips
    assert _confirmed(tracker.features(_at(16))) == (True, False, RECOVERING)
    tracker.push(_buy_back_to(20, *ABOVE))
    assert _confirmed(tracker.features(_at(29))) == (True, False, HOLDING)
    assert _confirmed(tracker.features(_at(30))) == (True, True, None)


def test_a_dip_after_the_hold_completed_does_not_unconfirm() -> None:
    tracker = AbsorbTracker()
    tracker.push(_large_sell(0))
    tracker.push(_buy_back_to(5, *AT_LEVEL))
    tracker.push(_trade(16, "sell", "0.1", v_sol=BELOW[0], v_tok=BELOW[1], real="9.4"))
    assert _confirmed(tracker.features(_at(17))) == (True, True, None)


def test_a_second_large_sell_before_confirmation_restarts_the_episode() -> None:
    tracker = AbsorbTracker()
    tracker.push(_large_sell(0))
    tracker.push(_buy_back_to(5, *AT_LEVEL))
    # A second 10 % sell at 8 s: the first was not absorbed — the reference moves.
    second = _trade(8, "sell", "1", v_sol="38", v_tok="840000000", real="8.5", tokens="40000000")
    tracker.push(second)
    f = tracker.features(_at(9))
    assert _confirmed(f) == (True, False, RECOVERING)
    assert f.sell_at == _at(0), "the control's anchor stays the first sell"
    assert f.reference_sell_at == _at(8) and f.sells_seen == 2
    assert f.recovered_at is None
    # Back to the SECOND sell's pre-level (39 / 800 M) but not the first's: recovers.
    tracker.push(_buy_back_to(20, "39", "800000000"))
    assert _confirmed(tracker.features(_at(30))) == (True, True, None)
    assert tracker.features(_at(30)).confirmed_at == _at(30)


def test_a_large_sell_after_confirmation_ends_the_mint_episode() -> None:
    tracker = AbsorbTracker()
    tracker.push(_large_sell(0))
    tracker.push(_buy_back_to(5, *AT_LEVEL))
    assert _confirmed(tracker.features(_at(15))) == (True, True, None)
    tracker.push(_large_sell(16))
    f = tracker.features(_at(17))
    assert _confirmed(f) == (True, False, SECOND_SELL_AFTER_CONFIRM)
    tracker.push(_buy_back_to(20, *ABOVE))
    assert _confirmed(tracker.features(_at(40))) == (False, False, SECOND_SELL_AFTER_CONFIRM), (
        "one confirmed episode per mint: nothing after it confirms again"
    )


def test_a_coverage_gap_makes_everything_unknown() -> None:
    tracker = AbsorbTracker()
    tracker.push(_large_sell(0))
    tracker.mark_gap(_at(3))
    f = tracker.features(_at(4))
    assert _confirmed(f) == (None, None, COVERAGE_GAP)
    tracker.push(_buy_back_to(5, *AT_LEVEL))
    assert _confirmed(tracker.features(_at(20))) == (None, None, COVERAGE_GAP)


def test_a_sell_received_after_as_of_is_not_seen_yet() -> None:
    tracker = AbsorbTracker()
    tracker.push(_large_sell(0))  # received at +0.5 s
    assert _confirmed(tracker.features(_at(0.2))) == (False, False, NO_LARGE_SELL)


def test_a_drained_curve_and_a_sell_without_tokens_are_not_a_reference() -> None:
    tracker = AbsorbTracker()
    tracker.push(_trade(1, "buy", "1", v_sol="41", v_tok="780000000", real="11"))
    # tokens unknown: the pre-sell price falls back to the last post-trade price (41 / 780 M).
    tracker.push(_trade(2, "sell", "2", v_sol="39", v_tok="820000000", real="9", tokens=None))
    f = tracker.features(_at(3))
    assert _confirmed(f) == (True, False, RECOVERING)
    tracker.push(_trade(4, "buy", "0", v_sol="0", v_tok="0", real="0"))  # a drained photo: ignored
    tracker.push(_buy_back_to(6, "41", "780000000"))
    assert _confirmed(tracker.features(_at(16))) == (True, True, None)


# -- the gate criteria -------------------------------------------------------


def _features(**overrides: object) -> AbsorbFeatures:
    base: dict[str, object] = {
        "sell_seen": False,
        "confirmed": False,
        "sell_at": None,
        "reference_sell_at": None,
        "sell_share": None,
        "recovered_at": None,
        "confirmed_at": None,
        "sells_seen": 0,
        "reason": NO_LARGE_SELL,
    }
    base.update(overrides)
    return AbsorbFeatures(**base)  # type: ignore[arg-type]


def test_a_set_that_asks_nothing_gets_no_refusal_even_without_readings() -> None:
    assert absorb_refusals(None, require_confirmed=False, require_sell_seen=False) == ()


def test_unknown_refuses_by_name_on_either_criterion() -> None:
    for confirmed, sell_seen in ((True, False), (False, True), (True, True)):
        assert absorb_refusals(None, require_confirmed=confirmed, require_sell_seen=sell_seen) == (
            REFUSAL_ABSORB_UNKNOWN,
        ), "the 15-second lane carries no absorb reading: fail closed"
        gapped = _features(sell_seen=None, confirmed=None, reason=COVERAGE_GAP)
        assert absorb_refusals(
            gapped, require_confirmed=confirmed, require_sell_seen=sell_seen
        ) == (REFUSAL_ABSORB_UNKNOWN,)


def test_the_treatment_refuses_until_confirmed_and_the_control_until_the_sell() -> None:
    nothing = _features()
    assert absorb_refusals(nothing, require_confirmed=True, require_sell_seen=False) == (
        REFUSAL_ABSORB_NOT_CONFIRMED,
    )
    assert absorb_refusals(nothing, require_confirmed=False, require_sell_seen=True) == (
        REFUSAL_ABSORB_SELL_NOT_SEEN,
    )
    seen = _features(sell_seen=True, reason=RECOVERING)
    assert absorb_refusals(seen, require_confirmed=False, require_sell_seen=True) == ()
    assert absorb_refusals(seen, require_confirmed=True, require_sell_seen=False) == (
        REFUSAL_ABSORB_NOT_CONFIRMED,
    )
    confirmed = _features(sell_seen=False, confirmed=True, reason=None)
    assert absorb_refusals(confirmed, require_confirmed=True, require_sell_seen=False) == ()
    assert absorb_refusals(confirmed, require_confirmed=True, require_sell_seen=True) == (
        REFUSAL_ABSORB_SELL_NOT_SEEN,
    )
