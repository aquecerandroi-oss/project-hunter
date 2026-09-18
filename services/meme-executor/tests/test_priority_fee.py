"""T4.55 — the dynamic priority fee: p75 of the recent slots, floored, capped by
total cost, and the floor whenever the read fails. Pure selection first, then the
bounded reader (one RPC read per tick, 1,5 s deadline, 10 s cache)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from hunter_meme_executor.priority_fee import (
    DEFAULT_FLOOR_MICRO_LAMPORTS,
    DEFAULT_MAX_SOL,
    PriorityFeeChoice,
    PriorityFeeReader,
    cap_micro_lamports,
    choose_priority_fee,
    percentile_nearest_rank,
)

pytestmark = pytest.mark.unit

CU = 400_000
FLOOR = DEFAULT_FLOOR_MICRO_LAMPORTS
CAP = cap_micro_lamports(DEFAULT_MAX_SOL, CU)


# ----------------------------------------------------------------- selection


def test_the_cap_is_the_owners_max_sol_spread_over_the_compute_unit_limit() -> None:
    # 0,002 SOL = 2 000 000 lamports = 2 000 000 000 000 µL over 400 000 CU
    assert CAP == 5_000_000
    assert cap_micro_lamports(Decimal("0.0004"), 400_000) == 1_000_000
    assert cap_micro_lamports(Decimal("0.002"), 200_000) == 10_000_000


def test_p75_is_nearest_rank() -> None:
    assert percentile_nearest_rank([1, 2, 3, 4], 75) == 3
    assert percentile_nearest_rank([10], 75) == 10
    assert percentile_nearest_rank([5, 1, 9, 3, 7], 75) == 7  # sorted 1 3 5 7 9 → rank 4
    assert percentile_nearest_rank([0] * 100 + [1_000_000] * 10, 75) == 0


def test_p75_between_floor_and_cap_is_used_as_is() -> None:
    choice = choose_priority_fee([250_000] * 40, floor=FLOOR, cap=CAP)
    assert choice.micro_lamports == 250_000 and choice.source == "p75"
    assert choice.p75_micro_lamports == 250_000 and choice.samples == 40


def test_a_quiet_curve_gets_the_floor_not_zero() -> None:
    choice = choose_priority_fee([0, 0, 0, 1_000, 0], floor=FLOOR, cap=CAP)
    assert choice.micro_lamports == FLOOR and choice.source == "floor"
    assert choice.fee_sol(CU) == Decimal("0.00004")


def test_a_bidding_war_is_capped_by_total_cost() -> None:
    choice = choose_priority_fee([50_000_000] * 10, floor=FLOOR, cap=CAP)
    assert choice.micro_lamports == CAP and choice.source == "cap"
    assert choice.fee_sol(CU) == DEFAULT_MAX_SOL


def test_a_failed_read_uses_the_floor_and_says_so() -> None:
    choice = choose_priority_fee(None, floor=FLOOR, cap=CAP)
    assert choice.micro_lamports == FLOOR and choice.source == "floor:read_failed"
    assert choice.p75_micro_lamports is None and choice.samples == 0


def test_an_empty_read_uses_the_floor_and_says_so() -> None:
    choice = choose_priority_fee([], floor=FLOOR, cap=CAP)
    assert choice.micro_lamports == FLOOR and choice.source == "floor:no_samples"


def test_a_floor_above_the_cap_never_exceeds_the_cap() -> None:
    """The cap is the owner's ceiling; a floor the operator set too high loses."""
    choice = choose_priority_fee(None, floor=CAP * 2, cap=CAP)
    assert choice.micro_lamports == CAP and choice.source == "cap"
    choice = choose_priority_fee([1], floor=CAP * 2, cap=CAP)
    assert choice.micro_lamports == CAP and choice.source == "cap"


def test_the_choice_is_logged_with_every_number_that_made_it() -> None:
    choice = choose_priority_fee([250_000] * 4, floor=FLOOR, cap=CAP)
    assert choice.as_json(CU) == {
        "micro_lamports": 250_000,
        "source": "p75",
        "p75_micro_lamports": 250_000,
        "floor_micro_lamports": FLOOR,
        "cap_micro_lamports": CAP,
        "samples": 4,
        "fee_sol": "0.0001",
    }


def test_a_static_choice_reports_the_configured_price() -> None:
    choice = PriorityFeeChoice.static(10_000)
    assert choice.micro_lamports == 10_000 and choice.source == "static"
    assert choice.fee_sol(CU) == Decimal("0.000004")


# -------------------------------------------------------------------- reader


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t


