"""The T4.2c changes to the tracked set: the final read of a finished curve (the
root cause of the hour with zero ``complete = true`` snapshots), the eviction of
a curve quoted in something other than SOL, and the declared priority order.

No database and no socket, like ``test_tracker.py``: the budget decisions live
in the tracker and a fake clock proves them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hunter_meme_worker.discovery import token_row_from_event
from hunter_meme_worker.tracker import (
    TIER_FINAL_READ,
    TIER_GRADUATING,
    TIER_NEW,
    TIER_OPEN_BET,
    TIER_REST,
    TIER_YOUNG,
    MintTracker,
    TrackedMint,
)

from hunter_exchanges.pumpfun.models import NormalizedMemeMigration, NormalizedMemeTokenCreated

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 12, 5, 0, tzinfo=UTC)


def _tracked(
    mint: str, *, minutes_old: int = 1, polled_minutes_ago: int | None = None, **kw: object
) -> TrackedMint:
    created = NOW - timedelta(minutes=minutes_old)
    return TrackedMint(
        mint=mint,
        first_seen_at=created,
        created_at=created,
        last_polled_at=None
        if polled_minutes_ago is None
        else NOW - timedelta(minutes=polled_minutes_ago),
        **kw,  # type: ignore[arg-type]
    )


def _create(mint: str, at: datetime) -> NormalizedMemeTokenCreated:
    return NormalizedMemeTokenCreated(
        mint=mint,
        name="n",
        symbol="s",
        uri="u",
        creator="CREATOR",
        created_at=at,
        bonding_curve="curve",
        initial_virtual_sol_reserves=Decimal(30),
        initial_virtual_token_reserves=Decimal(1_073_000_000),
        signature="sig-create",
        received_at=at,
        observed_at=at,
    )


def _migrate(mint: str, at: datetime) -> NormalizedMemeMigration:
    return NormalizedMemeMigration(
        mint=mint,
        pool="pump-amm",
        migrated_at=at,
        signature="sig-migrate",
        received_at=at,
        observed_at=at,
    )


def _tracked_from_frames(tracker: MintTracker, mint: str, at: datetime) -> None:
    """The discovery loop's own conversion, frame by frame (``discovery._tracked_from_row``)."""
    from hunter_meme_worker.discovery import (
        _tracked_from_row,  # pyright: ignore[reportPrivateUsage]
    )

    tracker.observe(_tracked_from_row(token_row_from_event(_create(mint, at))))
    tracker.observe(_tracked_from_row(token_row_from_event(_migrate(mint, at))))


def test_the_root_cause_a_curve_that_migrates_before_its_first_poll_was_never_read() -> None:
    """The measured production hour: 43/49 graduations in the creation slot, the
    ``migrate`` frame before the first poll, eviction on ``migrated`` — so no
    snapshot with ``complete = true`` and no ``completed_at``, ever. Now the mint
    survives ``prune`` for exactly one poll, ranked right after open bets."""
    tracker = MintTracker(window_minutes=1440, cap=10)
    _tracked_from_frames(tracker, "instant", NOW - timedelta(seconds=5))
    tracked = tracker.get("instant")
    assert tracked is not None and tracked.migrated and tracked.final_read_pending
    assert tracked.creator == "CREATOR", "the creator is what the tape's creator columns need"
    aged_out, _ = tracker.prune(NOW)
    assert aged_out == (), "the finished curve was evicted before its final read"
    plan = tracker.plan(NOW, budget=1)
    assert plan.selected == ("instant",)
    assert tracker.tier(tracked, NOW, {}) == TIER_FINAL_READ
    # The final read happened: the mint has nothing left to teach the radar.
    tracker.mark_polled("instant", NOW)
    read = tracker.get("instant")
    assert read is not None and not read.final_read_pending
    aged_out, _ = tracker.prune(NOW)
    assert aged_out == ("instant",)


def test_the_old_shape_of_the_bug_a_migrated_mint_without_a_pending_read_is_evicted() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.observe(_tracked("done", migrated=True))
    assert tracker.prune(NOW)[0] == ("done",)


def test_a_completion_seen_by_the_poller_clears_the_pending_read_and_evicts() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.observe(_tracked("g", complete=True, final_read_pending=True))
    assert tracker.prune(NOW)[0] == ()
    tracker.mark_polled("g", NOW)
    assert tracker.prune(NOW)[0] == ("g",)


def test_a_curve_quoted_in_something_other_than_sol_stops_costing_budget() -> None:
    """The adendo's 2–4 wasted requests a minute: one refusal, then gone."""
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.observe(_tracked("usdc"))
    tracker.observe(_tracked("sol"))
    tracker.mark_quote_unsupported("usdc")
    assert tracker.prune(NOW)[0] == ("usdc",)
    assert tracker.plan(NOW, budget=5).selected == ("sol",)


def test_the_priority_order_is_open_bets_final_reads_graduating_new_young_rest() -> None:
    tracker = MintTracker(window_minutes=1440, cap=20, young_minutes=30)
    tracker.observe(_tracked("rest", minutes_old=600, polled_minutes_ago=1))
    tracker.observe(_tracked("young", minutes_old=5, polled_minutes_ago=1))
    tracker.observe(_tracked("new", minutes_old=5, polled_minutes_ago=1, board="new"))
    tracker.observe(_tracked("grad", minutes_old=50, polled_minutes_ago=1, board="graduating"))
    tracker.observe(
        _tracked(
            "final", minutes_old=5, polled_minutes_ago=1, migrated=True, final_read_pending=True
        )
    )
    tracker.observe(_tracked("bet", minutes_old=700, polled_minutes_ago=1))
    boosted = {"bet": TIER_OPEN_BET}
    plan = tracker.plan(NOW, budget=6, boosted=boosted)
    assert plan.selected == ("bet", "final", "grad", "new", "young", "rest")
    tiers = {m.mint: tracker.tier(m, NOW, boosted) for m in tracker.snapshot()}
    assert tiers == {
        "bet": TIER_OPEN_BET,
        "final": TIER_FINAL_READ,
        "grad": TIER_GRADUATING,
        "new": TIER_NEW,
        "young": TIER_YOUNG,
        "rest": TIER_REST,
    }
    assert tracker.plan(NOW, budget=2, boosted=boosted).skipped == ("grad", "new", "rest", "young")


def test_inside_a_tier_the_least_recently_polled_still_goes_first() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.observe(_tracked("a", board="graduating", polled_minutes_ago=1))
    tracker.observe(_tracked("b", board="graduating", polled_minutes_ago=9))
    tracker.observe(_tracked("c", board="graduating"))
    assert tracker.plan(NOW, budget=3).selected == ("c", "b", "a")


def test_a_board_hint_and_a_creator_merge_like_state_and_identity() -> None:
    tracker = MintTracker(window_minutes=1440, cap=10)
    tracker.observe(_tracked("m", creator="X"))
    merged = tracker.observe(_tracked("m", creator=None, board="graduating"))
    assert merged.creator == "X" and merged.board == "graduating"
    merged = tracker.observe(_tracked("m", board="new"))
    assert merged.board == "new", "the board is state: the newest listing wins"
