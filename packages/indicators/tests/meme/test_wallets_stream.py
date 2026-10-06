"""The bounded engine (wave 1c-bis) equals the batch snapshot on the existing fixtures.

Same fixtures as ``test_wallets_ranking`` / ``test_wallets_leakage`` (synthetic, not data): the
snapshot of :func:`~hunter_indicators.meme.wallets.stream.stream_snapshot` must be **equal** —
every row, metric, manifest key and the entity version — to
:func:`~hunter_indicators.meme.wallets.ranking.build_snapshot`'s.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from hunter_indicators.meme.wallets.entities import Link
from hunter_indicators.meme.wallets.leakage import fingerprint
from hunter_indicators.meme.wallets.lots import Lot
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from packages.indicators.tests.meme.stream_harness import (
    World,
    reference_snapshot,
    streamed_snapshots,
)
from packages.indicators.tests.meme.test_wallets_builders import SOL, T0, TOKEN, fill
from packages.indicators.tests.meme.test_wallets_leakage import (  # the leak fixtures
    _base,  # pyright: ignore[reportPrivateUsage]
    _future,  # pyright: ignore[reportPrivateUsage]
)
from packages.indicators.tests.meme.test_wallets_ranking import DAY, S_EXIT_V, S_EXIT_W, week

pytestmark = pytest.mark.unit


def _ranking_world() -> World:
    w, cw = week("W", S_EXIT_W)
    v, cv = week("V", S_EXIT_V)
    return World(origin=T0, fills=(*w, *v), creates=(*cw, *cv))


def test_the_streamed_snapshot_equals_the_batch_on_the_ranking_week() -> None:
    world = _ranking_world()
    reference = reference_snapshot(world, DAY)
    [streamed] = streamed_snapshots(world, [DAY])
    assert reference.rows["W"].rank == 1  # the fixture still says what it said
    assert streamed == reference


def test_twins_preserved_lots_and_top_n_stay_equal() -> None:
    fills, creates = week("T1", S_EXIT_W, seller="T2")
    legacy = Lot("T2", "LEGACY", 10 * TOKEN, None, -1_000, T0 - timedelta(hours=2))
    sale = fill(wallet="T1", side="sell", slot=50_000, sol=SOL, atoms=10 * TOKEN, mint="LEGACY")
    world = World(origin=T0, fills=(*fills, sale), creates=tuple(creates),
                  links=(Link("T1", "T2", "strong", T0, "F"),), preserved=(legacy,))  # fmt: skip
    for params in (RankingParams(), RankingParams(top_n=1, min_h2_entities=1)):
        assert streamed_snapshots(world, [DAY], params=params) == [
            reference_snapshot(world, DAY, params=params)
        ]


def test_the_future_never_reaches_the_streamed_snapshot() -> None:
    base = _base()
    future = _future(base)  # trades, links, creates and funders at/after the cut
    world = World(origin=T0, fills=future.fills, creates=future.creates, links=future.links,
                  funders=future.funders)  # fmt: skip
    plain = World(origin=T0, fills=base.fills, creates=base.creates)
    [streamed] = streamed_snapshots(world, [DAY])
    assert streamed == reference_snapshot(world, DAY)
    assert fingerprint(streamed) == fingerprint(streamed_snapshots(plain, [DAY])[0])
    assert replace(streamed, entities=streamed.entities) == streamed


def test_the_daily_cap_and_excluded_bets_that_consume_it_stay_equal() -> None:
    # W's first qualifying buy in 3 mints a day; the cap keeps the first ones per (entity, day) in
    # decision order. W00 was created by W's funder: not a forward refusal (``own_mint`` only reads
    # the entity's wallets) but a historical exclusion — its bet is admitted, consumes the cap, and
    # is not copied (admission before the exclusion, Astra). Expected: min(cap, 3) × 7 − 1.
    fills, creates = week("W", S_EXIT_W)
    creates = [c if c.mint != "W00" else replace(c, creator="FUND") for c in creates]
    world = World(origin=T0, fills=tuple(fills), creates=tuple(creates),
                  funders={"W": ("FUND", T0)})  # fmt: skip
    for cap in (1, 2, 20):
        policy = FollowPolicy(max_bets_per_entity_day=cap)
        [streamed] = streamed_snapshots(world, [DAY], policy=policy)
        reference = reference_snapshot(world, DAY, policy=policy)
        assert streamed == reference
        metrics = reference.rows["W"].metrics
        assert metrics is not None
        assert metrics.copies + metrics.copies_incomplete == min(cap, 3) * 7 - 1


def test_a_night_with_an_empty_window_keeps_the_carried_horizon() -> None:
    w, cw = week("W", S_EXIT_W)
    early = tuple(f for f in w if f.block_time < T0 + timedelta(days=1))
    world = World(origin=T0, fills=early, creates=tuple(cw))
    params = RankingParams(window_days=2)
    days = [(T0 + timedelta(days=k)).date() for k in (2, 3, 4)]
    streamed = streamed_snapshots(world, days, params=params, roundtrip=True)
    for day, snap in zip(days, streamed, strict=True):
        reference = reference_snapshot(world, day, params=params)
        assert snap == reference
    assert streamed[-1].manifest["window_fills"] == "0"
    assert streamed[-1].manifest["horizon_slot"] == str(max(f.slot for f in early))