class FakeRpc:
    def __init__(self, fees: list[int] | Exception, *, delay_s: float = 0.0) -> None:
        self.fees = fees
        self.delay_s = delay_s
        self.calls: list[list[Any]] = []

    def call(self, method: str, params: list[Any]) -> Any:
        assert method == "getRecentPrioritizationFees"
        self.calls.append(params)
        if self.delay_s:
            import time

            time.sleep(self.delay_s)
        if isinstance(self.fees, Exception):
            raise self.fees
        return [{"slot": 1_000 + i, "prioritizationFee": f} for i, f in enumerate(self.fees)]


def _reader(rpc: FakeRpc, clock: Clock, **kw: Any) -> PriorityFeeReader:
    return PriorityFeeReader(
        rpc, floor=FLOOR, max_sol=DEFAULT_MAX_SOL, monotonic=clock.monotonic, **kw
    )


ADDRESSES = ("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "curve111")


def test_the_reader_asks_for_the_program_and_the_curve_and_uses_the_p75() -> None:
    clock = Clock()
    rpc = FakeRpc([0, 100_000, 300_000, 200_000])
    choice = asyncio.run(_reader(rpc, clock).choose(ADDRESSES, compute_unit_limit=CU))
    assert rpc.calls == [[list(ADDRESSES)]]
    assert choice.micro_lamports == 200_000 and choice.source == "p75"  # rank 3 of 4


def test_the_reader_caches_for_10s_then_reads_again() -> None:
    clock = Clock()
    rpc = FakeRpc([300_000] * 4)
    reader = _reader(rpc, clock)
    asyncio.run(reader.choose(ADDRESSES, compute_unit_limit=CU))
    clock.t = 9.9
    cached = asyncio.run(reader.choose(ADDRESSES, compute_unit_limit=CU))
    assert len(rpc.calls) == 1 and cached.source == "p75"
    clock.t = 10.1
    asyncio.run(reader.choose(ADDRESSES, compute_unit_limit=CU))
    assert len(rpc.calls) == 2


def test_the_reader_makes_at_most_one_read_per_tick() -> None:
    """A second key (another mint) inside the same second does not cost a
    second RPC call: it gets the floor by name, not a wait."""
    clock = Clock()
    rpc = FakeRpc([300_000] * 4)
    reader = _reader(rpc, clock)
    asyncio.run(reader.choose(ADDRESSES, compute_unit_limit=CU))
    other = asyncio.run(reader.choose(("prog", "curve222"), compute_unit_limit=CU))
    assert len(rpc.calls) == 1 and other.source == "floor:throttled"
    clock.t = 1.5
    again = asyncio.run(reader.choose(("prog", "curve222"), compute_unit_limit=CU))
    assert len(rpc.calls) == 2 and again.source == "p75"


def test_a_read_error_is_the_floor_and_is_not_cached_as_truth() -> None:
    clock = Clock()
    rpc = FakeRpc(RuntimeError("boom"))
    reader = _reader(rpc, clock)
    choice = asyncio.run(reader.choose(ADDRESSES, compute_unit_limit=CU))
    assert choice.source == "floor:read_failed" and choice.micro_lamports == FLOOR
    assert reader.last_error == "RuntimeError"
    clock.t = 2.0
    rpc.fees = [400_000] * 3
    healed = asyncio.run(reader.choose(ADDRESSES, compute_unit_limit=CU))
    assert healed.source == "p75" and healed.micro_lamports == 400_000


def test_a_slow_read_is_cut_at_the_deadline_and_is_the_floor() -> None:
    clock = Clock()
    rpc = FakeRpc([900_000] * 3, delay_s=0.3)
    reader = _reader(rpc, clock, read_timeout_s=0.05)
    choice = asyncio.run(reader.choose(ADDRESSES, compute_unit_limit=CU))
    assert choice.source == "floor:read_failed" and reader.last_error == "TimeoutError"


def test_the_window_keeps_only_the_most_recent_slots() -> None:
    clock = Clock()
    # 100 old slots at 5 000 000, then the newest 50 at 200 000: only the newest count
    rpc = FakeRpc([5_000_000] * 100 + [200_000] * 50)
    reader = _reader(rpc, clock, window_slots=50)
    choice = asyncio.run(reader.choose(ADDRESSES, compute_unit_limit=CU))
    assert choice.micro_lamports == 200_000 and choice.samples == 50


def test_a_malformed_reply_is_the_floor() -> None:
    clock = Clock()
    rpc = FakeRpc([])
    rpc.call = lambda method, params: {"not": "a list"}  # type: ignore[method-assign]
    choice = asyncio.run(_reader(rpc, clock).choose(ADDRESSES, compute_unit_limit=CU))
    assert choice.source == "floor:read_failed"
