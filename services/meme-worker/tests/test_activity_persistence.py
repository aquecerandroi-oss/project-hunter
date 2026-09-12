"""T4.2g against a real Postgres at ``head`` (``0032``) — one file, one
container, run alone (``timeout 590``).

What only a database can prove: the batch's rows land through the real
``INSERT`` under the schema's CHECKs (a number with its quote, a stated zero
with ``empty = true``, the same instant twice is one row, a dark window is no
row); the minute folds with ``tape_source = activity_1m`` and the window's
end as ``tape_as_of`` when the per-mint tape did not cover, and with
``swap_api_trades`` (creator columns real) when it did; a reading that
reached us after the close is not the minute's tape, and a later reading does
not hide the one that had arrived; the 15-second row carries the same
provenance; and the heartbeat says how much of the tape came from the batch.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.market_activity import ActivityBatch, parse_activity_batch
from hunter_exchanges.pumpfun.models import NormalizedSolPrice
from hunter_meme_worker.activity import ActivityPuller
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.fast_lane import fold_fast
from hunter_meme_worker.features import NO_TRADE_FEED
from hunter_meme_worker.features_tape import ACTIVITY_1M, SWAP_API_TRADES
from hunter_meme_worker.fold import fold_minute
from hunter_meme_worker.repo_tape import TradeRow, insert_trades
from hunter_meme_worker.sources import SourcesState
from hunter_meme_worker.tape_budget import TapeCoverage
from hunter_meme_worker.tracker import MintTracker, TrackedMint
from hunter_meme_worker.trades import TradesPuller

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
MINUTE = datetime(2026, 9, 12, 20, 25, tzinfo=UTC)
NOW = MINUTE - timedelta(seconds=3)
STAMP = MINUTE - timedelta(seconds=4)
LATE = MINUTE + timedelta(seconds=5)
T0 = MINUTE - timedelta(minutes=4)
MINTS = {"batch": "T42G_A", "tape": "T42G_B", "both": "T42G_C", "late": "T42G_D"}
LIVE: dict[str, Any] = {
    "numTxs": 7,
    "volumeUSD": Decimal("140"),
    "numUsers": 5,
    "numBuys": 5,
    "numSells": 2,
    "buyVolumeUSD": Decimal("100"),
    "sellVolumeUSD": Decimal("40"),
    "numBuyers": 4,
    "numSellers": 2,
    "priceChangePercent": Decimal("9.5"),
}
_ACTIVITY = text(
    "SELECT mint, window_name, empty, buys, sells, unique_buyers, buy_volume_usd, sol_usd, "
    "buy_volume_sol, sell_volume_sol, end_time, received_at FROM meme_market_activity_1m "
    "WHERE mint = ANY(:mints) ORDER BY mint, window_name, end_time"
)
_FEATURES = text(
    "SELECT mint, buys_1m, sells_1m, unique_buyers, net_sol_flow_1m, tape_reason, tape_source, "
    "tape_window_s, tape_as_of, creator_net_seller, creator_net_seller_reason "
    "FROM meme_features_1m WHERE mint = ANY(:mints) AND end_time = :end_time "
    "AND features_version = :version"
)
_FAST = text(
    "SELECT mint, buys_60s, tape_reason, tape_source, tape_window_s, tape_as_of, "
    "creator_net_seller_reason FROM meme_features_15s "
    "WHERE mint = ANY(:mints) AND as_of = :as_of AND features_version = :version"
)


class FakeSwapApi:
    """The batch route: ``LIVE`` for the coins in ``live``, ``null`` for the rest;
    stamped with the instant the test says the response came at."""

    def __init__(self, *, live: set[str]) -> None:
        self.live = live
        self.observed_at = STAMP
        self.received_at = NOW
        self.calls = 0

    async def market_activity_batch(
        self, mints: Any, *, windows: Any = ("1m", "5m")
    ) -> ActivityBatch:
        self.calls += 1
        raw = {
            m: {w: (dict(LIVE) if m in self.live and w == "1m" else None) for w in windows}
            for m in mints
        }
        return parse_activity_batch(
            raw,
            mints=mints,
            windows=windows,
            observed_at=self.observed_at,
            received_at=self.received_at,
        )

    async def get_trades(self, mint: str, *, limit: int = 100, cursor: str | None = None) -> Any:
        raise AssertionError("the fold reads the tape from the database, never pulls")


class FakeQuotes:
    async def get_sol_price(self) -> NormalizedSolPrice:
        return NormalizedSolPrice(
            price_usd=Decimal("200"),
            as_of=NOW - timedelta(seconds=30),
            stale=False,
            observed_at=NOW - timedelta(seconds=20),
            received_at=NOW - timedelta(seconds=20),
        )


async def _rows(
    factory: async_sessionmaker[AsyncSession], statement: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    async with role_session(factory, db_role=WORKER) as session:
        return [dict(r) for r in (await session.execute(statement, params)).mappings()]


def _context(factory: Any, trades: TradesPuller, activity: ActivityPuller) -> RadarContext:
    tracker = MintTracker(window_minutes=1440, cap=50)
    for mint in MINTS.values():
        tracker.observe(
            TrackedMint(mint=mint, first_seen_at=T0, created_at=T0, creator=f"CREATOR_{mint}")
        )
    return RadarContext(
        config=MemeConfig(),
        session_factory=factory,
        tracker=tracker,
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
        sources=SourcesState(),
        trades=trades,
        activity=activity,
    )


async def test_the_batch_feeds_both_series_with_its_provenance_and_never_before_it_arrived(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = FakeSwapApi(live={MINTS["batch"], MINTS["both"]})
    trades = TradesPuller(client, budget_60s=16, cycle_s=10.0)
    # The per-mint tape covers ``tape`` only: one creator sell inside the minute, received before the close.
    trades.coverage[MINTS["tape"]] = TapeCoverage(
        covered_since=T0, ok_times=deque([MINUTE - timedelta(seconds=25)], maxlen=8)
    )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_trades(
            session,
            [
                TradeRow(
                    block_time=MINUTE - timedelta(seconds=30),
                    signature="T42G_SIG_B_1",
                    event_index=0,
                    mint=MINTS["tape"],
                    slot=446_500_000,
                    received_at=MINUTE - timedelta(seconds=25),
                    trader=f"CREATOR_{MINTS['tape']}",
                    side="sell",
                    sol_lamports=1_000_000_000,
                    token_amount=Decimal("1000000"),
                    price=Decimal("0.000001"),
                )
            ],
        )
    activity = ActivityPuller(
        client, budget=trades.budget, quotes=FakeQuotes(), sources=SourcesState()
    )
    ctx = _context(db_session_factory, trades, activity)
    asked = [MINTS["batch"], MINTS["tape"], MINTS["both"]]
    report = await activity.pull_once(db_session_factory, asked, now=NOW)
    assert report.calls == 1 and report.live == {"1m": 2} and report.covered == 3
    assert report.rows == 3, "two numbers and one stated zero for 1m; 5m is dark — no row"
    again = await activity.pull_once(db_session_factory, asked, now=NOW)
    assert again.rows == 3
    rows = await _rows(db_session_factory, _ACTIVITY, {"mints": list(MINTS.values())})
    assert [(r["mint"], r["window_name"]) for r in rows] == [(m, "1m") for m in sorted(asked)], (
        "the same instant twice is one row; the dark 5m window wrote nothing"
    )
    by_mint = {r["mint"]: r for r in rows}
    live = by_mint[MINTS["batch"]]
    assert (live["buys"], live["sells"], live["unique_buyers"], live["empty"]) == (5, 2, 4, False)
    assert live["sol_usd"] == Decimal("200") and live["buy_volume_sol"] == Decimal("0.5")
    assert live["sell_volume_sol"] == Decimal("0.2") and live["end_time"] == STAMP
    assert live["received_at"] == NOW
    zero = by_mint[MINTS["tape"]]
    assert zero["empty"] is True and zero["buys"] == 0 and zero["buy_volume_sol"] == 0
    # A second response after the close: ``both`` again (must not hide its first reading)
    # and ``late`` for the first time (must not be the minute's tape).
    client.observed_at, client.received_at = LATE - timedelta(seconds=1), LATE
    client.live = {MINTS["both"], MINTS["late"]}
    late = await activity.pull_once(db_session_factory, [MINTS["both"], MINTS["late"]], now=LATE)
    assert late.rows == 2
    ctx.state.last_folded_minute = MINUTE - timedelta(minutes=1)
    folded = await fold_minute(ctx, MINUTE)
    assert len(folded) == 4
    features = {
        r["mint"]: r
        for r in await _rows(
            db_session_factory,
            _FEATURES,
            {
                "mints": list(MINTS.values()),
                "end_time": MINUTE,
                "version": ctx.config.features_version,
            },
        )
    }
    from_batch = features[MINTS["batch"]]
    assert (from_batch["tape_source"], from_batch["tape_window_s"]) == (ACTIVITY_1M, 60)
    assert from_batch["tape_as_of"] == STAMP and from_batch["tape_reason"] is None
    assert (from_batch["buys_1m"], from_batch["sells_1m"], from_batch["unique_buyers"]) == (5, 2, 4)
    assert from_batch["net_sol_flow_1m"] == Decimal("0.3"), "(100 − 40) USD at 200 USD/SOL"
    assert from_batch["creator_net_seller"] is None
    assert from_batch["creator_net_seller_reason"] == NO_TRADE_FEED, "the batch never says who"
    from_tape = features[MINTS["tape"]]
    assert (from_tape["tape_source"], from_tape["tape_as_of"]) == (SWAP_API_TRADES, MINUTE)
    assert from_tape["sells_1m"] == 1 and from_tape["creator_net_seller"] is True, (
        "the per-mint tape wins over the batch's stated zero, and knows the creator"
    )
    both = features[MINTS["both"]]
    assert both["tape_source"] == ACTIVITY_1M and both["tape_as_of"] == STAMP, (
        "the reading received before the close, not the one received after it"
    )
    late_row = features[MINTS["late"]]
    assert late_row["tape_source"] is None and late_row["buys_1m"] is None
    assert late_row["tape_reason"] == NO_TRADE_FEED, "its only reading came after the close"
    assert ctx.sources is not None
    fields = ctx.sources.heartbeat_fields(MINUTE, tracked=4)
    assert fields["tape_coverage_pct"] == "75.0" and fields["tape_activity_pct"] == "50.0"
    # The 15-second row at the close carries the same provenance.
    tracked = [t for t in ctx.tracker.snapshot() if t.mint == MINTS["batch"]]
    fast = await fold_fast(ctx, tracked, as_of=MINUTE)
    assert len(fast) == 1
    fast_rows = await _rows(
        db_session_factory,
        _FAST,
        {"mints": [MINTS["batch"]], "as_of": MINUTE, "version": ctx.config.features_15s_version},
    )
    assert fast_rows[0]["tape_source"] == ACTIVITY_1M and fast_rows[0]["tape_as_of"] == STAMP
    assert fast_rows[0]["buys_60s"] == 5 and fast_rows[0]["tape_reason"] is None
    assert fast_rows[0]["creator_net_seller_reason"] == NO_TRADE_FEED
