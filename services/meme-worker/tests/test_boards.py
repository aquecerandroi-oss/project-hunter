"""The board collector over the live capture: one row per mint per board per
closed minute, the exposure interval, censoring on reconnect, the tracker
hints — no socket, no database."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from hunter_meme_worker.boards import BoardCollector, minute_end_of
from hunter_meme_worker.tracker import MintTracker

from hunter_exchanges.pumpfun.trenches_state import BoardEvent, BoardState

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
T0 = datetime(2026, 9, 12, 9, 0, 10, tzinfo=UTC)


def _events(board: str, *, start: datetime = T0, step_s: float = 1.0) -> list[BoardEvent]:
    """The capture replayed with a synthetic receive clock, one event per second."""
    capture = json.loads((FIXTURES / f"trenches_{board}.json").read_text(encoding="utf-8"))
    state = BoardState(board)
    events: list[BoardEvent] = []
    for index, frame in enumerate(capture["frames"]):
        payload = json.loads(frame["raw"], parse_float=Decimal)
        events.append(state.apply(payload, received_at=start + timedelta(seconds=index * step_s)))
    return events


def _collector(
    boards: tuple[str, ...] = ("new", "graduating", "graduated", "movers"),
) -> tuple[BoardCollector, MintTracker]:
    tracker = MintTracker(window_minutes=1440, cap=500)
    return BoardCollector(tracker, boards=boards), tracker


def test_minute_end_of_is_the_closed_minute_a_message_falls_in() -> None:
    assert minute_end_of(datetime(2026, 9, 12, 9, 0, 30, tzinfo=UTC)) == datetime(
        2026, 9, 12, 9, 1, tzinfo=UTC
    )
    assert minute_end_of(datetime(2026, 9, 12, 9, 1, 0, tzinfo=UTC)) == datetime(
        2026, 9, 12, 9, 2, tzinfo=UTC
    )


def test_the_new_board_capture_becomes_rows_with_exposure_and_patch_counts() -> None:
    collector, tracker = _collector()
    events = _events("new")
    for event in events:
        collector.ingest(event, session_key=0)
    boundary = minute_end_of(events[-1].received_at)
    rows = collector.close_minute(boundary)
    on_board = collector.listed_on("new")
    exits = [r for r in rows if r.left_board_at is not None]
    minute_rows = [r for r in rows if r.left_board_at is None]
    assert len(exits) == 3, "three removes in the capture are three exits"
    assert all(not r.exposure_censored for r in exits)
    assert {r.mint for r in minute_rows} == on_board
    assert all(r.minute_end == boundary and r.board == "new" for r in rows)
    assert all(r.observed_at == events[-1].observed_at for r in minute_rows)
    assert all(r.first_seen_in_board_at <= r.last_seen_in_board_at for r in rows)
    assert (
        sum(r.patches for r in minute_rows) + sum(r.patches for r in exits)
        == sum(sum(e.patch_ops.values()) for e in events if e.kind == "delta") - 3
    ), "every patch but the three removes is counted on some row"
    added = [r for r in minute_rows if r.first_seen_in_board_at > events[0].observed_at]
    assert added, "the mints added during the capture start their exposure at the add"
    assert all(isinstance(r.market_cap_usd, Decimal) for r in rows if r.market_cap_usd is not None)
    # The tracker learned the pump/SOL mints of the board, with the site's age as creation.
    assert len(tracker) >= 1
    tracked = next(iter(tracker.snapshot()))
    assert tracked.board == "new" and tracked.created_at is not None
    tokens = collector.take_tokens()
    assert tokens and all(t.first_seen_source == "trenches_ws" and t.pool == "pump" for t in tokens)
    assert collector.take_tokens() == []


def test_a_mint_absent_after_a_reconnect_is_censored_not_exited() -> None:
    collector, _ = _collector(("graduated",))
    events = _events("graduated")
    snapshot = events[0]
    collector.ingest(snapshot, session_key=0)
    victim = next(iter(snapshot.positions))
    # A fresh snapshot after a reconnect, without the victim.
    kept = tuple(e for e in snapshot.entries if e.mint != victim)
    after = BoardEvent(
        kind="snapshot",
        board="graduated",
        version=snapshot.version + 100,
        observed_at=snapshot.observed_at + timedelta(seconds=30),
        received_at=snapshot.received_at + timedelta(seconds=30),
        entries=kept,
        removed=(),
        positions={e.mint: i for i, e in enumerate(kept)},
    )
    collector.ingest(after, session_key=1)
    rows = collector.take_rows()
    assert len(rows) == 1 and rows[0].mint == victim
    assert rows[0].exposure_censored and rows[0].left_board_at is None
    assert rows[0].last_seen_in_board_at == snapshot.observed_at, (
        "censoring does not extend exposure"
    )
    # The same absence inside one live session (movers re-sends snapshots) is an exit.
    collector2, _ = _collector(("graduated",))
    collector2.ingest(snapshot, session_key=0)
    collector2.ingest(after, session_key=0)
    exit_row = collector2.take_rows()[0]
    assert not exit_row.exposure_censored and exit_row.left_board_at == after.observed_at


def test_a_minute_roll_emits_the_previous_minute_and_resets_patch_counts() -> None:
    collector, _ = _collector(("movers",))
    events = _events("movers", start=datetime(2026, 9, 12, 9, 0, 50, tzinfo=UTC), step_s=1.0)
    for event in events:
        collector.ingest(event, session_key=0)
    rows = collector.take_rows()
    first_minute = datetime(2026, 9, 12, 9, 1, tzinfo=UTC)
    assert rows and all(r.minute_end == first_minute for r in rows), "the roll closed 09:00–09:01"
    assert any(r.patches > 0 for r in rows)
    later = collector.close_minute(minute_end_of(events[-1].received_at))
    assert later and all(r.minute_end > first_minute for r in later)
    assert {r.mint for r in later} >= {r.mint for r in rows if r.left_board_at is None}


def test_readings_keep_the_newest_holders_per_mint_and_the_movers_board_is_not_tracked() -> None:
    collector, tracker = _collector(("movers",))
    for event in _events("movers"):
        collector.ingest(event, session_key=0)
    mint = next(iter(collector.listed_on("movers")))
    readings = collector.readings(mint)
    assert readings and readings[-1].received_at >= readings[0].received_at
    assert len(tracker) == 0, "movers lists other chains and programs; nothing is tracked from it"


def test_a_graduated_listing_seen_on_a_tracked_board_asks_for_a_final_read() -> None:
    """A ``graduating``-board entry with ``gd`` set is a finished curve the poller
    must read once (the T4.2c fix), and the token row carries ``completed_at``."""
    collector, tracker = _collector(("graduating",))
    events = _events("graduated")  # entries with gd set, relabelled onto a tracked board
    snapshot = events[0]
    relabelled = tuple(e.model_copy(update={"board": "graduating"}) for e in snapshot.entries)
    event = BoardEvent(
        kind="snapshot",
        board="graduating",
        version=1,
        observed_at=snapshot.observed_at,
        received_at=snapshot.received_at,
        entries=relabelled,
        removed=(),
        positions=dict(snapshot.positions),
    )
    collector.ingest(event, session_key=0)
    pump = [e for e in relabelled if e.is_pump_curve_on_sol and e.graduated_at is not None]
    assert pump
    tracked = tracker.get(pump[0].mint)
    assert tracked is not None and tracked.complete and tracked.final_read_pending
    token = {t.mint: t for t in collector.take_tokens()}[pump[0].mint]
    assert token.completed_at == pump[0].graduated_at
