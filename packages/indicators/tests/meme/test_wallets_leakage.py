"""The leak tests of §2.1 plus the cheats that must be caught.

1. No trade mined **or** received at/after ``T_D`` changes D's snapshot (nor a
   link, create or funder known after ``T_D``).
2. A strategy that reads D's snapshot before ``published_at`` is caught.
3. An event received after the theoretical landing does not buy retroactively.
4. A ranker that peeks at future trades is caught by the perturbation test.
5. Decisions already taken do not change when later, not-yet-received events
   change (intraday prefix, Astra).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from hunter_indicators.meme.wallets.entities import Link
from hunter_indicators.meme.wallets.follow import ArmDecision, run_arm
from hunter_indicators.meme.wallets.leakage import (
    fingerprint,
    ranker_leaks,
    snapshot_violations,
    strip_future,
)
from hunter_indicators.meme.wallets.lots import Lot
from hunter_indicators.meme.wallets.params import FollowPolicy
from hunter_indicators.meme.wallets.policy import simulate_copy
from hunter_indicators.meme.wallets.pricing import MintTape
from hunter_indicators.meme.wallets.ranking import RankInputs, build_snapshot, cut_of
from hunter_indicators.meme.wallets.snapshot import Snapshot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill
from packages.indicators.tests.meme.test_wallets_builders import SOL, TOKEN, at, curve, fill
from packages.indicators.tests.meme.test_wallets_ranking import DAY, S_EXIT_V, S_EXIT_W, week

pytestmark = pytest.mark.unit

CUT = cut_of(DAY)
CUT_S = 7 * 86_400
CUT_SLOT = CUT_S * 5 // 2


def _base() -> RankInputs:
    """W01 is created by V: harmless unless V becomes W's funder (only known after T_D)."""
    w, cw = week("W", S_EXIT_W)
    v, cv = week("V", S_EXIT_V)
    cw = [c if c.mint != "W01" else replace(c, creator="V") for c in cw]
    return RankInputs(fills=(*w, *v), creates=(*cw, *cv))


def _future(base: RankInputs) -> RankInputs:
    """Things a cheater would love: all after T_D by mining time or by arrival."""
    late_dump = fill(wallet="W", side="sell", slot=CUT_SLOT - 5, sol=50 * SOL, atoms=TOKEN, mint="W60",
                     t=CUT_S - 2, received_delay=3.0, reserves=curve(31 * SOL, 2_000_000_000 * TOKEN))  # fmt: skip
    tomorrow = [
        fill(
            wallet="V",
            side="buy",
            slot=CUT_SLOT + 10 * i,
            sol=SOL,
            atoms=TOKEN,
            mint=f"N{i}",
            t=CUT_S + i,
        )
        for i in range(30)
    ]
    link = Link("V", "W", "strong", CUT + timedelta(seconds=1), "F")
    own = CreateEvent("W00", "W", 1_000, at(400), CUT + timedelta(seconds=5))
    return replace(
        base,
        fills=(*base.fills, late_dump, *tomorrow),
        links=(*base.links, link),
        creates=(*base.creates, own),
        funders={"W": ("V", CUT + timedelta(hours=1))},
        opening_lots=(
            Lot("W", "W60", 5_000_000 * TOKEN, SOL, CUT_SLOT + 100, CUT + timedelta(hours=1)),
            Lot("W", "W30", 5_000_000 * TOKEN, SOL, 3 * 216_000, CUT - timedelta(days=4)),
        ),
    )


def test_nothing_mined_or_received_at_or_after_the_cut_changes_the_snapshot() -> None:
    base = _base()
    future = _future(base)
    assert fingerprint(build_snapshot(future, DAY)) == fingerprint(build_snapshot(base, DAY))
    assert not ranker_leaks(build_snapshot, future, DAY)
    assert strip_future(future, CUT).fills == base.fills


def test_the_future_inputs_would_change_the_snapshot_if_known_before_the_cut() -> None:
    """Sensitivity of the test above: each future item matters once moved before T_D."""
    base = _base()
    reference = fingerprint(build_snapshot(base, DAY))
    early = CUT - timedelta(seconds=10)
    link = replace(base, links=(Link("V", "W", "strong", early, "F"),))
    # the earliest received create wins, so the W-created one replaces the dev one here
    own_creates = tuple(c if c.mint != "W00" else replace(c, creator="W") for c in base.creates)
    own = replace(base, creates=own_creates)
    dump = fill(
        wallet="W",
        side="sell",
        slot=CUT_SLOT - 50,
        sol=50 * SOL,
        atoms=TOKEN,
        mint="W60",
        t=CUT_S - 20,
    )
    late = replace(base, fills=(*base.fills, dump))
    funded = replace(base, funders={"W": ("V", early)})
    for moved in (link, own, late, funded):
        assert fingerprint(build_snapshot(moved, DAY)) != reference


