# pyright: reportPrivateUsage=false
"""T4.16 — the fast lane (``fast_lane.py``) over the live capture of 12/09
(``test_chain.py``'s ``FakeChain``): only the young mints with a known
creation time are read, through the same persistence path as the minute loop
(``solana_rpc`` snapshots stamped with the slot's block time), a failed read
is counted and does not stop the radar, the heartbeat carries the fast-lane
fields, and the sources' rolling counters forget what left the minute."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from hunter_meme_worker import fast_lane
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext
from hunter_meme_worker.fast_lane import fast_once, young_mints
from hunter_meme_worker.sources import SOLANA_RPC, SourcesState
from hunter_meme_worker.tracker import MintTracker, TrackedMint

from .test_chain import (  # pyright: ignore[reportPrivateUsage]
    BLOCK_TIME,
    RECEIVED,
    FakeChain,
    _accounts,
    _context,
    _kinds,
    _patch,
)

pytestmark = pytest.mark.unit

NOW = RECEIVED + timedelta(seconds=30)


def _tracked(mint: str, *, age_s: int | None, **kw: Any) -> TrackedMint:
    created = None if age_s is None else NOW - timedelta(seconds=age_s)
    return TrackedMint(
        mint=mint, first_seen_at=NOW - timedelta(minutes=10), created_at=created, **kw
    )


def test_only_young_mints_with_a_known_birth_are_read_by_the_fast_lane() -> None:
    tracker = MintTracker(window_minutes=1440, cap=200)
    for t in (
        _tracked("young", age_s=120),
        _tracked("newborn", age_s=0),
        _tracked("old", age_s=300),
        _tracked("older", age_s=900),
        _tracked("unknown_age", age_s=None),
        _tracked("usdc", age_s=60, quote_unsupported=True),
        _tracked("done", age_s=60, complete=True),
        _tracked("future", age_s=-5),
    ):
        tracker.observe(t)
    assert [t.mint for t in young_mints(tracker, NOW, max_age_s=300)] == ["newborn", "young"]
    assert [t.mint for t in young_mints(tracker, NOW, max_age_s=600)] == [
        "newborn",
        "young",
        "old",
    ]


async def test_the_fast_lane_reads_the_young_subset_through_the_same_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch)
    monkeypatch.setattr("hunter_meme_worker.fast_lane.utcnow", lambda: NOW)
    kinds = _kinds()
    mints, _ = _accounts()
    young = kinds["midlife"][:5]
    old = [m for m in mints if m not in young][:20]
    log: list[Any] = []
    chain = FakeChain()
    tracked = [
        dataclasses.replace(_tracked(m, age_s=90 + i), first_seen_at=NOW)
        for i, m in enumerate(young)
    ]
    tracked += [_tracked(m, age_s=1200) for m in old]
    ctx = _context(chain, log, tracked=tracked)
    ctx = dataclasses.replace(ctx, config=MemeConfig(fast_lane_max_age_s=300))
    folded: list[tuple[list[str], datetime]] = []

    async def fake_fold(
        ctx_: RadarContext, tracked_: list[TrackedMint], *, as_of: datetime
    ) -> list[Any]:
        folded.append(([t.mint for t in tracked_], as_of))
        return [object()] * len(tracked_)

    monkeypatch.setattr(fast_lane, "fold_fast", fake_fold)
    report = await fast_once(ctx)
    assert chain.calls == [young], "the young subset only, newest first, one batch"
    assert (report.mints, report.read, report.rows, report.failed) == (5, 5, 5, False)
    assert report.calls == 2, "one getMultipleAccounts and one getBlockTime for five mints"
    snapshots = [p for s, p in log if s.startswith("INSERT INTO meme_curve_snapshots")]
    assert len(snapshots) == 5 and all(
        p["source"] == "solana_rpc" and p["observed_at"] == BLOCK_TIME for p in snapshots
    ), "the fast lane's photo is the chain loop's photo: slot time, finality, same row"
    assert folded == [(young, NOW)], "one row per young mint, folded at the tick"
    for mint in young:
        current = ctx.tracker.get(mint)
        assert current is not None and current.last_polled_at == BLOCK_TIME
        assert current.last_rest_polled_at is None, "a chain read is not an identity read"
    assert ctx.sources is not None
    fields = ctx.sources.heartbeat_fields(NOW, tracked=len(tracked))
    assert fields["fast_lane_mints"] == "5" and fields["fast_lane_reads_60s"] == "5"
    assert fields["fast_lane_calls_60s"] == "2" and fields["fast_lane_cycle_s"] != ""
    assert ctx.sources[SOLANA_RPC].used_60s.total(NOW) == 2, "two calls, counted once each"
    later = ctx.sources.heartbeat_fields(NOW + timedelta(seconds=61), tracked=25)
    assert later["fast_lane_reads_60s"] == "0" and later["fast_lane_mints"] == "5"


async def test_a_failed_read_is_counted_and_the_lane_stays_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch)
    monkeypatch.setattr("hunter_meme_worker.fast_lane.utcnow", lambda: NOW)
    kinds = _kinds()
    log: list[Any] = []
    tracked = [_tracked(m, age_s=60) for m in kinds["midlife"][:3]]
    ctx = _context(FakeChain(fail=RuntimeError("rpc down")), log, tracked=tracked)
    report = await fast_once(ctx)
    assert report.failed and report.read == 0 and report.rows == 0 and log == []
    assert ctx.sources is not None and ctx.sources[SOLANA_RPC].last_error == "RuntimeError"
    assert ctx.sources.heartbeat_fields(NOW, tracked=3)["fast_lane_mints"] == "", (
        "a read that failed reports no subset; the minute loop still covers"
    )
    empty = _context(FakeChain(), [], tracked=[_tracked("old", age_s=3600)])
    report = await fast_once(empty)
    assert (report.mints, report.calls, report.rows) == (0, 0, 0)
    assert empty.sources is not None
    assert empty.sources.heartbeat_fields(NOW, tracked=1)["fast_lane_mints"] == "0"


def test_the_sources_state_records_the_fast_cycle_as_rolling_counters() -> None:
    sources = SourcesState()
    at = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)
    sources.record_fast_cycle(at, mints=7, read=6, calls=2, duration_s=0.41)
    sources.record_fast_cycle(at + timedelta(seconds=15), mints=8, read=8, calls=2, duration_s=0.39)
    fields = sources.heartbeat_fields(at + timedelta(seconds=20), tracked=100)
    assert (fields["fast_lane_mints"], fields["fast_lane_cycle_s"]) == ("8", "0.39")
    assert (fields["fast_lane_reads_60s"], fields["fast_lane_calls_60s"]) == ("14", "4")
    assert (
        sources.heartbeat_fields(at + timedelta(seconds=70), tracked=100)["fast_lane_reads_60s"]
        == "8"
    )
