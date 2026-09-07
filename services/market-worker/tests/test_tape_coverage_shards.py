"""T2.5g — one coverage hash, N collectors, and no borrowed proof.

The scanner reads a single ``mkt:{exchange}:coverage`` per exchange and this
task does not get to change that reader. With four shards, a plain ``HSET`` of
``covered_until`` is last-writer-wins: the healthy shard's fresh cut would be
applied to the symbols of a stuck one. These tests pin the conservative
aggregate (``coverage_publish``) that replaces it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from hunter_core.redis import keys
from hunter_market_worker.coverage import COVERAGE_SAFETY_S, CoverageTracker
from hunter_market_worker.coverage_publish import SHARD_RECORD_TTL_S, shards_key

pytestmark = pytest.mark.integration


def _at(second: float) -> datetime:
    return datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=second)


async def _hash(redis: Any, exchange: str = "binance") -> dict[str, str]:
    raw = await redis.hgetall(keys.tape_coverage(exchange))
    return {k.decode(): v.decode() for k, v in raw.items()}


def _shard(index: int, total: int = 2) -> CoverageTracker:
    return CoverageTracker("binance", index, total)


async def test_each_shard_publishes_its_own_symbols_and_the_cut_is_the_most_behind_one(
    redis_client: Any,
) -> None:
    first, second = _shard(0), _shard(1)
    first.session_started(["BTCUSDT"], at=_at(0))
    second.session_started(["ETHUSDT"], at=_at(0))

    await first.stamp(redis_client, dropped_events=0, now=_at(10))
    await second.stamp(redis_client, dropped_events=0, now=_at(8))

    published = await _hash(redis_client)
    assert published["sym:BTCUSDT"] == _at(0).isoformat()
    assert published["sym:ETHUSDT"] == _at(0).isoformat()
    # The slowest shard bounds the exchange: 8s - the 0.5s margin, never 10s.
    assert published["covered_until"] == (_at(8) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()
    assert published["session_since"] == _at(0).isoformat()


async def test_a_frozen_shard_holds_the_whole_exchange_back_instead_of_being_overwritten(
    redis_client: Any,
) -> None:
    """The failure this exists to prevent: shard 1 is stuck (queue backlog), so
    its ``covered_until`` freezes -- and shard 0, publishing every 250 ms with a
    fresh cut, must not hand the scanner a proof that covers shard 1's markets
    through the freeze."""
    first, second = _shard(0), _shard(1)
    first.session_started(["BTCUSDT"], at=_at(0))
    second.session_started(["ETHUSDT"], at=_at(0))
    await second.stamp(redis_client, dropped_events=0, now=_at(1))
    # shard 1 goes backlogged: its cut freezes at 1s - margin
    await second.stamp(
        redis_client,
        dropped_events=0,
        now=_at(2),
        queue_progress=(10, 0, 0),
        oldest_pending_ts=_at(0),
    )
    frozen = (await _hash(redis_client))["covered_until"]

    await first.stamp(redis_client, dropped_events=0, now=_at(3))

    assert (await _hash(redis_client))["covered_until"] == frozen
    assert frozen == (_at(1) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()


async def test_a_shard_that_stops_stamping_loses_its_symbols_rather_than_borrowing_a_proof(
    redis_client: Any,
) -> None:
    first, second = _shard(0), _shard(1)
    first.session_started(["BTCUSDT"], at=_at(0))
    second.session_started(["ETHUSDT"], at=_at(0))
    await first.stamp(redis_client, dropped_events=0, now=_at(1))
    await second.stamp(redis_client, dropped_events=0, now=_at(1))
    assert "sym:ETHUSDT" in await _hash(redis_client)

    # shard 1 dies; shard 0 keeps stamping past the record TTL
    await first.stamp(redis_client, dropped_events=0, now=_at(2 + SHARD_RECORD_TTL_S))

    published = await _hash(redis_client)
    assert "sym:ETHUSDT" not in published, "a dead shard's markets must stop claiming coverage"
    assert "sym:BTCUSDT" in published
    assert (
        published["covered_until"]
        == (_at(2 + SHARD_RECORD_TTL_S) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()
    )
    records = await redis_client.hgetall(shards_key("binance"))
    assert not any(key.decode().startswith("1of2") for key in records)


async def test_a_restarted_shard_reconciles_symbols_it_has_no_memory_of(
    redis_client: Any,
) -> None:
    """A new process starts with an empty published set, so reconciliation can
    only come from what is stored next to the hash -- otherwise a market that
    left the universe across a restart keeps a coverage field nobody collects."""
    before = _shard(0)
    before.session_started(["BTCUSDT", "ETHUSDT"], at=_at(0))
    await before.stamp(redis_client, dropped_events=0, now=_at(1))

    after = _shard(0)  # same shard id, brand new process
    after.session_started(["BTCUSDT"], at=_at(2))
    await after.stamp(redis_client, dropped_events=0, now=_at(3))

    published = await _hash(redis_client)
    assert "sym:ETHUSDT" not in published
    assert published["sym:BTCUSDT"] == _at(2).isoformat()


async def test_a_broken_session_withdraws_only_that_shards_symbols(redis_client: Any) -> None:
    first, second = _shard(0), _shard(1)
    first.session_started(["BTCUSDT"], at=_at(0))
    second.session_started(["ETHUSDT"], at=_at(0))
    await first.stamp(redis_client, dropped_events=0, now=_at(1))
    await second.stamp(redis_client, dropped_events=0, now=_at(1))

    second.session_broken()
    await second.stamp(redis_client, dropped_events=0, now=_at(2))

    published = await _hash(redis_client)
    assert "sym:ETHUSDT" not in published
    assert published["sym:BTCUSDT"] == _at(0).isoformat()
    assert published["session_since"] == _at(0).isoformat()
    assert published["covered_until"] == (_at(1) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()


async def test_the_last_shard_leaving_says_so_instead_of_deleting_the_key(
    redis_client: Any,
) -> None:
    solo = CoverageTracker("binance")
    solo.session_started(["BTCUSDT"], at=_at(0))
    await solo.stamp(redis_client, dropped_events=0, now=_at(1))

    solo.session_broken()
    await solo.stamp(redis_client, dropped_events=0, now=_at(2))

    published = await _hash(redis_client)
    assert published["session_since"] == ""
    assert published["covered_until"] == ""
    assert "sym:BTCUSDT" not in published


async def test_a_symbol_no_live_shard_claims_is_removed_whoever_left_it_there(
    redis_client: Any,
) -> None:
    """Found in production, not in review: after an 8 -> 4 topology change on the
    local stack, ``mkt:binance:coverage`` kept 201 ``sym:`` fields for 200
    monitored markets — ``KOMAUSDT`` belonged to no live shard and nothing was
    ever going to delete it, so the scanner would have claimed coverage for a
    market nobody collects. The invariant is now absolute: after any stamp, the
    ``sym:`` fields are exactly the union of the live records' own lists."""
    shard = _shard(0, 1)
    shard.session_started(["BTCUSDT"], at=_at(0))
    await shard.stamp(redis_client, dropped_events=0, now=_at(1))
    await redis_client.hset(keys.tape_coverage("binance"), "sym:ORPHANUSDT", _at(0).isoformat())

    await shard.stamp(redis_client, dropped_events=0, now=_at(2))

    published = await _hash(redis_client)
    assert "sym:ORPHANUSDT" not in published
    assert "sym:BTCUSDT" in published


