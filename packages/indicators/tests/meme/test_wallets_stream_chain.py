"""Wave 1c-bis on the REAL wave-1a chain fixtures: bounded engine == batch, night by night.

The fills come from real ``getTransaction`` logs (``t1a_tape.py``: the adapter's own log reader,
then :func:`~hunter_indicators.meme.wallets.bridge.fill_from_swap`) — the 8 WSOL-quoted PumpSwap
transactions (9 pool swaps, signed virtual quote, LP fee, cashback, v1) and the v1 pump.fun curve
buy. Their block times are the chain's (05/10/2026); the reader stamps ``received_at`` at
06/10 00:00 UTC, so every one arrives after its day ended and all of them are late across midnight
— the path the carry exists for. The comparison runs over a sliding 2-day window until the fills
have left it, the last nights seeing them only through the carry.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_indicators.meme.wallets.bridge import fill_from_swap
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.tape import Fill
from packages.indicators.tests.meme.stream_harness import (
    World,
    reference_snapshot,
    streamed_snapshots,
)
from packages.indicators.tests.meme.t1a_tape import (
    V1_PUMP_BUY,
    WSOL_QUOTED,
    chain_pool_mints,
    records,
    tx,
)

pytestmark = pytest.mark.unit

PARAMS = RankingParams(window_days=2, min_episodes=1, min_mints=1, min_active_days=1,
                       min_e_pnl_lamports=-(10**12), min_positive_days=0)  # fmt: skip


def _chain_fills() -> list[Fill]:
    out: list[Fill] = []
    for name in WSOL_QUOTED:
        t = tx(name)
        for record in records(t):
            fill = fill_from_swap(record, pool=chain_pool_mints(t, record.pool or ""))
            assert isinstance(fill, Fill), fill
            out.append(fill)
    (curve_record,) = records(tx(V1_PUMP_BUY, "pumpfun"))
    curve_fill = fill_from_swap(curve_record, curve_complete=False)
    assert isinstance(curve_fill, Fill), curve_fill
    return [*out, curve_fill]


def test_the_real_fixtures_give_the_same_snapshot_every_night() -> None:
    fills = _chain_fills()
    assert len(fills) == 10 and {f.venue for f in fills} == {"pool", "curve"}
    first = min(f.block_time for f in fills)
    origin = datetime(first.year, first.month, first.day, tzinfo=UTC)
    assert all(f.received_at.date() > f.block_time.date() for f in fills)  # late across midnight
    world = World(origin=origin, fills=tuple(fills))
    days = [(origin + timedelta(days=k)).date() for k in range(2, 6)]
    streamed = streamed_snapshots(world, days, params=PARAMS, roundtrip=True)
    for day, snap in zip(days, streamed, strict=True):
        assert snap == reference_snapshot(world, day, params=PARAMS), day
    assert streamed[0].manifest["window_fills"] == "10"
    assert (
        streamed[-1].manifest["window_fills"] == "0"
    )  # the last night sees them only via the carry
    assert len(streamed[0].rows) == len({f.wallet for f in fills})
