"""T4.52b-3/4, pure (no Docker): the debounce, the in-memory dedupe guard, the
cache pruning (F1) and the row builder's fail-closed reasons (F3/F4/F5).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_meme_worker.event_gate_caches import (
    EventGateCaches,
    prune_event_gate_caches,
    refresh_event_gate_caches,
)
from hunter_meme_worker.event_gate_rows import EventReserves, build_event_row
from hunter_meme_worker.event_gate_runtime import Debouncer
from hunter_meme_worker.event_state import EVENT_FEED_WARMING, CurvePoint, MintEventState
from hunter_meme_worker.features_tape import HoldersObservation, TapeTrade
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


def test_debouncer_forget_drops_a_mints_seat() -> None:
    d = Debouncer(interval_s=0.1)
    d.poll("MINT", 0.0)
    assert d.size == 1
    d.forget("MINT")
    assert d.size == 0
    assert d.poll("MINT", 0.0) is True  # fresh again, not throttled by the stale entry


def test_debouncer_prune_drops_stale_or_untracked_mints() -> None:
    """F1: called every sync — a mint outside ``keep`` or whose last poll is
    older than ``max_age_s`` is forgotten, even without an explicit unsubscribe."""
    d = Debouncer(interval_s=0.1)
    d.poll("KEEP", 690.0)
    d.poll("DROP_OLD", 0.0)  # in keep, but its last poll is too old
    d.poll("DROP_UNKEPT", 695.0)  # recent, but no longer tracked
    d.prune(keep=frozenset({"KEEP", "DROP_OLD"}), now_s=700.0, max_age_s=600)
    assert d.size == 1
    assert d.poll("DROP_UNKEPT", 700.0) is True  # forgotten -> a fresh touch, not throttled


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


# ---- prune_event_gate_caches (F1: memory has to have a ceiling) -------------------


def test_prune_evicts_a_mint_no_longer_kept_or_refreshed_too_long_ago() -> None:
    caches = EventGateCaches()
    for mint in ("OLD", "KEPT", "AGED_OUT"):
        caches.base_rows[mint] = _base_row(mint, created_at=NOW)
        caches.pedigree[mint] = object()  # type: ignore[assignment]
        caches.updated_at[mint] = NOW
    caches.updated_at["OLD"] = NOW - timedelta(minutes=11)  # stale even though still "kept"
    prune_event_gate_caches(caches, keep=frozenset({"KEPT", "OLD"}), now=NOW, max_mints=150)
    assert set(caches.base_rows) == {"KEPT"}
    assert set(caches.pedigree) == {"KEPT"}
    assert set(caches.updated_at) == {"KEPT"}


def test_prune_enforces_a_hard_cap_of_max_mints_times_two() -> None:
    caches = EventGateCaches()
    mints = [f"M{i}" for i in range(5)]
    for i, mint in enumerate(mints):
        caches.base_rows[mint] = _base_row(mint, created_at=NOW)
        caches.updated_at[mint] = NOW - timedelta(seconds=i)  # M0 newest .. M4 oldest
    prune_event_gate_caches(caches, keep=frozenset(mints), now=NOW, max_mints=1)  # cap = 2
    assert len(caches.base_rows) == 2
    assert set(caches.base_rows) == {"M0", "M1"}  # the two most recently refreshed survive


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


# ---- F4: top10_share must fail exactly as closed as the 15-second row -------------


def test_top10_share_stays_none_like_the_15s_row_even_with_a_holders_reader() -> None:
    base = _base_row("MINT", created_at=NOW - timedelta(seconds=200))  # top10_share=None
    state = _state(
        "MINT", subscribed_at=NOW - timedelta(seconds=90), first_seen_at=NOW - timedelta(seconds=90)
    )
    readings = [
        HoldersObservation(
            observed_at=NOW - timedelta(seconds=10),
            received_at=NOW - timedelta(seconds=9),
            source="trenches_new",
            holders=10,
            top10_share=Decimal("0.4"),
            dev_share=Decimal("0.05"),
            snipers=1,
        )
    ]
    row = build_event_row(
        base,
        state,
        as_of=NOW,
        reserves=EventReserves(Decimal("30"), Decimal("700000000")),
        holders_readings=readings,
    )
    assert row.top10_share is None  # never computed independently of the 15s row
    assert row.top10_reason == base.top10_reason


# ---- F5: a curve that completed mid-flight must not slip past the gate ------------


def test_completed_at_is_set_from_state_when_the_base_row_has_none() -> None:
    base = _base_row("MINT", created_at=NOW - timedelta(seconds=200))  # completed_at=None
    state = _state(
        "MINT", subscribed_at=NOW - timedelta(seconds=90), first_seen_at=NOW - timedelta(seconds=90)
    )
    state.complete = True
    row = build_event_row(base, state, as_of=NOW, reserves=None, holders_readings=())
    assert row.completed_at == NOW


def test_completed_at_on_the_base_row_wins_even_if_the_live_state_disagrees() -> None:
    already_completed = NOW - timedelta(seconds=500)
    base = replace(
        _base_row("MINT", created_at=NOW - timedelta(seconds=200)), completed_at=already_completed
    )
    state = _state(
        "MINT", subscribed_at=NOW - timedelta(seconds=90), first_seen_at=NOW - timedelta(seconds=90)
    )
    state.complete = False
    row = build_event_row(base, state, as_of=NOW, reserves=None, holders_readings=())
    assert row.completed_at == already_completed


# ---- F3: the in-memory creator flow can only ADD a sale, never remove one ---------


def _flow_state(mint: str, *, covered_from_birth: bool, sold: bool) -> MintEventState:
    subscribed_at = NOW - timedelta(seconds=90)
    first_seen_at = subscribed_at if covered_from_birth else subscribed_at - timedelta(seconds=1000)
    state = MintEventState(mint=mint, subscribed_at=subscribed_at, first_seen_at=first_seen_at)
    state.creator = "CREATOR"
    state.trades.append(
        TapeTrade(
            block_time=NOW - timedelta(seconds=30),
            received_at=NOW - timedelta(seconds=30),
            trader="BUYER",
            side="buy",
            sol_lamports=1_000_000_000,
        )
    )
    if sold:
        sell = TapeTrade(
            block_time=NOW - timedelta(seconds=10),
            received_at=NOW - timedelta(seconds=10),
            trader="CREATOR",
            side="sell",
            sol_lamports=500_000_000,
        )
        state.trades.append(sell)
        state.creator_trades.append(sell)
    return state


def test_creator_sold_true_on_the_base_row_is_never_downgraded() -> None:
    base = replace(_base_row("MINT", created_at=NOW - timedelta(seconds=200)), creator_sold=True)
    state = _flow_state("MINT", covered_from_birth=False, sold=False)  # memory: unknown
    row = build_event_row(base, state, as_of=NOW, reserves=None, holders_readings=())
    assert row.creator_sold is True


def test_creator_sold_none_on_the_base_row_defers_to_the_flows_own_rule() -> None:
    base = _base_row("MINT", created_at=NOW - timedelta(seconds=200))  # creator_sold=None
    covered_no_sale = _flow_state("MINT", covered_from_birth=True, sold=False)
    row = build_event_row(base, covered_no_sale, as_of=NOW, reserves=None, holders_readings=())
    assert row.creator_sold is False  # covered from birth, no sale seen: a real False

    uncovered_no_sale = _flow_state("MINT", covered_from_birth=False, sold=False)
    row2 = build_event_row(base, uncovered_no_sale, as_of=NOW, reserves=None, holders_readings=())
    assert row2.creator_sold is None  # not covered from birth: unknown, never a lied False


def test_creator_sold_false_on_the_base_row_is_only_upgraded_by_a_witnessed_sale() -> None:
    base = replace(_base_row("MINT", created_at=NOW - timedelta(seconds=200)), creator_sold=False)
    quiet = _flow_state("MINT", covered_from_birth=False, sold=False)
    row_quiet = build_event_row(base, quiet, as_of=NOW, reserves=None, holders_readings=())
    assert row_quiet.creator_sold is False  # never downgraded further, and never blanked to None

    witnessed = _flow_state("MINT", covered_from_birth=False, sold=True)
    row_sold = build_event_row(base, witnessed, as_of=NOW, reserves=None, holders_readings=())
    assert row_sold.creator_sold is True  # a witnessed sale always adds