async def test_during_a_handover_the_later_start_wins(redis_client: Any) -> None:
    """Astra, T2.5g diff review: while a topology change is rolling, two shards
    claim the same symbol for a few seconds. If the old owner's older ``since``
    won, the reader would accept a window crossing the handover — seconds in
    which the old owner was already frozen and the new one had not connected."""
    old = CoverageTracker("binance", 0, 2)
    old.session_started(["BTCUSDT"], at=_at(0))
    await old.stamp(redis_client, dropped_events=0, now=_at(10))

    new = CoverageTracker("binance", 0, 4)
    new.session_started(["BTCUSDT"], at=_at(10.5))
    await new.stamp(redis_client, dropped_events=0, now=_at(11))
    # the old owner stamps once more before noticing it lost the symbol
    await old.stamp(redis_client, dropped_events=0, now=_at(11.5))

    assert (await _hash(redis_client))["sym:BTCUSDT"] == _at(10.5).isoformat()


async def test_a_topology_change_never_deletes_a_symbol_its_new_owner_claims(
    redis_client: Any,
) -> None:
    """``0of2`` is replaced by ``0of4``; the old record ages out and is purged,
    but ``BTCUSDT`` moved to the new shard and its field must survive."""
    old = CoverageTracker("binance", 0, 2)
    old.session_started(["BTCUSDT"], at=_at(0))
    await old.stamp(redis_client, dropped_events=0, now=_at(1))

    new = CoverageTracker("binance", 0, 4)
    new.session_started(["BTCUSDT"], at=_at(2))
    await new.stamp(redis_client, dropped_events=0, now=_at(2 + SHARD_RECORD_TTL_S))

    published = await _hash(redis_client)
    assert published["sym:BTCUSDT"] == _at(2).isoformat()
    records = await redis_client.hgetall(shards_key("binance"))
    assert not any(key.decode().startswith("0of2") for key in records)
