"""T4.2e against a real Postgres at ``head`` (``0025``) — one file, one
container, run alone (``timeout 590``).

What only a database can prove: the ``mayhem_state`` denominator lands through
the real upsert and the widened CHECK, once, and a later ``observed_virgin``
does not move it; a Mayhem minute folds with its progress **stored negative**
(the site clamps, this radar does not) and the fold's coverage bookkeeping
counts it; a tape pulled before the minute's close gives the minute a tape and
a stale one does not — and the heartbeat's two coverage numbers are exactly
the rows' own.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.features import DENOMINATOR_UNKNOWN, NO_TRADE_FEED, CurveObservation
from hunter_meme_worker.fold import fold_minute
from hunter_meme_worker.graduation import MAYHEM_STATE, OBSERVED_VIRGIN
from hunter_meme_worker.repo import TokenRow, load_tracked, upsert_token
from hunter_meme_worker.repo_tape import TradeRow, insert_trades
from hunter_meme_worker.sources import SourcesState
from hunter_meme_worker.tracker import MintTracker, TrackedMint
from hunter_meme_worker.trades import TapeCoverage, TradesPuller

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
T0 = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
MINUTE = T0 + timedelta(minutes=1)
MAYHEM = "T42E_MAYHEM"
STANDARD = "T42E_STANDARD"
_DENOMINATOR = text(
    "SELECT initial_real_token_reserves, progress_denominator_source, mayhem_enabled "
    "FROM meme_tokens WHERE mint = :mint"
)
_FEATURES = text(
    "SELECT curve_progress_pct, progress_reason, buys_1m, tape_reason FROM meme_features_1m "
    "WHERE mint = :mint AND end_time = :end_time AND features_version = :version"
)


def _token(mint: str, **kw: object) -> TokenRow:
    defaults: dict[str, object] = {
        "mint": mint,
        "first_seen_source": "pumpfun_rest",
        "first_seen_at": T0,
        "last_seen_at": T0,
        "created_at": T0,
        "creator": "CREATOR",
    }
    defaults.update(kw)
    return TokenRow(**defaults)  # type: ignore[arg-type]


async def _denominator(factory: async_sessionmaker[AsyncSession], mint: str) -> dict[str, Any]:
    async with role_session(factory, db_role=WORKER) as session:
        return dict((await session.execute(_DENOMINATOR, {"mint": mint})).mappings().one())


class _NoSource:
    async def get_trades(self, mint: str, *, limit: int = 100, cursor: str | None = None) -> Any:
        raise AssertionError("the fold never pulls")


async def test_the_mayhem_denominator_lands_once_through_the_widened_check(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(session, _token(MAYHEM, mayhem_enabled=True, mayhem_state="paused"))
        await upsert_token(
            session,
            _token(
                MAYHEM,
                first_seen_source="solana_rpc",
                initial_real_token_reserves=Decimal("793100000"),
                progress_denominator_source=MAYHEM_STATE,
                mayhem_enabled=True,
            ),
        )
        await upsert_token(
            session,
            _token(
                MAYHEM,
                initial_real_token_reserves=Decimal("822644036.902123"),
                progress_denominator_source=OBSERVED_VIRGIN,
            ),
        )
    row = await _denominator(db_session_factory, MAYHEM)
    assert row["initial_real_token_reserves"] == Decimal("793100000")
    assert row["progress_denominator_source"] == MAYHEM_STATE
    assert row["mayhem_enabled"] is True
    async with role_session(db_session_factory, db_role=WORKER) as session:
        tracked = {
            t.mint: t for t in await load_tracked(session, cutoff=T0 - timedelta(hours=1), cap=50)
        }
    assert tracked[MAYHEM].initial_real_token_reserves == Decimal("793100000")
    assert tracked[MAYHEM].mayhem_state == "paused", "a restart still knows the coin is Mayhem"


async def test_a_mayhem_minute_folds_with_its_negative_progress_and_the_coverage_is_counted(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``2sduGq…`` by its numbers, folded: 1 − 822 644 036,902123 / 793 100 000 =
    −0,037251, stored — and the fold reports 1 of 2 rows with a progress."""
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(session, _token(STANDARD))
    tracker = MintTracker(window_minutes=1440, cap=50)
    tracker.observe(
        TrackedMint(
            mint=MAYHEM,
            first_seen_at=T0,
            created_at=T0,
            creator="CREATOR",
            mayhem_state="paused",
            initial_real_token_reserves=Decimal("793100000"),
        )
    )
    tracker.observe(TrackedMint(mint=STANDARD, first_seen_at=T0, created_at=T0))
    state = RadarState()
    state.last_folded_minute = T0
    state.observe(
        MAYHEM,
        CurveObservation(
            observed_at=T0 + timedelta(seconds=30),
            source="solana_rpc",
            real_token_reserves=Decimal("822644036.902123"),
            mcap_sol=Decimal("2.79599331167002"),
            complete=False,
        ),
    )
    sources = SourcesState()
    puller = TradesPuller(_NoSource(), budget_60s=900, cycle_s=10, stale_s=180)
    ctx = RadarContext(
        config=MemeConfig(),
        session_factory=db_session_factory,
        tracker=tracker,
        state=state,
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
        sources=sources,
        trades=puller,
    )
    rows = await fold_minute(ctx, MINUTE)
    assert len(rows) == 2
    async with role_session(db_session_factory, db_role=WORKER) as session:
        mayhem = dict(
            (
                await session.execute(
                    _FEATURES,
                    {"mint": MAYHEM, "end_time": MINUTE, "version": ctx.config.features_version},
                )
            )
            .mappings()
            .one()
        )
        standard = dict(
            (
                await session.execute(
                    _FEATURES,
                    {"mint": STANDARD, "end_time": MINUTE, "version": ctx.config.features_version},
                )
            )
            .mappings()
            .one()
        )
    assert mayhem["curve_progress_pct"] == Decimal("-0.037251")
    assert mayhem["progress_reason"] is None
    assert mayhem["tape_reason"] == NO_TRADE_FEED and mayhem["buys_1m"] is None
    assert standard["progress_reason"] is not None, "no photo: no progress, with a reason"
    assert standard["progress_reason"] != DENOMINATOR_UNKNOWN
    assert sources.fold_minute == MINUTE and sources.fold_rows == 2
    assert sources.fold_rows_with_progress == 1 and sources.fold_rows_with_tape == 0
    fields = sources.heartbeat_fields(MINUTE, tracked=2)
    assert fields["progress_coverage_pct"] == "50.0" and fields["tape_coverage_pct"] == "0.0"


