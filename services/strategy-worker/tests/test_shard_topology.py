"""``consumer_group``/``heartbeat_key`` (T3.74f) -- the per-shard names."""

from __future__ import annotations

import pytest

from hunter_strategy_worker.config import CONSUMER_GROUP, HEARTBEAT_KEY
from hunter_strategy_worker.shard import (
    consumer_group,
    consumer_groups,
    heartbeat_key,
    heartbeat_keys,
)

pytestmark = pytest.mark.unit


def test_solo_shard_keeps_the_classic_names_byte_for_byte() -> None:
    assert consumer_group(0, 1) == CONSUMER_GROUP
    assert heartbeat_key(0, 1) == HEARTBEAT_KEY


def test_sharded_names_embed_index_and_total() -> None:
    assert consumer_group(1, 4) == f"{CONSUMER_GROUP}.1of4"
    assert heartbeat_key(1, 4) == f"{HEARTBEAT_KEY}:1of4"


def test_every_shard_of_a_topology_gets_a_distinct_name() -> None:
    total = 4
    groups = {consumer_group(i, total) for i in range(total)}
    hbs = {heartbeat_key(i, total) for i in range(total)}
    assert len(groups) == total
    assert len(hbs) == total


class TestTopologySets:
    """``consumer_groups``/``heartbeat_keys`` (T3.87) -- the whole topology at
    once, derived from the same per-shard functions above so the replay gate
    never rederives the naming formula."""

    def test_solo_topology_is_the_classic_single_name(self) -> None:
        assert consumer_groups(1) == (CONSUMER_GROUP,)
        assert heartbeat_keys(1) == (HEARTBEAT_KEY,)

    def test_four_shards_matches_the_per_shard_function_one_for_one(self) -> None:
        total = 4
        assert consumer_groups(total) == tuple(consumer_group(i, total) for i in range(total))
        assert heartbeat_keys(total) == tuple(heartbeat_key(i, total) for i in range(total))

    def test_zero_or_negative_is_clamped_to_one_shard(self) -> None:
        assert consumer_groups(0) == (CONSUMER_GROUP,)
        assert heartbeat_keys(-1) == (HEARTBEAT_KEY,)
