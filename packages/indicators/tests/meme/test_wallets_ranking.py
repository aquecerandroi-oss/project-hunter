"""The daily snapshot end to end on a synthetic week (fixtures, not data).

Entity ``W`` makes 21 clean round trips (3 mints a day, 200 s holds, +0.3 SOL
each) whose copies are profitable; ``V`` does the same with a weaker exit; the
market buyer ``X`` only buys. Expected: W rank 1, V rank 2, X ineligible.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from hunter_indicators.meme.wallets.entities import Link
from hunter_indicators.meme.wallets.lots import Lot
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.ranking import RankInputs, build_snapshot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Reserves
from packages.indicators.tests.meme.test_wallets_builders import (
    SOL,
    T0,
    TOKEN,
    at,
    create,
    curve,
    fill,
)

pytestmark = pytest.mark.unit

DAY = date(2026, 10, 13)  # cut = T0 + 7 days
DAY_SLOTS = 216_000
S_ENTRY = curve(40 * SOL, 800_000_000 * TOKEN)
S_EXIT_W = curve(50 * SOL, 640_000_000 * TOKEN)
S_EXIT_V = curve(46 * SOL, 695_652_173 * TOKEN)


def week(
    leader: str, exit_state: Reserves, *, seller: str | None = None, tag: str = ""
) -> tuple[list[Fill], list[CreateEvent]]:
    fills: list[Fill] = []
    creates: list[CreateEvent] = []
    for k in range(7):
        for j in range(3):
            mint = f"{leader}{tag}{k}{j}"
            s0 = k * DAY_SLOTS + 1_000 + j * 2_000
            creates.append(create(mint, "dev", s0))
            fills.append(
                fill(
                    wallet=leader,
                    side="buy",
                    slot=s0 + 100,
                    sol=SOL,
                    atoms=10_000_000 * TOKEN,
                    mint=mint,
                    reserves=S_ENTRY,
                    fee_bps=0,
                )
            )
            fills.append(
                fill(
                    wallet="X",
                    side="buy",
                    slot=s0 + 200,
                    sol=SOL // 10,
                    atoms=TOKEN,
                    mint=mint,
                    reserves=exit_state,
                    fee_bps=0,
                )
            )
            fills.append(
                fill(
                    wallet=seller or leader,
                    side="sell",
                    slot=s0 + 600,
                    sol=13 * SOL // 10,
                    atoms=10_000_000 * TOKEN,
                    mint=mint,
                    reserves=exit_state,
                    fee_bps=0,
                )
            )
    return fills, creates


def _inputs() -> RankInputs:
    w, cw = week("W", S_EXIT_W)
    v, cv = week("V", S_EXIT_V)
    return RankInputs(fills=(*w, *v), creates=(*cw, *cv))


def test_two_clean_entities_rank_by_c_pnl_and_the_pure_buyer_is_ineligible() -> None:
    snap = build_snapshot(_inputs(), DAY)
    w, v, x = snap.rows["W"], snap.rows["V"], snap.rows["X"]
    assert snap.cut == at(7 * 86_400)
    assert snap.published_at is None
    assert (w.rank, w.followed, w.reasons) == (1, True, ())
    assert (v.rank, v.followed, v.reasons) == (2, True, ())
    assert w.c_pnl_lamports > v.c_pnl_lamports > 0
    assert w.metrics is not None
    assert w.metrics.e_pnl_lamports == 21 * (3 * SOL // 10 - 2 * 5_000)  # +0.3 SOL each, 2 tx fees
    # the last copy's exit lands 5 slots after the last slot ever observed before the cut:
    # the horizon never extrapolates, so it is incomplete — not a sale (KB-0148)
    assert w.metrics.copies == 20
    assert "activity_episodes" in x.reasons and x.rank is None and not x.followed


def test_top_n_cuts_the_followed_set_and_ties_break_by_entity_hash() -> None:
    snap = build_snapshot(_inputs(), DAY, params=RankingParams(top_n=1))
    assert [snap.rows["W"].followed, snap.rows["V"].followed] == [True, False]
    a, ca = week("A", S_EXIT_W)
    b, cb = week("B", S_EXIT_W)
    tie = build_snapshot(RankInputs(fills=(*a, *b), creates=(*ca, *cb)), DAY)
    assert tie.rows["A"].c_pnl_lamports == tie.rows["B"].c_pnl_lamports
    import hashlib

    first = min(["A", "B"], key=lambda e: hashlib.sha256(e.encode()).hexdigest())
    assert tie.rows[first].rank == 1


def test_twins_linked_before_the_cut_rank_as_one_entity() -> None:
    fills, creates = week("T1", S_EXIT_W, seller="T2")
    link = Link("T1", "T2", "strong", T0, "F")
    merged = build_snapshot(
        RankInputs(fills=tuple(fills), creates=tuple(creates), links=(link,)), DAY
    )
    assert merged.rows["e:T1"].reasons == ()
    alone = build_snapshot(RankInputs(fills=tuple(fills), creates=tuple(creates)), DAY)
    assert "unmatched_share" in alone.rows["T2"].reasons  # sells without its own buys


def test_the_manifest_carries_the_parameter_hash_and_input_counts() -> None:
    snap = build_snapshot(_inputs(), DAY, code_version="abc123")
    assert snap.manifest["code_version"] == "abc123"
    assert snap.manifest["window_fills"] == str(2 * 21 * 3)
    assert len(snap.manifest["params_hash"]) == 64
    assert snap.snapshot_id.startswith("2026-10-13:")


def test_an_excluded_episode_cannot_rank_the_entity_through_its_copy() -> None:
    # Astra must-fix 7: a mint created by the entity's funder leaves E *and* C
    fills, creates = week("W", S_EXIT_W)
    by_funder = [c if c.mint != "W00" else create("W00", "FUND", c.slot) for c in creates]
    funders = {"W": ("FUND", T0)}
    base = build_snapshot(RankInputs(fills=tuple(fills), creates=tuple(creates)), DAY)
    moved = RankInputs(fills=tuple(fills), creates=tuple(by_funder), funders=funders)
    cut = build_snapshot(moved, DAY)
    before, after = base.rows["W"].metrics, cut.rows["W"].metrics
    assert before is not None
    assert after is not None
    assert after.copies == before.copies - 1
    assert cut.rows["W"].c_pnl_lamports < base.rows["W"].c_pnl_lamports


def test_copy_diagnostics_and_h2_support_are_published() -> None:
    snap = build_snapshot(_inputs(), DAY)
    w = snap.rows["W"].metrics
    assert w is not None
    assert (w.copies_incomplete, w.copies_contaminated) == (1, 0)
    assert snap.manifest["h2_comparable_entities"] == "0"
    assert snap.manifest["h2_supported"] == "false"


def _flood(day_index: int, count: int) -> list[Fill]:
    s0 = day_index * DAY_SLOTS + 100_000
    return [
        fill(
            wallet="W",
            side="buy",
            slot=s0 + i,
            sol=SOL // 1000,
            atoms=TOKEN,
            mint="FLOOD",
            fee_bps=0,
        )
        for i in range(count)
    ]


def test_the_volume_bot_rule_reads_only_the_previous_day() -> None:
    w, cw = week("W", S_EXIT_W)
    early = build_snapshot(RankInputs(fills=(*w, *_flood(0, 501)), creates=tuple(cw)), DAY)
    late = build_snapshot(RankInputs(fills=(*w, *_flood(6, 501)), creates=tuple(cw)), DAY)
    assert "volume_bot" not in early.rows["W"].reasons
    assert "volume_bot" in late.rows["W"].reasons


def test_the_horizon_stops_settle_seconds_before_the_cut() -> None:
    w, cw = week("W", S_EXIT_W)
    edge = fill(wallet="Z", side="buy", slot=7 * DAY_SLOTS - 3, sol=SOL, atoms=TOKEN, mint="E", t=7 * 86_400 - 1.2,
                received_delay=0.1)  # fmt: skip
    inputs = RankInputs(fills=(*w, edge), creates=tuple(cw))
    settled = max(f.slot for f in w)
    assert build_snapshot(inputs, DAY).manifest["horizon_slot"] == str(settled)
    loose = build_snapshot(inputs, DAY, params=RankingParams(settle_seconds=0))
    assert loose.manifest["horizon_slot"] == str(edge.slot)


def test_the_earliest_received_create_event_wins() -> None:
    fills, creates = week("W", S_EXIT_W)
    first = create("W00", "W", 1_000)
    later = replace(first, creator="dev", received_at=first.received_at + timedelta(seconds=30))
    others = [c for c in creates if c.mint != "W00"]
    a = build_snapshot(RankInputs(fills=tuple(fills), creates=(first, later, *others)), DAY)
    b = build_snapshot(RankInputs(fills=tuple(fills), creates=(later, first, *others)), DAY)
    for snap in (a, b):
        m = snap.rows["W"].metrics
        assert m is not None
        assert m.creator_share > 0


def test_opening_lots_are_mapped_to_the_entity() -> None:
    fills, creates = week("T1", S_EXIT_W)
    lot = Lot("T2", "LEGACY", 10 * TOKEN, SOL, -1_000, T0 - timedelta(hours=2))
    sale = fill(wallet="T1", side="sell", slot=50_000, sol=SOL, atoms=10 * TOKEN, mint="LEGACY")
    link = Link("T1", "T2", "strong", T0 - timedelta(days=1), "F")
    snap = build_snapshot(
        RankInputs(
            fills=(*fills, sale), creates=tuple(creates), links=(link,), opening_lots=(lot,)
        ),
        DAY,
    )
    m = snap.rows["e:T1"].metrics
    assert m is not None
    assert m.unmatched_share == 0.0


def test_h2_support_needs_at_least_the_minimum_comparable_entities() -> None:
    snap = build_snapshot(_inputs(), DAY, params=RankingParams(top_n=1, min_h2_entities=1))
    assert snap.manifest["h2_comparable_entities"] == "1"
    assert snap.manifest["h2_supported"] == "true"
    strict = build_snapshot(_inputs(), DAY, params=RankingParams(top_n=1, min_h2_entities=2))
    assert strict.manifest["h2_supported"] == "false"