def test_a_ranker_that_peeks_at_future_trades_is_caught() -> None:
    def cheat(inputs: RankInputs, day: date) -> Snapshot:
        peeked = build_snapshot(inputs, day + timedelta(days=1))  # its "today" includes day D
        return replace(peeked, day=day, cut=cut_of(day))

    assert ranker_leaks(cheat, _future(_base()), DAY)

    def ignores_arrival(inputs: RankInputs, day: date) -> Snapshot:
        cut = cut_of(day)
        mined = tuple(
            replace(f, received_at=min(f.received_at, f.block_time))
            for f in inputs.fills
            if f.block_time < cut
        )
        return build_snapshot(replace(inputs, fills=mined), day)

    assert ranker_leaks(ignores_arrival, _future(_base()), DAY)


def _published(day: date, hours: float) -> Snapshot:
    return build_snapshot(_base(), day).published(cut_of(day) + timedelta(hours=hours))


def test_a_strategy_reading_the_snapshot_before_publication_is_caught() -> None:
    d_prev = replace(_published(DAY, 2.5), snapshot_id="prev", day=DAY - timedelta(days=1),
                     cut=CUT - timedelta(days=1), published_at=CUT - timedelta(hours=21.5))  # fmt: skip
    d_today = _published(DAY, 2.5)
    snaps = (d_prev, d_today)
    one_am = fill(
        wallet="W",
        side="buy",
        slot=CUT_SLOT + 9_000,
        sol=SOL,
        atoms=TOKEN,
        mint="Q",
        t=CUT_S + 3_600,
    )
    honest = run_arm([one_am], snaps, {}, FollowPolicy(), "follow")
    assert honest[0].snapshot_id == "prev"
    assert snapshot_violations(honest, snaps) == ()
    cheat = (
        replace(honest[0], snapshot_id=d_today.snapshot_id, bet=True),
    )  # reads today's at 01:00
    assert snapshot_violations(cheat, snaps) == (f"{one_am.signature}:published_after_decision",)
    unpublished = replace(d_today, published_at=None)
    assert snapshot_violations(cheat, (d_prev, unpublished)) == (f"{one_am.signature}:unpublished",)


def test_an_event_received_after_the_theoretical_landing_does_not_buy() -> None:
    late = fill(wallet="L", side="buy", slot=100, sol=SOL, atoms=TOKEN, received_delay=2.5)
    out = simulate_copy(
        late,
        leader_wallets=frozenset({"L"}),
        tape=MintTape([late]),
        policy=FollowPolicy(),
        horizon_slot=10**9,
    )
    assert (out.status, out.reason, out.entry_slot) == ("refused", "late_event", None)


def test_decisions_already_taken_do_not_change_when_later_events_change() -> None:
    snap = _published(DAY, 2.5)
    morning = [
        fill(wallet="W", side="buy", slot=CUT_SLOT + 30_000 + i, sol=SOL, atoms=TOKEN, mint=f"P{i}")
        for i in range(5)
    ]
    afternoon = [
        fill(
            wallet="W",
            side="buy",
            slot=CUT_SLOT + 90_000 + i,
            sol=SOL,
            atoms=TOKEN,
            mint=f"P{i % 2}",
        )
        for i in range(30)
    ]
    altered = [replace(f, sol_lamports=f.sol_lamports * 7, mint="P0") for f in afternoon]
    a: tuple[ArmDecision, ...] = run_arm(
        [*morning, *afternoon], (snap,), {}, FollowPolicy(), "follow"
    )
    b = run_arm([*morning, *altered], (snap,), {}, FollowPolicy(), "follow")
    assert a[:5] == b[:5]


def test_strip_future_keeps_exactly_what_was_known() -> None:
    future = _future(_base())
    stripped = strip_future(future, CUT)
    assert all(f.block_time < CUT and f.received_at < CUT for f in stripped.fills)
    assert all(link.known_at < CUT for link in stripped.links)
    assert all(c.received_at < CUT for c in stripped.creates)
    assert dict(stripped.funders) == {}
    assert isinstance(stripped.fills[0], Fill)


def test_opening_lots_are_only_the_ones_preserved_before_the_window_start() -> None:
    """Code review HIGH: a lot opened after the cut leaked, and one opened inside the window
    was counted twice (once as a lot, once through its own buy)."""
    base = _base()
    future = _future(base)
    assert fingerprint(build_snapshot(replace(base, opening_lots=future.opening_lots), DAY)) == (
        fingerprint(build_snapshot(base, DAY))
    )
    stripped = strip_future(future, CUT)
    assert stripped.opening_lots == ()
