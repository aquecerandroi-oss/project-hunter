"""``Throttle`` coalesces per-channel updates to the configured interval."""

from __future__ import annotations

import pytest

from hunter_api.realtime.throttle import DEFAULT_INTERVALS_MS, Throttle

pytestmark = pytest.mark.unit


def test_emits_once_then_coalesces_within_the_interval() -> None:
    throttle = Throttle({"prices": 250})

    assert throttle.should_emit("prices", now=0.0) is True
    assert throttle.should_emit("prices", now=0.1) is False
    assert throttle.should_emit("prices", now=0.24) is False


def test_emits_again_once_the_interval_elapses() -> None:
    throttle = Throttle({"prices": 250})

    assert throttle.should_emit("prices", now=0.0) is True
    assert throttle.should_emit("prices", now=0.25) is True


def test_channels_are_independent() -> None:
    throttle = Throttle(DEFAULT_INTERVALS_MS)

    assert throttle.should_emit("prices", now=0.0) is True
    assert throttle.should_emit("radar", now=0.0) is True
    assert throttle.should_emit("prices", now=0.1) is False
    assert throttle.should_emit("radar", now=0.1) is False


def test_risk_channel_has_zero_interval_and_never_coalesces() -> None:
    throttle = Throttle(DEFAULT_INTERVALS_MS)

    assert throttle.should_emit("risk", now=0.0) is True
    assert throttle.should_emit("risk", now=0.0001) is True


def test_unknown_channel_uses_default_interval() -> None:
    throttle = Throttle({}, default_ms=500)

    assert throttle.should_emit("unknown", now=0.0) is True
    assert throttle.should_emit("unknown", now=0.1) is False
    assert throttle.should_emit("unknown", now=0.5) is True
