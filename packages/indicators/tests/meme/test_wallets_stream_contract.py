"""The contract of wave 1c-bis is refused by name, never published around (Astra).

Synthetic fixtures (not data). Each violation would silently break the equivalence with the batch
snapshot, so the bounded engine stops with a :class:`ContractViolation` naming the reason:

- ``late_beyond_seal`` (P1) — an event mined before the window start, received after the night
  that sealed its block day;
- ``received_before_mined`` (P2);
- ``slot_time_inconsistent`` (P3) — two times in one slot, or time going back with the slot;
- ``carry_mismatch`` — a carry of another window start (state lost or replayed out of order);
- ``lot_after_origin`` — a preserved lot opened after the campaign origin.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from hunter_indicators.meme.wallets.carry import ContractViolation, MintCarry, initial_carry
from hunter_indicators.meme.wallets.carry_codec import carry_from_json, carry_to_json
from hunter_indicators.meme.wallets.lots import Lot
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.ranking import cut_of
from hunter_indicators.meme.wallets.stream import (
    MintWindow,
    StreamInputs,
    shared_signatures,
    stream_snapshot,
)
from hunter_indicators.meme.wallets.tape import Fill
from packages.indicators.tests.meme.stream_harness import (
    World,
    mint_windows,
    reference_snapshot,
    streamed_snapshots,
)
from packages.indicators.tests.meme.stream_world import random_world
from packages.indicators.tests.meme.test_wallets_builders import SOL, T0, TOKEN, fill

pytestmark = pytest.mark.unit

PARAMS = RankingParams(window_days=2)
DAY0 = (T0 + timedelta(days=2)).date()


def _reason(world: World, days: int = 1) -> str:
    with pytest.raises(ContractViolation) as caught:
        streamed_snapshots(world, [DAY0 + timedelta(days=k) for k in range(days)], params=PARAMS)
    return caught.value.reason


def _buy(
    slot: int, *, received_delay: float = 0.5, t: float | None = None, mint: str = "MINT"
) -> Fill:
    return fill(wallet="A", side="buy", slot=slot, sol=SOL, atoms=TOKEN, mint=mint, t=t,
                received_delay=received_delay)  # fmt: skip


def test_an_event_received_after_its_day_was_sealed_is_refused() -> None:
    # mined on day 0, received 2.5 days later: the night of day 2 sealed day 0 with what had
    # arrived by then, so the night of day 3 cannot take it into the lots any more
    late = _buy(1_000, received_delay=2.5 * 86_400)
    ok = _buy(2_000)
    assert _reason(World(T0, (ok, late)), days=2) == "late_beyond_seal"
    # 1.5 days late is inside the seal: no refusal
    streamed_snapshots(World(T0, (ok, _buy(1_000, received_delay=1.5 * 86_400))),
                       [DAY0, DAY0 + timedelta(days=1)], params=PARAMS)  # fmt: skip


def test_an_event_mined_before_the_origin_can_never_be_sealed() -> None:
    before = replace(
        _buy(10), block_time=T0 - timedelta(seconds=5), received_at=T0 + timedelta(seconds=1)
    )
    assert _reason(World(T0, (before,))) == "late_beyond_seal"


def test_reception_before_mining_and_two_times_in_one_slot_are_refused() -> None:
    early = _buy(500, received_delay=-3.0)
    assert _reason(World(T0, (early,))) == "received_before_mined"
    a, b = _buy(500), _buy(500, t=500 * 0.4 + 7)
    assert _reason(World(T0, (a, b))) == "slot_time_inconsistent"
    back = _buy(600, t=100.0)
    assert _reason(World(T0, (_buy(500), back))) == "slot_time_inconsistent"


def test_a_carry_of_another_window_start_is_refused() -> None:
    carry, _ = initial_carry(T0, window_days=2)
    inputs = StreamInputs(carry=carry, mints=lambda: iter(()), shared_signatures=frozenset())
    with pytest.raises(ContractViolation, match="carry_mismatch"):
        stream_snapshot(inputs, DAY0 + timedelta(days=1), params=PARAMS)
    stream_snapshot(inputs, DAY0, params=PARAMS)  # its own night is fine
    with pytest.raises(ContractViolation, match="carry_mismatch"):
        stream_snapshot(inputs, DAY0)  # same start, other window length


def test_a_preserved_lot_opened_after_the_origin_is_refused() -> None:
    lot = Lot("A", "M", TOKEN, None, 5, T0 + timedelta(seconds=2))
    with pytest.raises(ContractViolation, match="lot_after_origin"):
        initial_carry(T0, (lot,))


def test_an_event_of_another_mint_in_a_window_is_a_caller_error() -> None:
    carry, _ = initial_carry(T0, window_days=2)
    stray = MintWindow(MintCarry("M"), (_buy(5, mint="X"),))
    with pytest.raises(ValueError, match="another mint"):
        stream_snapshot(
            StreamInputs(carry=carry, mints=lambda: iter((stray,)), shared_signatures=frozenset()),
            DAY0,
            params=PARAMS,
        )


def test_the_carry_survives_a_json_round_trip_bit_for_bit() -> None:
    world, _ = random_world(7, window_days=2, days=4)
    carry, mints = initial_carry(world.origin, world.preserved, window_days=2)
    windows = mint_windows(world, {m.mint: m for m in mints}, cut_of(DAY0) - timedelta(days=2))
    result = stream_snapshot(StreamInputs(carry=carry, mints=lambda: iter(windows), links=world.links,
                                          shared_signatures=shared_signatures(world.fills),
                                          gaps=world.gaps), DAY0, params=PARAMS)  # fmt: skip
    dead = MintCarry("DEAD", lots=(Lot("Z", "DEAD", TOKEN, None, -1, T0 - timedelta(hours=1)),))
    mints_out = (*result.mint_carries, dead)
    text = carry_to_json(result.carry, mints_out)
    back_carry, back_mints = carry_from_json(text)
    assert back_carry == result.carry
    assert back_mints == mints_out
    assert any(m.lots for m in back_mints) and any(m.frontier for m in back_mints)
    assert any(
        lot.cost_lamports is None for m in back_mints for lot in m.lots
    )  # unknown stays unknown
    assert carry_to_json(back_carry, back_mints) == text


def test_a_settle_horizon_reaching_before_the_window_start_is_refused() -> None:
    # Astra (diff review): with settle_seconds past the window start the carried highest slot
    # may not be settled yet, and the horizon would differ from the batch's — outside the proof
    carry, _ = initial_carry(T0, window_days=2)
    wide = RankingParams(window_days=2, settle_seconds=2 * 86_400 + 1)
    inputs = StreamInputs(carry=carry, mints=lambda: iter(()), shared_signatures=frozenset())
    with pytest.raises(ContractViolation, match="settle_beyond_window"):
        stream_snapshot(inputs, DAY0, params=wide)
    stream_snapshot(inputs, DAY0, params=RankingParams(window_days=2, settle_seconds=2 * 86_400))


def test_next_carries_can_be_emitted_one_mint_at_a_time() -> None:
    # Astra (diff review): collecting every next carry keeps the whole campaign resident
    world, _ = random_world(3, window_days=2, days=3)
    carry, mints = initial_carry(world.origin, world.preserved, window_days=2)
    windows = mint_windows(world, {m.mint: m for m in mints}, cut_of(DAY0) - timedelta(days=2))
    inputs = StreamInputs(
        carry=carry,
        mints=lambda: iter(windows),
        links=world.links,
        shared_signatures=shared_signatures(world.fills),
    )
    collected = stream_snapshot(inputs, DAY0, params=PARAMS)
    sink: list[MintCarry] = []
    emitted = stream_snapshot(inputs, DAY0, params=PARAMS, emit=sink.append)
    assert emitted.mint_carries == ()
    assert tuple(sink) == collected.mint_carries and sink
    assert emitted.snapshot == collected.snapshot and emitted.carry == collected.carry


# --- Input validation (code-reviewer + Astra review of the diff, 06/10). These call StreamInputs
# --- directly: the harness builds clean sources and would normalize each defect away.


def _two_mint_world() -> World:
    """One tx buys X (ordinal 1) and Y (ordinal 0); X is sold later: the fee belongs to Y."""
    return World(T0, (
        fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=10 * TOKEN, mint="X", signature="tx", ordinal=1, fee_bps=0),
        fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=10 * TOKEN, mint="Y", signature="tx", ordinal=0, fee_bps=0),
        fill(wallet="A", side="sell", slot=20, sol=2 * SOL, atoms=10 * TOKEN, mint="X", fee_bps=0),
    ))  # fmt: skip


def _night(world: World, shared: frozenset[str], repeat: int = 1) -> StreamInputs:
    carry, mints = initial_carry(world.origin, world.preserved, window_days=2)
    windows = mint_windows(world, {m.mint: m for m in mints}, cut_of(DAY0) - timedelta(days=2))
    return StreamInputs(carry=carry, mints=lambda: iter(windows * repeat), shared_signatures=shared)


def test_a_window_fill_received_before_the_window_start_is_refused() -> None:
    # Astra: a source handing back day-0 events on the next night would double-count them in
    # the carried leader totals (and fire a leader exit that does not exist)
    world = _two_mint_world()
    first = stream_snapshot(_night(world, frozenset({"tx"})), DAY0, params=PARAMS)
    carry_x = next(m for m in first.mint_carries if m.mint == "X")
    old = MintWindow(carry_x, tuple(f for f in world.fills if f.mint == "X"))
    inputs = StreamInputs(
        carry=first.carry, mints=lambda: iter((old,)), shared_signatures=frozenset({"tx"})
    )
    with pytest.raises(ContractViolation, match="received_before_window"):
        stream_snapshot(inputs, DAY0 + timedelta(days=1), params=PARAMS)


def test_a_mint_repeated_in_the_source_is_refused() -> None:
    inputs = _night(_two_mint_world(), frozenset({"tx"}), repeat=2)
    with pytest.raises(ContractViolation, match="repeated_mint"):
        stream_snapshot(inputs, DAY0, params=PARAMS)


def test_omitting_a_shared_signature_charges_the_fee_twice_silently() -> None:
    # Documents an EXTERNAL guarantee: completeness of shared_signatures belongs to storage (it
    # cannot be checked one mint at a time). Omitted, the X lot pays the 5 000 lamports again.
    world = _two_mint_world()
    reference = reference_snapshot(world, DAY0, params=PARAMS)
    right = stream_snapshot(_night(world, shared_signatures(world.fills)), DAY0, params=PARAMS)
    wrong = stream_snapshot(_night(world, frozenset()), DAY0, params=PARAMS)
    assert right.snapshot == reference
    ref_w, wrong_w = reference.rows["A"].metrics, wrong.snapshot.rows["A"].metrics
    assert ref_w is not None and wrong_w is not None
    assert ref_w.w_pnl_lamports - wrong_w.w_pnl_lamports == 5_000


def test_shared_signatures_has_no_default() -> None:
    carry, _ = initial_carry(T0, window_days=2)
    with pytest.raises(TypeError, match="shared_signatures"):
        StreamInputs(carry=carry, mints=lambda: iter(()))  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]
