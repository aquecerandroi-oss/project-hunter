"""The tracked set and the prioritiser, against the T4.1 capture.

No database and no socket: the tracker is where the budget decisions live, so the
things worth proving are exactly the ones a fake clock can prove — who stays, who
is dropped, who is polled first, and who is honestly reported as skipped.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun import normalize
from hunter_meme_worker.discovery import token_row_from_event
from hunter_meme_worker.tracker import MintTracker, TrackedMint

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
NOW = datetime(2026, 9, 12, 5, 0, tzinfo=UTC)


def _frames() -> list[dict[str, Any]]:
    """``parse_float=Decimal`` is not optional: the adapter refuses a float field
    outright (``normalize._decimal``), which is the same discipline that keeps a
    price from coming back as ``0.30000000000000004``."""
    raw = (FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text(encoding="utf-8")
    return [json.loads(line, parse_float=Decimal) for line in raw.splitlines() if line.strip()]


def _tracked(
    mint: str, *, minutes_old: int, polled_minutes_ago: int | None = None, **kw: Any
) -> TrackedMint:
    created = NOW - timedelta(minutes=minutes_old)
    return TrackedMint(
        mint=mint,
        first_seen_at=created,
        created_at=created,
        last_polled_at=None
        if polled_minutes_ago is None
        else NOW - timedelta(minutes=polled_minutes_ago),
        **kw,
    )


def test_the_capture_is_the_input_and_a_create_frame_becomes_a_tracked_mint() -> None:
    """The real T4.1 frames, through the real normalizer, into the tracker."""
    creates = [f for f in _frames() if f.get("txType") == "create" and f.get("pool") == "pump"]
    assert len(creates) >= 10, "the T4.1 capture no longer carries pump.fun creates"

    tracker = MintTracker(window_minutes=1440, cap=len(creates))
    for frame in creates:
        row = token_row_from_event(normalize.parse_new_token(frame))
        tracker.observe(
            TrackedMint(
                mint=row.mint,
                first_seen_at=row.first_seen_at,
                created_at=row.created_at,
                bonding_curve=row.bonding_curve,
            )
        )
    assert len(tracker) == len({f["mint"] for f in creates})
    assert all(m.bonding_curve for m in tracker.snapshot()), (
        "every create frame names a bonding curve; without it the RPC cannot reconcile"
    )


def test_a_migration_frame_never_blanks_what_the_create_frame_taught() -> None:
    """The schema's write-once rule, mirrored in memory so the two cannot disagree."""
    frames = _frames()
    create = next(f for f in frames if f.get("txType") == "create" and f.get("pool") == "pump")
    migration = dict(next(f for f in frames if f.get("txType") == "migrate"))
    migration["mint"] = create["mint"]

    tracker = MintTracker(window_minutes=1440, cap=10)
    created_row = token_row_from_event(normalize.parse_new_token(create))
    tracker.observe(
        TrackedMint(
            mint=created_row.mint,
            first_seen_at=created_row.first_seen_at,
            created_at=created_row.created_at,
            bonding_curve=created_row.bonding_curve,
        )
    )
    migrated_row = token_row_from_event(normalize.parse_migration(migration))
    merged = tracker.observe(
        TrackedMint(
            mint=migrated_row.mint,
            first_seen_at=migrated_row.first_seen_at,
            migrated=True,
        )
    )
    assert merged.created_at == created_row.created_at, "a later, poorer frame blanked the identity"
    assert merged.bonding_curve == created_row.bonding_curve
    assert merged.migrated is True, "migration is mutable state and the newest answer wins"


def test_a_migrated_or_complete_curve_leaves_the_set_and_keeps_nothing_else() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.observe(_tracked("young", minutes_old=1))
    tracker.observe(_tracked("migrated", minutes_old=1, migrated=True))
    tracker.observe(_tracked("complete", minutes_old=1, complete=True))
    aged_out, capped, pinned_kept = tracker.prune(NOW)
    assert aged_out == ("complete", "migrated"), "a static curve kept costing budget"
    assert capped == ()
    assert pinned_kept == ()
    assert [m.mint for m in tracker.snapshot()] == ["young"]


def test_an_old_mint_leaves_unless_its_mayhem_agent_is_still_running() -> None:
    """``paused`` is not ``ended`` (A4.1b §2), so it keeps the mint in the set."""
    tracker = MintTracker(window_minutes=60, cap=10)
    tracker.observe(_tracked("stale", minutes_old=120))
    tracker.observe(_tracked("paused_agent", minutes_old=120, mayhem_state="paused"))
    tracker.observe(_tracked("ended_agent", minutes_old=120, mayhem_state="completed"))
    aged_out, _, _ = tracker.prune(NOW)
    assert aged_out == ("ended_agent", "stale")
    assert [m.mint for m in tracker.snapshot()] == ["paused_agent"]


def test_the_cap_evicts_the_oldest_and_says_so_separately_from_ageing_out() -> None:
    """Two return values because they are two different operator facts."""
    tracker = MintTracker(window_minutes=1440, cap=2)
    for age in (1, 2, 3, 4):
        tracker.observe(_tracked(f"m{age}", minutes_old=age))
    aged_out, capped, pinned_kept = tracker.prune(NOW)
    assert aged_out == ()
    assert capped == ("m3", "m4"), "the cap did not keep the youngest"
    assert pinned_kept == ()
    assert [m.mint for m in tracker.snapshot()] == ["m1", "m2"]


