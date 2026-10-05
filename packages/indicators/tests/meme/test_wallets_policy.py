"""The copy policy (§3): entry at trigger + 5 slots, exit on the leader's >50 %
sale / stop at 50 % of cost / 60 min, each landing 5 slots after firing, costs,
R, censorship, incompleteness and contamination. Synthetic, hand-checkable.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_indicators.meme.wallets.params import FollowPolicy
from hunter_indicators.meme.wallets.policy import CopyOutcome, simulate_copy
from hunter_indicators.meme.wallets.pricing import MintTape, buy_atoms, sell_lamports
from hunter_indicators.meme.wallets.tape import Fill, Gap, Reserves
from packages.indicators.tests.meme.test_wallets_builders import SOL, TOKEN, curve, fill

pytestmark = pytest.mark.unit

POLICY = FollowPolicy()
BUDGET = 50_000_000
COSTS = 2 * 50_000 + 5_000
S100 = curve(40 * SOL, 800_000_000 * TOKEN)
S110 = curve(50 * SOL, 640_000_000 * TOKEN)
S120 = curve(45 * SOL, 711_111_111 * TOKEN)
S125 = curve(44 * SOL, 727_272_727 * TOKEN)


def _trigger(received_delay: float = 0.5) -> Fill:
    return fill(
        wallet="L",
        side="buy",
        slot=100,
        sol=SOL,
        atoms=25_000_000 * TOKEN,
        reserves=S100,
        received_delay=received_delay,
    )


def _atoms() -> int:
    atoms = buy_atoms(S100, BUDGET, fee_bps=125)
    assert atoms is not None
    return atoms


def _sell(state: Reserves, atoms: int) -> int:
    v = sell_lamports(state, atoms, fee_bps=125)
    assert v is not None
    return v


def _run(
    events: list[Fill],
    horizon: int = 20_000,
    gaps: tuple[Gap, ...] = (),
    trigger: Fill | None = None,
) -> CopyOutcome:
    trig = trigger or _trigger()
    return simulate_copy(
        trig,
        leader_wallets=frozenset({"L"}),
        tape=MintTape([trig, *events]),
        policy=POLICY,
        horizon_slot=horizon,
        gaps=gaps,
    )


def test_exit_after_the_leader_sells_more_than_half_lands_five_slots_later_at_the_worst_state() -> (
    None
):
    events = [
        fill(wallet="X", side="buy", slot=110, sol=SOL, atoms=TOKEN, reserves=S110),
        fill(wallet="L", side="sell", slot=120, sol=SOL, atoms=15_000_000 * TOKEN, reserves=S120),
        fill(wallet="Y", side="sell", slot=125, sol=SOL, atoms=TOKEN, reserves=S125),
    ]
    out = _run(events)
    atoms = _atoms()
    expected = min(_sell(S120, atoms), _sell(S125, atoms)) - BUDGET - COSTS
    assert (out.status, out.reason, out.entry_slot, out.exit_slot) == (
        "closed",
        "leader_sold",
        105,
        125,
    )
    assert out.entry_atoms == atoms
    assert out.net_lamports == expected
    assert out.r == Decimal(expected) / Decimal(25_000_000)


def test_selling_exactly_half_is_not_more_than_half() -> None:
    events = [
        fill(wallet="L", side="sell", slot=120, sol=SOL, atoms=12_500_000 * TOKEN, reserves=S120)
    ]
    assert _run(events).reason == "time_cap"


def test_stop_fires_when_our_sale_quote_falls_to_half_of_the_cost() -> None:
    dump = curve(31 * SOL, 1_500_000_000 * TOKEN)
    events = [fill(wallet="X", side="sell", slot=130, sol=9 * SOL, atoms=TOKEN, reserves=dump)]
    atoms = _atoms()
    assert _sell(dump, atoms) <= BUDGET // 2
    out = _run(events)
    assert (out.reason, out.exit_slot) == ("stop", 135)
    assert out.net_lamports == _sell(dump, atoms) - BUDGET - COSTS


def test_time_cap_is_sixty_minutes_after_the_entry_instant_then_the_delay() -> None:
    out = _run([])
    # entry lands at slot 105; +3600 s at 0.4 s/slot = slot 9105; lands at 9110 on the last state
    assert (out.reason, out.exit_slot) == ("time_cap", 9110)
    assert out.net_lamports == _sell(S100, _atoms()) - BUDGET - COSTS


def test_an_exit_landing_beyond_the_settled_horizon_is_incomplete_not_a_sale() -> None:
    out = _run([], horizon=9_000)
    assert out.status == "incomplete"
    assert out.net_lamports is None
    assert out.r is None


def test_migration_without_a_pool_is_censored_at_r_minus_one() -> None:
    done = curve(115 * SOL, 280_000_000 * TOKEN, real_sol=85 * SOL, complete=True)
    out = _run([fill(wallet="X", side="buy", slot=110, sol=SOL, atoms=TOKEN, reserves=done)])
    assert out.status == "censored"
    assert out.net_lamports == -25_000_000
    assert out.r == Decimal(-1)


def test_an_event_received_after_the_theoretical_landing_does_not_buy_retroactively() -> None:
    # landing instant = trigger block_time + 5 × 0.4 s = +2.0 s; decision = received + 0.4 s
    assert _run([], trigger=_trigger(received_delay=1.5)).status == "closed"
    late = _run([], trigger=_trigger(received_delay=1.7))
    assert (late.status, late.reason) == ("refused", "late_event")
    assert late.net_lamports is None


def test_a_leader_sale_before_our_landing_still_leaves_us_in_the_bet() -> None:
    events = [
        fill(wallet="L", side="sell", slot=101, sol=SOL, atoms=20_000_000 * TOKEN, reserves=S120)
    ]
    out = _run(events)
    assert (out.status, out.reason, out.exit_slot) == ("closed", "leader_sold", 106)


def test_a_late_received_exit_event_lands_when_we_could_have_reacted() -> None:
    events = [
        fill(
            wallet="L",
            side="sell",
            slot=120,
            sol=SOL,
            atoms=15_000_000 * TOKEN,
            reserves=S120,
            received_delay=5.0,
        )
    ]
    # block_time of slot 120 = +8 s from the trigger; received +13 s, decision +13.4 s → slot 100 + 34 = 134
    assert _run(events).exit_slot == 134


def test_a_gap_between_trigger_and_exit_contaminates_the_bet() -> None:
    assert _run([], gaps=(Gap(500, 600),)).contaminated is True
    assert _run([], gaps=(Gap(9_200, 9_300),)).contaminated is False


def test_costs_follow_the_policy_parameters() -> None:
    heavy = FollowPolicy(network_leg_lamports=100_000, ata_rent_lost_lamports=1_000)
    trig = _trigger()
    out = simulate_copy(
        trig,
        leader_wallets=frozenset({"L"}),
        tape=MintTape([trig]),
        policy=heavy,
        horizon_slot=20_000,
    )
    assert out.net_lamports == _sell(S100, _atoms()) - BUDGET - (200_000 + 5_000 + 1_000)


def test_the_leader_sold_exit_only_counts_sales_already_received() -> None:
    # Astra must-fix 2: 30 % sold at slot 110 but received 100 s late, 30 % at slot 120 on
    # time. At 120 only 30 % is known; > 50 % is known when the late one arrives (+100.4 s)
    events = [
        fill(
            wallet="L",
            side="sell",
            slot=110,
            sol=SOL,
            atoms=7_500_000 * TOKEN,
            reserves=S120,
            received_delay=100.0,
        ),
        fill(wallet="L", side="sell", slot=120, sol=SOL, atoms=7_500_000 * TOKEN, reserves=S120),
    ]
    out = _run(events)
    # slot 110 mined +4 s after the trigger, received +104 s, decided +104.4 s → slot 100 + 261
    assert (out.reason, out.exit_fire_slot, out.exit_slot) == ("leader_sold", 110, 361)


def test_a_sale_received_before_our_trigger_is_judged_with_the_trigger_counted() -> None:
    # Astra round 2: 40 % sold at slot 101, received before the trigger itself arrived.
    # Once we are in, 40 % of what was bought is not more than half: no leader exit.
    early_sale = fill(
        wallet="L", side="sell", slot=101, sol=SOL, atoms=10_000_000 * TOKEN, reserves=S120
    )
    out = _run([early_sale], trigger=_trigger(received_delay=1.5))
    assert (out.reason, out.exit_slot) == ("time_cap", 9110)


def test_an_earlier_slot_sale_received_after_the_trigger_can_fire_the_exit() -> None:
    # Astra round 2: 100 M bought at slot 80, sold at slot 90 but received only at +60 s;
    # with the 25 M trigger, 80 % is sold once it arrives → decide at 60.4 s → slot 151
    events = [
        fill(
            wallet="L", side="buy", slot=80, sol=SOL // 20, atoms=100_000_000 * TOKEN, reserves=S100
        ),
        fill(
            wallet="L",
            side="sell",
            slot=90,
            sol=SOL,
            atoms=100_000_000 * TOKEN,
            reserves=S100,
            received_delay=24.0,
        ),
    ]
    out = _run(events)
    assert (out.reason, out.exit_fire_slot, out.exit_slot) == ("leader_sold", 90, 151)


def test_a_tape_without_the_trigger_is_refused() -> None:
    trig = _trigger()
    with pytest.raises(ValueError, match="trigger"):
        simulate_copy(
            trig, leader_wallets=frozenset({"L"}), tape=MintTape([]), policy=POLICY, horizon_slot=1
        )


def test_a_same_slot_leader_sale_lands_one_slot_after_our_entry() -> None:
    sale = fill(
        wallet="L",
        side="sell",
        slot=100,
        sol=SOL,
        atoms=20_000_000 * TOKEN,
        reserves=S100,
        ordinal=1,
    )
    out = _run([sale])
    assert (out.reason, out.exit_fire_slot, out.exit_slot) == ("leader_sold", 100, 106)


def test_the_stop_fires_at_exactly_the_stop_fraction() -> None:
    dump = curve(31 * SOL, 1_500_000_000 * TOKEN)
    quote = _sell(dump, _atoms())
    events = [fill(wallet="X", side="sell", slot=130, sol=9 * SOL, atoms=TOKEN, reserves=dump)]
    trig = _trigger()
    tape = MintTape([trig, *events])
    exact = FollowPolicy(stop_fraction=Decimal(quote) / BUDGET)
    below = FollowPolicy(stop_fraction=(Decimal(quote) - 1) / BUDGET)

    def run(p: FollowPolicy) -> CopyOutcome:
        return simulate_copy(
            trig, leader_wallets=frozenset({"L"}), tape=tape, policy=p, horizon_slot=20_000
        )

    assert run(exact).reason == "stop"
    assert run(below).reason == "time_cap"


def test_a_dump_in_the_entry_slot_itself_is_not_a_stop_observation() -> None:
    dump = curve(31 * SOL, 1_500_000_000 * TOKEN)
    events = [fill(wallet="X", side="sell", slot=105, sol=9 * SOL, atoms=TOKEN, reserves=dump)]
    out = _run(events)
    assert out.entry_atoms == _atoms()  # bought at the worst (pre-dump) state
    assert out.reason == "time_cap"