async def test_a_tape_pulled_before_the_close_covers_the_minute_and_a_stale_one_does_not(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    later = MINUTE + timedelta(minutes=1)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_trades(
            session,
            [
                TradeRow(
                    block_time=MINUTE - timedelta(seconds=20),
                    signature="T42E_SIG_1",
                    event_index=0,
                    mint=MAYHEM,
                    slot=446421000,
                    received_at=MINUTE - timedelta(seconds=15),
                    trader="BUYER",
                    side="buy",
                    sol_lamports=250_000_000,
                    token_amount=Decimal("1000000"),
                    price=Decimal("0.00000025"),
                )
            ],
        )
    tracker = MintTracker(window_minutes=1440, cap=50)
    tracker.observe(
        TrackedMint(
            mint=MAYHEM,
            first_seen_at=T0,
            created_at=T0,
            creator="CREATOR",
            mayhem_state="paused",
            initial_real_token_reserves=Decimal("793100000"),
        )
    )
    puller = TradesPuller(_NoSource(), budget_60s=900, cycle_s=10, stale_s=180)
    coverage = TapeCoverage(covered_since=MINUTE - timedelta(seconds=30), last_pull_at=MINUTE)
    coverage.ok_times.append(MINUTE - timedelta(seconds=15))
    puller.coverage[MAYHEM] = coverage
    sources = SourcesState()
    state = RadarState()
    state.last_folded_minute = T0
    ctx = RadarContext(
        config=MemeConfig(),
        session_factory=db_session_factory,
        tracker=tracker,
        state=state,
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
        sources=sources,
        trades=puller,
    )
    # A second minute (``MINUTE``) — the fold of this test — sees the pull.
    rows = await fold_minute(ctx, MINUTE)
    assert len(rows) == 1 and rows[0].buys_1m == 1 and rows[0].tape_reason is None
    assert rows[0].curve_volume_1m_sol == Decimal("0.25")
    assert sources.heartbeat_fields(MINUTE, tracked=1)["tape_coverage_pct"] == "100.0"
    # Four minutes later with no successful pull since: the tape is stale.
    stale = MINUTE + timedelta(minutes=4)
    rows = await fold_minute(ctx, stale)
    assert len(rows) == 1 and rows[0].buys_1m is None and rows[0].tape_reason == NO_TRADE_FEED
    assert sources.heartbeat_fields(stale, tracked=1)["tape_coverage_pct"] == "0.0"
    assert later < stale
