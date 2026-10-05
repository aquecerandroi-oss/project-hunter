"""`follow` and `control` as pure evaluate functions (§3, §3.2): snapshot in
force by ``published_at``, causal trigger rules, caps, and the seeded pairing.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from hunter_indicators.meme.wallets.entities import Entities
from hunter_indicators.meme.wallets.follow import (
    Arm,
    ArmContext,
    TriggerState,
    evaluate,
    pair_controls,
    pre_trade_real_sol,
    run_arm,
)
from hunter_indicators.meme.wallets.params import FollowPolicy
from hunter_indicators.meme.wallets.snapshot import RankRow, Snapshot, current_snapshot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill
from packages.indicators.tests.meme.test_wallets_builders import (
    SOL,
    T0,
    TOKEN,
    create,
    curve,
    fill,
    pool,
)

pytestmark = pytest.mark.unit

POLICY = FollowPolicy()
DAY_SLOTS = 216_000


def _snap(day: date, followed: str = "e:L", published_h: float = 2.5) -> Snapshot:
    ents = Entities(
        "v1",
        {"L": "e:L", "L2": "e:L", "C": "e:C"},
        {"e:L": frozenset({"L", "L2"}), "e:C": frozenset({"C"})},
    )
    rows = {
        followed: RankRow(followed, (), 1, True, 5 * SOL),
        "e:C": RankRow("e:C", (), 31, False, SOL),
        "N": RankRow("N", ("activity_episodes",), None, False, 9 * SOL),
        "N2": RankRow("N2", ("e_pnl_below_min", "c_pnl_not_positive"), None, False, -SOL),
    }
    cut = T0.replace(year=day.year, month=day.month, day=day.day)
    return Snapshot(f"{day}:x", day, cut, cut + timedelta(hours=published_h), ents, rows, {})


D1 = date(2026, 10, 7)  # cut = T0 + 1 day
SNAPS = (_snap(D1),)
IN_FORCE_SLOT = DAY_SLOTS + 9 * 3600 * 5 // 2  # 09:00 on D1: its snapshot (02:30) is in force


def _buy(
    wallet: str,
    slot: int = IN_FORCE_SLOT,
    sol: int = SOL,
    mint: str = "M1",
    received_delay: float = 0.5,
) -> Fill:
    return fill(
        wallet=wallet,
        side="buy",
        slot=slot,
        sol=sol,
        atoms=TOKEN,
        mint=mint,
        received_delay=received_delay,
    )


def _ctx(
    f: Fill,
    state: TriggerState | None = None,
    arm: Arm = "follow",
    creates: dict[str, CreateEvent] | None = None,
) -> ArmContext:
    return ArmContext(f, SNAPS, creates or {}, state or TriggerState(), POLICY, arm)


def test_snapshot_in_force_is_the_latest_published_at_or_before_the_decision() -> None:
    d0, d1 = _snap(date(2026, 10, 6)), _snap(D1)
    assert current_snapshot((d0, d1), d1.cut + timedelta(hours=1)) is d0  # D1 not yet published
    assert current_snapshot((d0, d1), d1.cut + timedelta(hours=3)) is d1
    assert current_snapshot((d1,), d1.cut + timedelta(hours=1)) is None


def test_follow_bets_on_the_first_qualifying_buy_of_a_followed_entity() -> None:
    d = evaluate(_ctx(_buy("L2")))
    assert (d.bet, d.reason, d.entity, d.snapshot_id) == (True, "trigger", "e:L", f"{D1}:x")
    assert evaluate(_ctx(_buy("C"))).reason == "not_in_arm"
    assert evaluate(_ctx(_buy("N"))).reason == "not_in_arm"


def test_control_arm_takes_eligible_entities_outside_the_top() -> None:
    assert evaluate(_ctx(_buy("C"), arm="control")).bet is True
    assert evaluate(_ctx(_buy("L"), arm="control")).reason == "not_in_arm"
    assert evaluate(_ctx(_buy("N"), arm="control")).reason == "not_in_arm"


def test_small_buys_do_not_trigger_and_do_not_consume_the_first_buy() -> None:
    fills = [
        _buy("L", sol=SOL // 20),
        _buy("L", slot=IN_FORCE_SLOT + 10),
        _buy("L2", slot=IN_FORCE_SLOT + 20),
    ]
    decisions = run_arm(fills, SNAPS, {}, POLICY, "follow")
    assert [d.reason for d in decisions] == ["below_min", "trigger", "not_first_buy"]


def test_creator_and_create_block_triggers_are_refused_only_when_the_create_was_known() -> None:
    f = _buy("L", slot=IN_FORCE_SLOT)
    own = {"M1": create("M1", "L2", IN_FORCE_SLOT - 100)}
    assert evaluate(_ctx(f, creates=own)).reason == "own_mint"
    block = {"M1": create("M1", "X", IN_FORCE_SLOT - 2)}
    assert evaluate(_ctx(f, creates=block)).reason == "create_block"
    unseen = {"M1": create("M1", "L2", IN_FORCE_SLOT + 50)}  # received after our decision
    assert evaluate(_ctx(f, creates=unseen)).bet is True


def test_entity_day_cap_and_mint_cooldown() -> None:
    fills = [_buy("L", slot=IN_FORCE_SLOT + 10 * i, mint=f"M{i}") for i in range(21)]
    reasons = [d.reason for d in run_arm(fills, SNAPS, {}, POLICY, "follow")]
    assert reasons.count("trigger") == 20
    assert reasons[-1] == "entity_day_cap"
    two = [_buy("L", mint="Z"), _buy("C", slot=IN_FORCE_SLOT + 100, mint="Z")]
    shared = Snapshot("s", D1, SNAPS[0].cut, SNAPS[0].published_at, SNAPS[0].entities,
                      {"e:L": RankRow("e:L", (), 1, True, SOL), "e:C": RankRow("e:C", (), 2, True, SOL)}, {})  # fmt: skip
    again = run_arm(two, (shared,), {}, POLICY, "follow")
    assert [d.reason for d in again] == ["trigger", "mint_cooldown"]


def test_a_trigger_received_after_the_theoretical_landing_is_refused() -> None:
    assert evaluate(_ctx(_buy("L", received_delay=1.7))).reason == "late_event"


def test_pairing_is_seeded_without_replacement_and_matches_the_strata() -> None:
    def trig(wallet: str, mint: str, slot: int, real: int, venue: str = "curve") -> Fill:
        state = (
            curve(30 * SOL + real, 900_000_000 * TOKEN, real_sol=real)
            if venue == "curve"
            else pool(real, 900 * TOKEN)
        )
        return fill(
            wallet=wallet,
            side="buy",
            slot=slot,
            sol=SOL // 5,
            atoms=TOKEN,
            mint=mint,
            reserves=state,
        )

    creates = {m: create(m, "x", 0) for m in ["F1", "F2", "C1", "C2", "C3", "C4"]}
    follows = [trig("L", "F1", 10_000, 5 * SOL), trig("L", "F2", 10_050, 5 * SOL)]
    controls = [
        trig("C", "F1", 10_010, 5 * SOL),  # same mint: never
        trig("C", "C1", 10_020, 5 * SOL),
        trig("C", "C2", 10_030, 5 * SOL),
        trig("C", "C3", 10_040, 50 * SOL),  # other tercile
        trig("C", "C4", 10_020, 5 * SOL, "pool"),  # other venue
    ]
    edges = (10 * SOL, 40 * SOL)
    pairs = pair_controls(follows, controls, creates=creates, tercile_edges=edges, seed=20261005)
    paired = [pairs[f.signature] for f in follows]
    assert None not in paired and len(set(paired)) == 2  # both paired, no control reused
    assert pairs[follows[0].signature] != controls[0].signature  # never the follow's own mint
    assert not set(paired) & {controls[3].signature, controls[4].signature}  # tercile, venue
    assert pairs == pair_controls(
        follows, controls, creates=creates, tercile_edges=edges, seed=20261005
    )
    lonely = pair_controls(follows[:1], controls[3:], creates=creates, tercile_edges=edges, seed=1)
    assert lonely[follows[0].signature] is None
    far = [trig("C", "C1", 10_000 + 200, 5 * SOL)]  # 80 s later: outside ±60 s
    assert (
        pair_controls(follows[:1], far, creates=creates, tercile_edges=edges, seed=1)[
            follows[0].signature
        ]
        is None
    )


def test_arrival_order_decides_the_first_buy_not_the_slot_order() -> None:
    # Astra must-fix 1: an earlier-slot buy received 100 s late must not turn the buy we
    # already acted on into "not_first_buy"
    late = _buy("L", slot=IN_FORCE_SLOT, received_delay=100.0)
    on_time = _buy("L", slot=IN_FORCE_SLOT + 20)
    decisions = run_arm([late, on_time], SNAPS, {}, POLICY, "follow")
    assert (decisions[0].fill, decisions[0].reason) == (on_time, "trigger")
    assert (decisions[1].fill, decisions[1].reason) == (late, "not_first_buy")


def test_control2_is_active_but_not_eligible_only_for_money_or_copyability() -> None:
    assert evaluate(_ctx(_buy("N2"), arm="control2")).bet is True
    assert evaluate(_ctx(_buy("N"), arm="control2")).reason == "not_in_arm"
    assert evaluate(_ctx(_buy("C"), arm="control2")).reason == "not_in_arm"


def test_pre_trade_real_sol_undoes_the_trade_in_the_right_direction() -> None:
    post = curve(40 * SOL, 900_000_000 * TOKEN, real_sol=10 * SOL)
    buy = fill(wallet="X", side="buy", slot=1, sol=SOL, atoms=TOKEN, reserves=post)
    sell = fill(wallet="X", side="sell", slot=1, sol=SOL, atoms=TOKEN, reserves=post)
    assert pre_trade_real_sol(buy) == 9 * SOL
    assert pre_trade_real_sol(sell) == 11 * SOL
    assert pre_trade_real_sol(replace(buy, reserves=pool(50 * SOL, 900 * TOKEN))) == 49 * SOL
