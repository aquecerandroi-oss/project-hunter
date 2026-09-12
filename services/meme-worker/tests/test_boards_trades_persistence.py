"""The T4.2c persistence path against a real Postgres at ``head`` (``0023``) —
one file, one container, run alone (``timeout 590``).

What only a database can prove: the board minute and the risk read route to
their month and dedupe on their keys; a ``swap-api`` trade lands with
``commitment NULL`` and the tape dedupes on ``(block_time, signature,
event_index)``; ``load_tape`` obeys ``received_at <= end_time`` (a trade
received after the close is not in the minute); the real graduated coin of
the live capture writes ``completed_at`` through the real parser (the root
cause of the hour with zero ``complete = true``); a migrated-not-completed mint
comes back from ``load_tracked`` with ``final_read_pending``; the grants hold
as the roles; and ``fold_minute`` writes a features row with the ``0023``
columns filled from a real board entry and a real tape.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun import normalize
from hunter_exchanges.pumpfun.indexer_rest import parse_risk_snapshot
from hunter_exchanges.pumpfun.swap_api import parse_trades_page
from hunter_exchanges.pumpfun.trenches_state import BoardState
from hunter_meme_worker.boards import BoardCollector
from hunter_meme_worker.collect import token_row_from_curve
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.features import CurveObservation
from hunter_meme_worker.fold import fold_minute
from hunter_meme_worker.repo import TokenRow, load_tracked, upsert_token
from hunter_meme_worker.repo_boards import insert_board_minutes, insert_risk_snapshot
from hunter_meme_worker.repo_tape import insert_trades, load_tape, open_bet_mints, trade_rows
from hunter_meme_worker.sources import SourcesState
from hunter_meme_worker.tracker import MintTracker, TrackedMint
from hunter_meme_worker.trades import TapeCoverage, TradesPuller

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
APP = "hunter_app"
FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
CURVE_MINT = "TAPE_MINT"
CREATOR = "dev12bVcv5ZLjo7eYgZcSmZ7KBjEVfnfvorwqdZ14fo"
"""A real trader of ``swap_api_trades_5ejA_raw.json``, used as the creator."""


def _raw(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"), parse_float=Decimal)


def _ingest(received: datetime, board: str = "new") -> BoardCollector:
    """A board capture through a collector, one frame per second from ``received``."""
    capture = _raw(f"trenches_{board}.json")
    state = BoardState(board)
    collector = BoardCollector(MintTracker(window_minutes=1440, cap=500), boards=(board,))
    for index, frame in enumerate(capture["frames"]):
        event = state.apply(
            json.loads(frame["raw"], parse_float=Decimal),
            received_at=received + timedelta(seconds=index),
        )
        collector.ingest(event, session_key=0)
    return collector


def _board_rows(received: datetime) -> tuple[list[Any], BoardCollector]:
    collector = _ingest(received)
    boundary = received.replace(second=0, microsecond=0) + timedelta(minutes=2)
    return collector.close_minute(boundary), collector


async def test_a_board_minute_routes_to_its_month_and_dedupes_on_its_key(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    rows, _ = _board_rows(datetime(2026, 10, 5, 12, 0, 10, tzinfo=UTC))
    assert rows
    async with role_session(db_session_factory, db_role=WORKER) as session:
        assert await insert_board_minutes(session, rows) == len(rows)
        await insert_board_minutes(session, rows)  # the same minute twice writes once
    async with role_session(db_session_factory, db_role=WORKER) as session:
        stored = (
            (
                await session.execute(
                    text(
                        "SELECT count(*) AS n, min(tableoid::regclass::text) AS part, "
                        "count(*) FILTER (WHERE left_board_at IS NOT NULL) AS exits, "
                        "count(*) FILTER (WHERE exposure_censored) AS censored, "
                        "count(*) FILTER (WHERE holders IS NOT NULL) AS with_holders, "
                        "count(*) FILTER (WHERE extra <> '{}'::jsonb) AS with_extra "
                        "FROM meme_board_observations WHERE board = 'new'"
                    )
                )
            )
            .mappings()
            .one()
        )
    assert stored["n"] == len(rows), "a re-insert of the same minute wrote twice"
    assert stored["part"] == "meme_board_observations_2026_09", "observed_at is serverTs, September"
    assert stored["exits"] == 3 and stored["censored"] == 0
    assert stored["with_holders"] == len(rows) and stored["with_extra"] == len(rows)


async def test_the_tape_lands_with_no_finality_claim_and_dedupes(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    received = datetime(2026, 9, 12, 7, 40, tzinfo=UTC)
    page = parse_trades_page(
        CURVE_MINT, _raw("swap_api_trades_5ejA_raw.json"), received_at=received
    )
    rows, skipped = trade_rows(page.trades)
    assert len(rows) == 30 and skipped == {}
    async with role_session(db_session_factory, db_role=WORKER) as session:
        assert await insert_trades(session, rows) == 30
        await insert_trades(session, rows[:10])  # a re-pull offers the same rows again
    async with role_session(db_session_factory, db_role=WORKER) as session:
        stored = (
            (
                await session.execute(
                    text(
                        "SELECT count(*) AS n, min(tableoid::regclass::text) AS part, "
                        "count(*) FILTER (WHERE commitment IS NULL) AS unstated, "
                        "sum(sol_lamports) AS lamports, min(slot) AS slot "
                        "FROM meme_trades WHERE mint = :mint AND source = 'swap_api'"
                    ),
                    {"mint": CURVE_MINT},
                )
            )
            .mappings()
            .one()
        )
    assert stored["n"] == 30 and stored["unstated"] == 30
    assert stored["part"] == "meme_trades_2026_09"
    assert stored["lamports"] == sum(r.sol_lamports for r in rows)
    assert stored["slot"] == 446070380


async def test_load_tape_obeys_received_at_and_joins_the_creator(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The look-ahead case in the database: a trade whose block time is inside
    the minute but which reached us after the close is not in that minute."""
    mint = "LOOKAHEAD_MINT"
    end = datetime(2026, 10, 6, 10, 1, tzinfo=UTC)
    page = parse_trades_page(mint, _raw("swap_api_trades_5ejA_raw.json"), received_at=end)
    rows, _ = trade_rows(page.trades[:3])
    early = [
        _shift(
            r, block_time=end - timedelta(seconds=30 + i), received_at=end - timedelta(seconds=1)
        )
        for i, r in enumerate(rows[:2])
    ]
    late = [
        _shift(
            rows[2], block_time=end - timedelta(seconds=5), received_at=end + timedelta(seconds=1)
        )
    ]
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session,
            TokenRow(
                mint=mint,
                first_seen_source="pumpportal_ws",
                first_seen_at=end,
                last_seen_at=end,
                creator=early[0].trader,
            ),
        )
        await insert_trades(session, early + late)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        tape = await load_tape(session, mints=[mint, "NOBODY"], end_time=end)
    assert len(tape[mint]) == 2, "the trade received after the close leaked into the minute"
    assert all(t.received_at <= end for t in tape[mint])
    assert any(t.trader == early[0].trader for t in tape[mint]), "the creator join found the row"
    assert tape["NOBODY"] == []


