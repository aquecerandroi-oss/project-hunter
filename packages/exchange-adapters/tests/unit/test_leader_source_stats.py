"""Copy-trade pilot (H-037): the latency distributions the leader source publishes."""

from __future__ import annotations

import pytest

from hunter_exchanges.pumpfun.leader_source_stats import LatencyDist, LeaderSourceStats

pytestmark = pytest.mark.unit


def test_an_empty_distribution_says_so_instead_of_inventing_numbers() -> None:
    assert LatencyDist().summary() == {"n": 0}


def test_percentiles_are_nearest_rank_in_milliseconds() -> None:
    dist = LatencyDist()
    for ms in range(1, 101):
        dist.record(ms / 1000)
    s = dist.summary()
    assert s["n"] == 100
    assert (s["p50_ms"], s["p90_ms"], s["p99_ms"], s["max_ms"]) == (50.0, 90.0, 99.0, 100.0)


def test_the_window_is_bounded_but_the_count_is_not() -> None:
    dist = LatencyDist(window=10)
    for i in range(25):
        dist.record(i / 1000)
    s = dist.summary()
    assert s["n"] == 25 and s["window"] == 10 and s["min_ms"] == 15.0


def test_negative_latencies_are_clamped_not_dropped() -> None:
    dist = LatencyDist()
    dist.record(-0.5)
    assert dist.summary()["p50_ms"] == 0.0


def test_source_stats_snapshot_is_plain_data() -> None:
    stats = LeaderSourceStats()
    stats.receive_to_emit.record(0.002)
    stats.nats_to_confirm.record(0.4)
    stats.count("frames")
    stats.count("frames")
    snap = stats.snapshot()
    assert snap["counters"] == {"frames": 2}
    assert snap["receive_to_emit"]["n"] == 1 and snap["nats_to_confirm"]["p50_ms"] == 400.0
