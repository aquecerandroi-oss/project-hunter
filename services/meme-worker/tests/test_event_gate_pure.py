"""T4.52b-3, pure (no Docker): the debounce, the in-memory dedupe guard and
the row builder's fail-closed reasons.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_meme_worker.event_gate_caches import EventGateCaches, refresh_event_gate_caches
from hunter_meme_worker.event_gate_rows import EventReserves, build_event_row
from hunter_meme_worker.event_gate_runtime import Debouncer
from hunter_meme_worker.event_state import EVENT_FEED_WARMING, CurvePoint, MintEventState
from hunter_meme_worker.proposals_row import GateRow

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _base_row(mint: str, *, created_at: datetime) -> GateRow:
    return GateRow(
        mint=mint,
        end_time=created_at,
        created_at=created_at,
        curve_progress_pct=None,
        progress_reason=None,
        mcap_sol=None,
        creator_sold=None,
        curve_volume_1m_sol=None,
        completed_at=None,
        migrated_at=None,
        snapshot=None,
        symbol="TEST",
        series="meme_features_15s_v1",
        initial_real_token_reserves=Decimal("793100000"),
    )


# ---- Debouncer --------------------------------------------------------------------


def test_debounce_evaluates_the_first_touch_immediately() -> None:
    d = Debouncer(interval_s=0.1)
    assert d.poll("MINT", 0.0) is True


def test_debounce_marks_a_second_touch_inside_the_window_dirty_not_ready() -> None:
    d = Debouncer(interval_s=0.1)
    assert d.poll("MINT", 0.0) is True
    assert d.poll("MINT", 0.05) is False
    assert d.drain_ready(0.05) == []


def test_debounce_flush_picks_up_a_dirty_mint_once_the_window_passes() -> None:
    d = Debouncer(interval_s=0.1)
    d.poll("MINT", 0.0)
    d.poll("MINT", 0.05)  # dirty
    assert d.drain_ready(0.11) == ["MINT"]
    assert d.drain_ready(0.11) == []  # drained once, not re-armed without another touch


def test_debounce_tracks_mints_independently() -> None:
    d = Debouncer(interval_s=0.1)
    assert d.poll("A", 0.0) is True
    assert d.poll("B", 0.0) is True
    assert d.poll("A", 0.05) is False
    assert d.poll("B", 0.2) is True


# ---- recently_proposed (the cross-lane dedupe guard) -------------------------------


def test_recently_proposed_is_seen_immediately_by_the_other_lane() -> None:
    caches = EventGateCaches()
    caches.mark_proposed("MINT", "rs-1", now=NOW, ttl_s=120)
    assert caches.recently_proposed_mints("rs-1", now=NOW) == frozenset({"MINT"})


def test_recently_proposed_expires_after_its_own_ttl() -> None:
    caches = EventGateCaches()
    caches.mark_proposed("MINT", "rs-1", now=NOW, ttl_s=60)
    after = NOW + timedelta(seconds=61)
    assert caches.recently_proposed_mints("rs-1", now=after) == frozenset()


def test_recently_proposed_is_scoped_to_its_own_rule_set() -> None:
    caches = EventGateCaches()
    caches.mark_proposed("MINT", "rs-1", now=NOW, ttl_s=120)
    assert caches.recently_proposed_mints("rs-2", now=NOW) == frozenset()


def test_refresh_replaces_open_mints_wholesale_but_merges_base_rows() -> None:
    caches = EventGateCaches()
    old_row = _base_row("OLD", created_at=NOW - timedelta(minutes=5))
    caches.base_rows["OLD"] = old_row
    new_row = _base_row("NEW", created_at=NOW)
    refresh_event_gate_caches(
        caches,
        specs=(),
        rows=[new_row],
        open_mints={"rs-1": frozenset({"NEW"})},
        pedigree={},
        e2b=None,
        now=NOW,
    )
    assert caches.open_mints == {"rs-1": frozenset({"NEW"})}
    assert caches.base_rows["OLD"] is old_row  # a mint absent this tick keeps its last row
    assert caches.base_rows["NEW"] is new_row


# ---- build_event_row: fail-closed reasons ------------------------------------------


def _state(mint: str, *, subscribed_at: datetime, first_seen_at: datetime) -> MintEventState:
    return MintEventState(mint=mint, subscribed_at=subscribed_at, first_seen_at=first_seen_at)


def test_warming_tape_reads_event_feed_warming_not_a_crash() -> None:
    base = _base_row("MINT", created_at=NOW - timedelta(seconds=200))
    state = _state(
        "MINT", subscribed_at=NOW - timedelta(seconds=5), first_seen_at=NOW - timedelta(seconds=5)
    )
    row = build_event_row(base, state, as_of=NOW, reserves=None, holders_readings=())
    assert row.tape_reason == EVENT_FEED_WARMING
    assert row.buys_1m is None and row.unique_buyers_1m is None


def test_no_reserves_or_total_supply_leaves_snapshot_none() -> None:
    base = _base_row("MINT", created_at=NOW - timedelta(seconds=200))
    state = _state(
        "MINT", subscribed_at=NOW - timedelta(seconds=90), first_seen_at=NOW - timedelta(seconds=90)
    )
    state.points.append(
        CurvePoint(
            observed_at=NOW,
            received_at=NOW,
            mcap_sol=Decimal("30"),
            real_sol=Decimal("30"),
            real_token=Decimal("700000000"),
            mayhem=False,
        )
    )
    row = build_event_row(base, state, as_of=NOW, reserves=None, holders_readings=())
    assert row.snapshot is None  # no total_supply -> evaluate_gate refuses no_snapshot_for_quote


def test_no_holders_reader_leaves_holders_and_dev_share_unknown() -> None:
    base = _base_row("MINT", created_at=NOW - timedelta(seconds=200))
    state = _state(
        "MINT", subscribed_at=NOW - timedelta(seconds=90), first_seen_at=NOW - timedelta(seconds=90)
    )
    row = build_event_row(
        base,
        state,
        as_of=NOW,
        reserves=EventReserves(Decimal("30"), Decimal("700000000")),
        holders_readings=(),
    )
    assert row.holders is None
    assert row.dev_share is None
