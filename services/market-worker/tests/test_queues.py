"""D2: the bounded loss-reporting queue must never raise, even when full —
losing the *report* of a loss must never be worse than the loss itself."""

from __future__ import annotations

from typing import Any, cast

import pytest

from hunter_core.observability import market_persistence_loss_reports_dropped_total
from hunter_market_worker.queues import PersistQueues

from . import builders

pytestmark = pytest.mark.unit


def test_drop_never_raises_and_evicts_oldest_when_the_loss_deque_is_full() -> None:
    queues = PersistQueues(max_items=4)
    metric = cast(Any, market_persistence_loss_reports_dropped_total)
    before = metric._value.get()

    for i in range(5):
        queues.drop(builders.liquidation("BTCUSDT", qty=str(i + 1)), "capacity")

    assert len(queues.losses) == 4
    assert metric._value.get() == before + 1


def test_losses_deque_keeps_the_most_recent_items_after_eviction() -> None:
    queues = PersistQueues(max_items=2)
    first = builders.liquidation("BTCUSDT", qty="1")
    second = builders.liquidation("BTCUSDT", qty="2")
    third = builders.liquidation("BTCUSDT", qty="3")

    queues.drop(first, "capacity")
    queues.drop(second, "capacity")
    queues.drop(third, "capacity")

    remaining = [loss.item for loss in queues.losses]
    assert remaining == [second, third]