def test_the_plan_polls_the_young_tier_first_and_the_never_polled_before_anyone() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10, young_minutes=30)
    tracker.observe(_tracked("young_polled", minutes_old=5, polled_minutes_ago=1))
    tracker.observe(_tracked("young_never", minutes_old=10))
    tracker.observe(_tracked("old_never", minutes_old=600))
    tracker.observe(_tracked("old_polled", minutes_old=700, polled_minutes_ago=90))

    plan = tracker.plan(NOW, budget=3)
    assert plan.selected == ("young_never", "young_polled", "old_never")
    assert plan.skipped == ("old_polled",)
    assert plan.skipped_count == 1


def test_a_budget_of_zero_skips_everything_and_reports_all_of_it() -> None:
    """The honest half of the starvation this design accepts: nothing is hidden."""
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.observe(_tracked("a", minutes_old=1))
    tracker.observe(_tracked("b", minutes_old=2))
    plan = tracker.plan(NOW, budget=0)
    assert plan.selected == ()
    assert plan.skipped == ("a", "b")


def test_least_recently_polled_wins_inside_a_tier_so_nobody_starves_forever() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10, young_minutes=30)
    tracker.observe(_tracked("recent", minutes_old=5, polled_minutes_ago=1))
    tracker.observe(_tracked("stalest", minutes_old=5, polled_minutes_ago=20))
    assert tracker.plan(NOW, budget=1).selected == ("stalest",)


def test_reconciliation_ranks_by_market_cap_and_ignores_a_mint_never_priced() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.observe(_tracked("small", minutes_old=1, mcap_sol=Decimal("10")))
    tracker.observe(_tracked("big", minutes_old=2, mcap_sol=Decimal("900")))
    tracker.observe(_tracked("unpriced", minutes_old=3))
    assert tracker.top_by_mcap(3) == ("big", "small")
    assert tracker.top_by_mcap(1) == ("big",)
    assert tracker.top_by_mcap(0) == ()


def test_marking_a_poll_records_the_market_cap_without_losing_the_old_one() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.observe(_tracked("m", minutes_old=1, mcap_sol=Decimal("5")))
    tracker.mark_polled("m", NOW, mcap_sol=None)
    kept = tracker.get("m")
    assert kept is not None
    assert kept.last_polled_at == NOW
    assert kept.mcap_sol == Decimal("5"), "a poll with no price erased the last known one"


def test_the_age_anchor_falls_back_to_first_seen_and_never_invents_a_birth() -> None:
    seen = NOW - timedelta(minutes=3)
    tracked = TrackedMint(mint="m", first_seen_at=seen)
    assert tracked.age_anchor == seen
    assert tracked.created_at is None


# T4.16b: a mint with an open paper bet, an open live position or a pending
# proposal is never evicted by the window or by the cap.


def test_a_pinned_mint_survives_the_window_it_would_otherwise_have_aged_out_of() -> None:
    tracker = MintTracker(window_minutes=60, cap=10)
    tracker.observe(_tracked("old_bet", minutes_old=120))
    tracker.observe(_tracked("old_nothing", minutes_old=120))
    tracker.pin(["old_bet"])
    aged_out, capped, pinned_kept = tracker.prune(NOW)
    assert aged_out == ("old_nothing",), "only the un-pinned mint aged out of the window"
    assert capped == ()
    assert pinned_kept == ("old_bet",)
    assert [m.mint for m in tracker.snapshot()] == ["old_bet"]


def test_a_pinned_mint_survives_the_cap_and_the_cap_shrinks_for_the_rest() -> None:
    """``effective_cap = min(cap, max(floor, cap - |pinned|))``: with a cap of
    25 and 3 pinned mints (below the floor's reach), the 25 free mints compete
    for 22 slots, not 25 — the three oldest go."""
    tracker = MintTracker(window_minutes=1440, cap=25)
    for age in range(1, 26):
        tracker.observe(_tracked(f"free{age}", minutes_old=age))
    tracker.observe(_tracked("bet1", minutes_old=100))
    tracker.observe(_tracked("bet2", minutes_old=200))
    tracker.observe(_tracked("bet3", minutes_old=300))
    tracker.pin(["bet1", "bet2", "bet3"])
    aged_out, capped, pinned_kept = tracker.prune(NOW)
    assert aged_out == ()
    assert pinned_kept == ("bet1", "bet2", "bet3")
    assert capped == ("free23", "free24", "free25"), "25 - 3 = 22 slots: the three oldest go"
    assert len(tracker) == 25, "22 free plus the 3 pinned — the pinned spent none of the 25"


def test_the_effective_cap_never_drops_below_the_floor_however_many_are_pinned() -> None:
    tracker = MintTracker(window_minutes=1440, cap=25)
    pinned = [f"bet{i}" for i in range(10)]
    for mint in pinned:
        tracker.observe(_tracked(mint, minutes_old=1))
    for age in range(30):
        tracker.observe(_tracked(f"free{age}", minutes_old=age + 1))
    tracker.pin(pinned)
    _, capped, pinned_kept = tracker.prune(NOW)
    assert len(pinned_kept) == 10
    # cap(25) - pinned(10) = 15, above the floor(20)? no: max(20, 15) = 20.
    assert len(tracker) - len(pinned_kept) == 20, "the floor of 20 won over 25 - 10"
    assert len(capped) == 30 - 20


def test_unpin_returns_a_mint_to_the_ordinary_window_and_cap() -> None:
    tracker = MintTracker(window_minutes=60, cap=10)
    tracker.observe(_tracked("m", minutes_old=120))
    tracker.pin(["m"])
    assert tracker.prune(NOW)[0] == (), "pinned: the window does not evict it"
    tracker.unpin(["m"])
    assert tracker.prune(NOW)[0] == ("m",), "unpinned: the ordinary rule applies again"


def test_set_pinned_replaces_the_whole_set_in_one_call() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.pin(["a", "b"])
    tracker.set_pinned(["b", "c"])
    assert tracker.pinned == frozenset({"b", "c"}), "a's pin did not survive the reload"
