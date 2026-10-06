"""Differential proof of wave 1c-bis on random multi-day campaigns (fixtures, not data).

Night by night from the campaign origin, the bounded engine — which never sees an event received
before the window start except through the carry — must publish **exactly** the batch snapshot,
on every day after the first window, with and without a serialize/restore of the carry between
nights (restart). A census proves the generator keeps exercising the paths that break naive
incremental engines.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from hunter_indicators.meme.wallets.params import RankingParams
from packages.indicators.tests.meme.stream_harness import reference_snapshot, streamed_snapshots
from packages.indicators.tests.meme.stream_world import Census, random_world
from packages.indicators.tests.meme.test_wallets_builders import T0

pytestmark = pytest.mark.unit

SEEDS = range(24)


def _days(window: int, total: int) -> list[date]:
    first = (T0 + timedelta(days=window)).date()
    return [first + timedelta(days=k) for k in range(total - window + 1)]


@pytest.mark.parametrize("seed", SEEDS)
def test_every_night_equals_the_batch_snapshot(seed: int) -> None:
    params = RankingParams(window_days=2, min_episodes=2, min_mints=1, min_active_days=1,
                           min_e_pnl_lamports=0, min_positive_days=1, top_n=2)  # fmt: skip
    world, _ = random_world(seed, window_days=2, days=6)
    days = _days(2, 6)
    streamed = streamed_snapshots(world, days, params=params, roundtrip=seed % 2 == 0)
    for day, snap in zip(days, streamed, strict=True):
        assert snap == reference_snapshot(world, day, params=params), day


@pytest.mark.parametrize("seed", range(3))
def test_the_seven_day_window_equals_the_batch_snapshot(seed: int) -> None:
    world, _ = random_world(100 + seed, window_days=7, days=10)
    days = _days(7, 10)
    streamed = streamed_snapshots(world, days, roundtrip=True)
    for day, snap in zip(days, streamed, strict=True):
        assert snap == reference_snapshot(world, day), day


def test_the_generator_exercises_every_hard_path() -> None:
    params = RankingParams(window_days=2)
    total = Census()
    copies = merged = incomplete = contaminated = unmatched = 0
    for seed in SEEDS:
        world, census = random_world(seed, window_days=2, days=6)
        for name in total.__slots__:
            setattr(total, name, getattr(total, name) + getattr(census, name))
        for day in _days(2, 6):
            snap = reference_snapshot(world, day, params=params)
            merged += any(e.startswith("e:") for e in snap.rows)
            for row in snap.rows.values():
                m = row.metrics
                assert m is not None
                copies += m.copies
                incomplete += m.incomplete_episodes
                contaminated += m.contaminated_episodes
                unmatched += m.unmatched_share > 0
    assert min(getattr(total, n) for n in total.__slots__) > 0, total
    assert min(copies, merged, incomplete, contaminated, unmatched) > 0
