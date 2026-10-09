"""Copy-trade pilot (H-037): open/close bookkeeping of coverage gaps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_exchanges.pumpfun.leader_events import LeaderGap
from hunter_exchanges.pumpfun.leader_source_gaps import GapTracker

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


def test_the_first_loss_opens_a_gap_and_a_repeat_is_silent() -> None:
    gaps = GapTracker()
    assert gaps.open("nats_disconnect", T0) == LeaderGap(None, T0, None, "nats_disconnect")
    assert gaps.open("nats_disconnect", T0 + timedelta(seconds=1)) is None
    assert gaps.is_open()


def test_closing_emits_each_gap_with_its_original_start_and_clears() -> None:
    gaps = GapTracker()
    gaps.open("nats_disconnect", T0)
    gaps.open("nats_auth", T0 + timedelta(seconds=2))
    gaps.open("nats_subscription_refused", T0 + timedelta(seconds=3), wallet="W1")
    end = T0 + timedelta(seconds=10)
    closed = gaps.close_all(end)
    assert closed == [
        LeaderGap(None, T0, end, "nats_disconnect"),
        LeaderGap(None, T0 + timedelta(seconds=2), end, "nats_auth"),
        LeaderGap("W1", T0 + timedelta(seconds=3), end, "nats_subscription_refused"),
    ]
    assert not gaps.is_open()


def test_the_same_reason_for_two_wallets_is_two_gaps() -> None:
    gaps = GapTracker()
    assert gaps.open("r", T0, wallet="A") is not None
    assert gaps.open("r", T0, wallet="B") is not None
    assert gaps.open("r", T0, wallet="A") is None


def test_one_gap_can_be_closed_alone_and_only_once() -> None:
    gaps = GapTracker()
    gaps.open("nats_unseeded", T0, wallet="A")
    gaps.open("nats_unseeded", T0, wallet="B")
    end = T0 + timedelta(seconds=1)
    assert gaps.close("nats_unseeded", end, wallet="A") == LeaderGap("A", T0, end, "nats_unseeded")
    assert gaps.close("nats_unseeded", end, wallet="A") is None
    assert gaps.is_open()  # B is still unseeded
