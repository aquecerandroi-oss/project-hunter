"""``consumer_group``/``heartbeat_key`` (T3.74f) -- the per-shard names."""

from __future__ import annotations

import pytest

from hunter_strategy_worker.config import CONSUMER_GROUP, HEARTBEAT_KEY
from hunter_strategy_worker.shard import consumer_group, heartbeat_key

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