def _shift(row: Any, *, block_time: datetime, received_at: datetime) -> Any:
    import dataclasses

    return dataclasses.replace(row, block_time=block_time, received_at=received_at)


async def test_the_risk_read_keeps_the_raw_object_and_routes_to_its_month(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    received = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    snapshot = parse_risk_snapshot(_raw("indexer_in_memory_coin_raw.json"), received_at=received)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_risk_snapshot(session, snapshot)
        await insert_risk_snapshot(session, snapshot)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        stored = (
            (
                await session.execute(
                    text(
                        "SELECT count(*) OVER () AS n, tableoid::regclass::text AS part, holders, "
                        "snipers, top10_share, raw FROM meme_risk_snapshots WHERE mint = :mint"
                    ),
                    {"mint": snapshot.mint},
                )
            )
            .mappings()
            .one()
        )
    assert stored["n"] == 1 and stored["part"] == "meme_risk_snapshots_2026_11"
    assert stored["holders"] == 24 and stored["snipers"] == 19
    assert stored["top10_share"] == Decimal("0.000001")
    assert len(stored["raw"]) == 65 and stored["raw"]["program"] == "raydium_launchpad"


async def test_the_real_graduated_coin_writes_completed_at_through_the_real_parser(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The root cause, closed from the reading side: the live ``/coins/{mint}``
    of a graduated coin parses (``complete = true``, virtual reserve > 0), and
    the token row it teaches carries ``rest_complete_seen_at`` — once. Since
    T4.2d it does **not** carry ``completed_at``: the photo's reserve is zero
    (the SOL left for the pool), and a zero reserve classifies nothing until
    the PumpPortal ``migrate`` frame brings the pool."""
    state = normalize.parse_curve_state_rest(_raw("frontend_api_v3_coin_graduated_raw.json"))
    assert state.complete and state.real_token_reserves == 0 and state.real_sol_reserves == 0
    row = token_row_from_curve(state)
    assert row.rest_complete_seen_at == state.observed_at and row.completed_at is None
    assert row.initial_real_token_reserves is None, "no record given, no denominator claimed"
    migrated = state.observed_at + timedelta(seconds=1)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(session, row)
        before = await session.scalar(
            text("SELECT completed_at FROM meme_tokens WHERE mint = :mint"), {"mint": state.mint}
        )
        await upsert_token(
            session,
            TokenRow(
                mint=state.mint,
                first_seen_source="pumpportal_ws",
                first_seen_at=migrated,
                last_seen_at=migrated,
                migrated_at=migrated,
                migrated_pool="pump-amm",
                pool_created_at=migrated,
                pool_created_source="pumpportal_ws",
                completed_at=migrated,
            ),
        )
        completed = await session.scalar(
            text("SELECT completed_at FROM meme_tokens WHERE mint = :mint"), {"mint": state.mint}
        )
    assert before is None, "the zero-reserve photo alone is not a completion"
    assert completed == migrated, "the pool is"


async def test_a_migrated_mint_without_a_completion_reading_comes_back_for_its_final_read(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 12, 2, 12, 0, tzinfo=UTC)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session,
            TokenRow(
                mint="FINAL_READ",
                first_seen_source="pumpportal_ws",
                first_seen_at=now,
                last_seen_at=now,
                created_at=now,
                creator="C",
                migrated_at=now,
                migrated_pool="pump-amm",
            ),
        )
        await upsert_token(
            session,
            TokenRow(
                mint="DONE",
                first_seen_source="pumpfun_rest",
                first_seen_at=now,
                last_seen_at=now,
                created_at=now,
                rest_complete_seen_at=now,
            ),
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        tracked = {
            t.mint: t for t in await load_tracked(session, cutoff=now - timedelta(hours=24), cap=50)
        }
    assert "DONE" not in tracked, "a curve the REST photo said complete is static: no more budget"
    pending = tracked["FINAL_READ"]
    assert pending.migrated and pending.final_read_pending and pending.creator == "C"
    tracker = MintTracker(window_minutes=1440, cap=50)
    tracker.observe(pending)
    assert tracker.plan(now, budget=1).selected == ("FINAL_READ",)


async def test_fold_minute_writes_the_0023_columns_from_a_real_entry_and_a_real_tape(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    boundary = datetime(2026, 10, 7, 15, 1, tzinfo=UTC)
    # The ``graduated`` capture: a different board and different serverTs from the
    # ``new`` rows the first test wrote, so the PK (observed_at, board, mint) is new.
    collector = _ingest(boundary - timedelta(seconds=50), board="graduated")
    entry = next(
        p.entry for p in collector.mirrors["graduated"].presences.values() if p.entry.holders
    )
    mint = entry.mint
    page = parse_trades_page(mint, _raw("swap_api_trades_5ejA_raw.json"), received_at=boundary)
    trades, _ = trade_rows(page.trades[:4])
    shifted = [
        _shift(
            r,
            block_time=boundary - timedelta(seconds=10 * (i + 1)),
            received_at=boundary - timedelta(seconds=2),
        )
        for i, r in enumerate(trades)
    ]
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session,
            TokenRow(
                mint=mint,
                first_seen_source="trenches_ws",
                first_seen_at=boundary,
                last_seen_at=boundary,
                creator=CREATOR,
            ),
        )
        await insert_trades(session, shifted)
    tracker = MintTracker(window_minutes=1440, cap=50)
    tracker.observe(
        TrackedMint(
            mint=mint,
            first_seen_at=boundary - timedelta(minutes=5),
            created_at=boundary - timedelta(minutes=5),
            creator=CREATOR,
            initial_real_token_reserves=Decimal("793100000"),
            board="new",
        )
    )
    puller = TradesPuller(cast(Any, None), budget_60s=900, cycle_s=10)
    puller.coverage[mint] = TapeCoverage(covered_since=boundary - timedelta(minutes=3))
    state = RadarState(last_folded_minute=boundary - timedelta(minutes=1))
    state.observe(
        mint,
        CurveObservation(
            observed_at=boundary - timedelta(seconds=20),
            source="pumpfun_rest",
            real_token_reserves=Decimal("396550000"),
            mcap_sol=Decimal("27.9589934762"),
            complete=False,
        ),
    )
    ctx = RadarContext(
        config=MemeConfig(),
        session_factory=db_session_factory,
        tracker=tracker,
        state=state,
        events=cast(Any, None),
        curves=cast(Any, None),
        chain=cast(Any, None),
        sources=SourcesState(),
        boards=collector,
        trades=puller,
        risk=None,
    )
    written = await fold_minute(ctx, boundary)
    assert len(written) == 1
    async with role_session(db_session_factory, db_role=WORKER) as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT holders, holders_source, top10_share, dev_share, snipers, buys_1m, sells_1m, net_sol_flow_1m, curve_volume_1m_sol, tape_reason, creator_sold, creator_net_seller, unique_buyers, buy_sell_ratio, buy_sell_ratio_reason, curve_progress_pct FROM meme_features_1m WHERE mint = :mint AND end_time = :t"
                    ),
                    {"mint": mint, "t": boundary},
                )
            )
            .mappings()
            .one()
        )
        boards = await session.scalar(
            text(
                "SELECT count(*) FROM meme_board_observations WHERE mint = :mint AND minute_end = :t"
            ),
            {"mint": mint, "t": boundary},
        )
    assert row["holders"] == entry.holders and row["holders_source"] == "trenches_ws"
    assert row["top10_share"] == entry.top10_share and row["snipers"] == entry.snipers
    assert row["tape_reason"] is None and row["buys_1m"] + row["sells_1m"] == 4
    assert row["curve_volume_1m_sol"] > 0 and row["creator_sold"] is not None
    assert row["creator_net_seller"] is not None and row["curve_progress_pct"] == Decimal(
        "0.500000"
    )
    assert (row["buy_sell_ratio"] is None) == (row["buy_sell_ratio_reason"] is not None)
    assert boards == 1, "the board minute of the same boundary was written by the same fold"


async def test_the_lab_bets_feed_the_priority_and_the_roles_hold(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        assert await open_bet_mints(session) == frozenset()
    async with role_session(db_session_factory, db_role=APP) as session:
        n = await session.scalar(text("SELECT count(*) FROM meme_board_observations"))
        assert n is not None
        m = await session.scalar(text("SELECT count(*) FROM meme_risk_snapshots"))
        assert m is not None
    with pytest.raises((ProgrammingError, DBAPIError), match="permission denied"):
        async with role_session(db_session_factory, db_role=APP) as session:
            await session.execute(text("DELETE FROM meme_board_observations"))
    with pytest.raises((ProgrammingError, DBAPIError), match="permission denied"):
        async with role_session(db_session_factory, db_role=WORKER) as session:
            await session.execute(text("UPDATE meme_risk_snapshots SET holders = 0"))
