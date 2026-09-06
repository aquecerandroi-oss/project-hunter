"""The eight exit policies of the R1 replay, as declarations and as pure rules.

Nothing here touches a database or a candle series: a policy is a *declaration*
(key, version, parameters, description, inputs) plus the pure predicates the
replay engine evaluates at a bar close. The engine that binds them to the real
walker lives in ``hunter_strategy_worker.replay`` and is tested there.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_indicators.replay.observers import ChannelObserver, ConsecutiveCloseObserver
from hunter_indicators.replay.policies import (
    BASE,
    CONTRASTS,
    FAMILY_SIZE,
    NO_TARGET_FACTOR,
    POLICIES,
    InvalidationRule,
    TargetRule,
    buffered_level,
    check_target_unreachable,
    no_target_level,
    policy,
)

pytestmark = pytest.mark.unit


def test_eight_policies_and_seven_contrasts_declared_up_front() -> None:
    assert len(POLICIES) == 8
    assert set(POLICIES) == {
        "base",
        "INV-B",
        "INV-C",
        "INV-E",
        "TGT-3",
        "TGT-4.5",
        "EXIT-NOTGT",
        "EXIT-CHAN",
    }
    assert len(CONTRASTS) == 7
    assert FAMILY_SIZE == 7


def test_every_policy_is_registered_with_a_full_definition() -> None:
    for key, definition in POLICIES.items():
        assert definition.key == key
        assert definition.version >= 1
        assert definition.description
        assert definition.inputs
        assert isinstance(definition.parameters, Mapping)
        for value in definition.parameters.values():
            assert isinstance(value, str), "parameters are canonical strings, never floats"


def test_contrast_terms_are_declared_policies_and_six_of_seven_face_the_base() -> None:
    against_base = 0
    for contrast in CONTRASTS:
        assert contrast.treatment in POLICIES
        assert contrast.control in POLICIES
        against_base += contrast.control == BASE
    assert against_base == 6
    assert ("EXIT-CHAN", "EXIT-NOTGT") in [(c.treatment, c.control) for c in CONTRASTS]


def test_the_two_families_do_not_collapse_into_one_another() -> None:
    """``INV-B`` drops the invalidation and keeps the target; ``EXIT-NOTGT``
    drops the target and keeps the invalidation (Strategy Backlog, bloco de
    políticas de saída)."""
    assert policy("INV-B").invalidation is InvalidationRule.NONE
    assert policy("INV-B").target is TargetRule.AS_DECIDED
    assert policy("EXIT-NOTGT").invalidation is InvalidationRule.AS_DECIDED
    assert policy("EXIT-NOTGT").target is TargetRule.NONE


def test_channel_arm_keeps_the_original_invalidation() -> None:
    """Astra, design review must-fix 2: ``CHAN − NOTGT`` must isolate the
    channel exit, so the invalidation stays exactly as decided."""
    chan = policy("EXIT-CHAN")
    assert chan.invalidation is InvalidationRule.AS_DECIDED
    assert chan.channel is not None
    assert chan.channel.lookback == 10
    assert chan.channel.timeframe is Timeframe.M15
    assert policy("EXIT-NOTGT").channel is None


def test_buffered_level_subtracts_a_quarter_of_the_frozen_atr() -> None:
    assert buffered_level(Decimal("100"), Decimal("4"), Decimal("0.25")) == Decimal("99")
    assert policy("INV-E").invalidation is InvalidationRule.BUFFERED
    assert policy("INV-E").parameters["buffer_atr"] == "0.25"


def test_no_target_level_is_a_declared_unreachable_sentinel() -> None:
    sentinel = no_target_level(Decimal("2"))
    assert sentinel == Decimal("2") * NO_TARGET_FACTOR
    check_target_unreachable(sentinel, [Decimal("1000"), Decimal("500")])
    with pytest.raises(ValueError, match="sentinel"):
        check_target_unreachable(sentinel, [sentinel])


def _close(minute: int) -> datetime:
    return datetime(2026, 9, 5, 12, 0, tzinfo=UTC).replace(minute=minute % 60)


def test_consecutive_observer_fires_only_on_the_second_aligned_close_below() -> None:
    obs = ConsecutiveCloseObserver(level=Decimal("100"), timeframe=Timeframe.M15, required=2)
    streak, fired = obs.step(0, close_time=_close(15), close=Decimal("99"))
    assert (streak, fired) == (1, False)
    streak, fired = obs.step(streak, close_time=_close(30), close=Decimal("98"))
    assert (streak, fired) == (2, True)


def test_consecutive_observer_resets_on_a_close_at_or_above_the_level() -> None:
    obs = ConsecutiveCloseObserver(level=Decimal("100"), timeframe=Timeframe.M15, required=2)
    streak, _ = obs.step(0, close_time=_close(15), close=Decimal("99"))
    streak, fired = obs.step(streak, close_time=_close(30), close=Decimal("100"))
    assert (streak, fired) == (0, False)
    streak, fired = obs.step(streak, close_time=_close(45), close=Decimal("99"))
    assert (streak, fired) == (1, False)


def test_consecutive_observer_ignores_closes_off_the_frozen_timeframe() -> None:
    obs = ConsecutiveCloseObserver(level=Decimal("100"), timeframe=Timeframe.M15, required=2)
    streak, fired = obs.step(1, close_time=_close(16), close=Decimal("99"))
    assert (streak, fired) == (1, False), "a 1m close is not an observation of a 15m rule"


def test_channel_break_compares_the_close_with_the_previous_closes_only() -> None:
    obs = ChannelObserver(lookback=3)
    previous = [Decimal("101"), Decimal("100"), Decimal("102")]
    assert obs.fired(Decimal("99.9"), previous) is True
    assert obs.fired(Decimal("100"), previous) is False, "strictly below, never equal"


def test_channel_break_is_unavailable_without_the_whole_window() -> None:
    obs = ChannelObserver(lookback=3)
    assert obs.fired(Decimal("1"), [Decimal("101"), Decimal("100")]) is None
