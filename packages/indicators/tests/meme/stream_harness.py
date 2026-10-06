"""Test harness of wave 1c-bis: the batch reference and the night-by-night streaming driver.

**Reference** = the untouched :func:`~hunter_indicators.meme.wallets.ranking.build_snapshot` over
the whole tape, with the opening lots it leaves to its caller defined as the per-wallet FIFO of
every event mined before the window start (``block_time < S``), in
:func:`~hunter_indicators.meme.wallets.carry.lot_order`, on top of the preserved lots.

**Streamed** = :func:`~hunter_indicators.meme.wallets.stream.stream_snapshot` once per night from
the campaign origin, each night seeing per mint only its carry and the events received from the
window start on (future ones included, to prove they are ignored). ``roundtrip=True`` serializes
and restores the carry between nights (restart).

A test tool, not production: it groups the whole tape per mint every night.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import MappingProxyType

from hunter_indicators.meme.wallets.carry import (
    MintCarry,
    canonical_order,
    initial_carry,
    sort_lots,
)
from hunter_indicators.meme.wallets.carry_codec import carry_from_json, carry_to_json
from hunter_indicators.meme.wallets.entities import Link
from hunter_indicators.meme.wallets.lots import Lot, fifo
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from hunter_indicators.meme.wallets.ranking import RankInputs, build_snapshot, cut_of
from hunter_indicators.meme.wallets.snapshot import Snapshot
from hunter_indicators.meme.wallets.stream import (
    MintWindow,
    StreamInputs,
    shared_signatures,
    stream_snapshot,
)
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Gap, dedupe


def _no_funders() -> Mapping[str, tuple[str, datetime]]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class World:
    """Everything a campaign ever sees (future included); ``origin`` = first window start."""

    origin: datetime
    fills: tuple[Fill, ...]
    creates: tuple[CreateEvent, ...] = ()
    links: tuple[Link, ...] = ()
    funders: Mapping[str, tuple[str, datetime]] = field(default_factory=_no_funders)
    preserved: tuple[Lot, ...] = ()
    gaps: tuple[Gap, ...] = ()


def _canonical(fills: Iterable[Fill]) -> tuple[Fill, ...]:
    return tuple(sorted(fills, key=canonical_order))


def reference_snapshot(
    world: World,
    day: date,
    *,
    policy: FollowPolicy | None = None,
    params: RankingParams | None = None,
) -> Snapshot:
    par = params or RankingParams()
    cut = cut_of(day)
    start = cut - timedelta(days=par.window_days)
    canon = _canonical(world.fills)
    mined_before = [f for f in dedupe(canon) if f.block_time < start and f.received_at < cut]
    opening = sort_lots(fifo(mined_before, owner_of=str, opening=world.preserved).open_lots)
    inputs = RankInputs(
        fills=canon,
        creates=tuple(sorted(world.creates, key=lambda c: c.received_at)),
        links=world.links,
        funders=world.funders,
        opening_lots=opening,
        gaps=world.gaps,
    )
    return build_snapshot(inputs, day, policy=policy, params=par)


def mint_windows(world: World, mints: Mapping[str, MintCarry], start: datetime) -> list[MintWindow]:
    fills: dict[str, list[Fill]] = {}
    for f in _canonical(world.fills):
        if f.received_at >= start:
            fills.setdefault(f.mint, []).append(f)
    creates: dict[str, list[CreateEvent]] = {}
    for c in sorted(world.creates, key=lambda c: c.received_at):
        if c.received_at >= start:
            creates.setdefault(c.mint, []).append(c)
    names = sorted({*mints, *fills, *creates})
    return [
        MintWindow(mints.get(m, MintCarry(m)), tuple(fills.get(m, ())), tuple(creates.get(m, ())))
        for m in names
    ]


def streamed_snapshots(
    world: World,
    days: Sequence[date],
    *,
    policy: FollowPolicy | None = None,
    params: RankingParams | None = None,
    roundtrip: bool = False,
) -> list[Snapshot]:
    """One snapshot per consecutive day; the first day's window must start at ``origin``."""
    par = params or RankingParams()
    carry, first = initial_carry(world.origin, world.preserved, window_days=par.window_days)
    mints = {m.mint: m for m in first}
    shared = shared_signatures(world.fills)
    out: list[Snapshot] = []
    for day in days:
        start = cut_of(day) - timedelta(days=par.window_days)
        windows = mint_windows(world, mints, start)
        inputs = StreamInputs(
            carry=carry,
            mints=lambda w=windows: iter(w),
            links=world.links,
            funders=world.funders,
            gaps=world.gaps,
            shared_signatures=shared,
        )
        result = stream_snapshot(inputs, day, policy=policy, params=par)
        out.append(result.snapshot)
        carry, next_mints = result.carry, result.mint_carries
        if roundtrip:
            carry, next_mints = carry_from_json(carry_to_json(carry, next_mints))
        mints = {m.mint: m for m in next_mints}
    return out
