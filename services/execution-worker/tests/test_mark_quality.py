"""T3.29 item 4 — ``mark_quality``: the number ``mtm_fresh`` never measured.

Astra's review of 2026-09-08 (§2, row "MTM") named the scenario exactly: a
market whose tape stopped keeps its **last durable mark**
(``hunter_core.portfolio.marking``), the cycle keeps writing curve points and
renewing ``mtm_written_at``, so ``health.mtm_fresh`` stays green while the
equity it reports is an estimate. ``mtm_fresh`` measures the *write*;
``mark_quality`` measures the *prices*.

Everything here is arithmetic over one dataclass and one payload, so it needs no
Docker and no clock.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

from hunter_execution_worker.bridge_inputs import MarkCoverage
from hunter_execution_worker.config import HEARTBEAT_KEY, ExecutionConfig
from hunter_execution_worker.heartbeat import write_heartbeat
from hunter_execution_worker.state import CycleHealth


def _coverage(marked: int, positions: int) -> MarkCoverage:
    return MarkCoverage(
        marks={uuid.uuid4(): Decimal(100) for _ in range(marked)}, open_positions=positions
    )


class TestQualityIsAShareOfPositionsNotOfWrites:
    """**O que refuta:** a quality that reports ``1`` while a position is priced
    at the last durable mark; a quality that reports ``0`` for a wallet that
    holds nothing and turns the normal state into a permanent alarm."""

    def test_every_position_marked_live_is_one(self) -> None:
        assert _coverage(3, 3).quality == Decimal(1)
        assert _coverage(3, 3).complete is True

    def test_one_stale_mark_out_of_two_is_a_half_and_not_complete(self) -> None:
        coverage = _coverage(1, 2)
        assert coverage.quality == Decimal("0.5")
        assert coverage.complete is False

    def test_a_stopped_tape_over_the_whole_wallet_is_zero(self) -> None:
        coverage = _coverage(0, 2)
        assert coverage.quality == Decimal(0)
        assert coverage.complete is False

    def test_an_empty_wallet_is_complete_by_construction(self) -> None:
        coverage = _coverage(0, 0)
        assert coverage.quality == Decimal(1)
        assert coverage.complete is True

    def test_the_share_is_decimal_never_float(self) -> None:
        # 1/3 as a float is 0.3333333333333333; the heartbeat publishes this
        # number as a string and money-adjacent numbers never become floats.
        assert isinstance(_coverage(1, 3).quality, Decimal)


class TestHealthTakesBothNumbersFromOnePass:
    """**O que refuta:** a numerator from one pass and a denominator from
    another — a wallet that shows 2 of 1 positions marked."""

    def test_record_marks_moves_both_together(self) -> None:
        health = CycleHealth()
        health.record_marks(_coverage(2, 4))
        assert (health.marked_positions, health.open_positions) == (2, 4)
        assert health.mark_quality() == Decimal("0.5")
        health.record_marks(_coverage(1, 1))
        assert (health.marked_positions, health.open_positions) == (1, 1)
        assert health.mark_quality() == Decimal(1)

    def test_a_fresh_process_reports_a_complete_empty_wallet(self) -> None:
        assert CycleHealth().mark_quality() == Decimal(1)


class _Redis:
    """A **labelled double** for the heartbeat's two Redis calls."""

    def __init__(self) -> None:
        self.written: dict[str, str] = {}
        self.ttl: int | None = None

    async def hset(self, key: str, *, mapping: dict[str, str]) -> None:
        assert key == HEARTBEAT_KEY
        self.written = mapping

    async def expire(self, key: str, ttl: int) -> None:
        self.ttl = ttl


class _Runtime:
    def __init__(self, redis: _Redis) -> None:
        self.redis = redis
        self.instance = "test:1"


class TestTheOperatorSeesTheQualityNextToTheWrite:
    """``hb:execution:paper`` is what the shift report and ``/ever/system``
    read. "No fills today" is legitimate; "the wallet is marked at yesterday's
    prices" is not, and only one of the two fields can say so.

    **O que refuta:** a heartbeat that publishes ``last_mtm`` and leaves an
    operator to infer the mark quality from an equity that does not move."""

    async def test_the_heartbeat_publishes_mark_quality_and_the_two_counts(self) -> None:
        redis = _Redis()
        health = CycleHealth()
        health.record_marks(_coverage(1, 2))
        await write_heartbeat(cast("Any", _Runtime(redis)), health, ExecutionConfig())
        assert redis.written["mark_quality"] == "0.5"
        assert redis.written["marked_positions"] == "1"
        assert redis.written["open_positions"] == "2"

    async def test_an_empty_wallet_publishes_one_not_an_alarm(self) -> None:
        redis = _Redis()
        await write_heartbeat(cast("Any", _Runtime(redis)), CycleHealth(), ExecutionConfig())
        assert redis.written["mark_quality"] == "1"
        assert redis.written["open_positions"] == "0"
