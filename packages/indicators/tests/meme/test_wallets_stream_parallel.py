"""CPU plan step 3 (06/10/2026): whole mints in worker processes, exact reduction, rules unchanged.

The global passes (survey, entities, bets under the per-entity daily cap, fee seeds) stay on the
coordinator; workers replay whole mints and hand back partial tallies and the next carries; the
coordinator reduces them exactly. Proof, on synthetic fixtures (not data):

- the frozen digests of commit ``84704fa1`` (``wallets_golden.json``) come out of the parallel
  engine for 1, 2 and 4 workers;
- the reduction is order-free: per-mint partials reduced in many random orders publish the serial
  snapshot, and real runs with a random per-mint delay (shuffled completion) equal the serial one;
- a failure in a worker reaches the caller (named refusals intact) and leaves no child process.
"""

from __future__ import annotations

import json
import multiprocessing
import pickle
import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from hunter_indicators.meme.wallets.carry import ContractViolation, MintCarry, initial_carry
from hunter_indicators.meme.wallets.carry_codec import carry_to_json
from hunter_indicators.meme.wallets.leakage import fingerprint
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.ranking import cut_of
from hunter_indicators.meme.wallets.stream import (
    MintWindow,
    StreamInputs,
    StreamResult,
    finish_night,
    plan_night,
    replay_window,
    shared_signatures,
    stream_snapshot,
)
from hunter_indicators.meme.wallets.stream_mint import Tallies, replay_mint
from hunter_indicators.meme.wallets.stream_parallel import (
    stream_snapshot_parallel,
)
from hunter_indicators.meme.wallets.stream_source import prepared
from packages.indicators.tests.meme.stream_fetch import (
    ByName,
    Failing,
    Rendezvous,
    Sleepy,
    Tampered,
    by_name,
)
from packages.indicators.tests.meme.stream_harness import World, mint_windows
from packages.indicators.tests.meme.test_wallets_builders import T0
from packages.indicators.tests.meme.wallets_golden import (
    DAYS,
    GOLDEN,
    SMALL,
    Engine,
    dense_world,
    night_worlds,
)
from packages.indicators.tests.meme.wallets_golden import (
    _nights as golden_nights,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = pytest.mark.unit


def _parallel(workers: int) -> Engine:
    def run(inputs: StreamInputs, windows: list[MintWindow], day: date,
            params: RankingParams) -> StreamResult:  # fmt: skip
        return stream_snapshot_parallel(inputs, day, params=params, workers=workers,
                                        fetch=ByName(by_name(windows)))  # fmt: skip

    return run


def _last_night(world: World, days: list[date]) -> tuple[StreamInputs, list[MintWindow], date]:
    """The inputs of the last of ``days`` (earlier nights streamed serially from the origin)."""
    carry, first = initial_carry(world.origin, world.preserved, window_days=SMALL.window_days)
    mints = {m.mint: m for m in first}
    shared = shared_signatures(world.fills)

    def inputs_of(day: date) -> tuple[StreamInputs, list[MintWindow]]:
        windows = mint_windows(world, mints, cut_of(day) - timedelta(days=SMALL.window_days))
        return StreamInputs(carry, lambda w=windows: iter(w), shared, world.links, world.funders,
                            world.gaps), windows  # fmt: skip

    for day in days[:-1]:
        result = stream_snapshot(inputs_of(day)[0], day, params=SMALL)
        carry, mints = result.carry, {m.mint: m for m in result.mint_carries}
    inputs, windows = inputs_of(days[-1])
    return inputs, windows, days[-1]


def _same(a: StreamResult, b: StreamResult) -> None:
    assert fingerprint(a.snapshot) == fingerprint(b.snapshot)
    assert a.snapshot == b.snapshot
    assert carry_to_json(a.carry, a.mint_carries) == carry_to_json(b.carry, b.mint_carries)


@pytest.mark.parametrize(
    ("workers", "keys"),
    [
        (2, ("random0", "random1", "random2", "random3", "dense_nights")),  # every frozen night
        (1, ("dense_nights",)),
        (4, ("dense_nights", "random2")),  # more workers than mints on some nights
    ],
)
def test_the_parallel_engine_reproduces_the_frozen_reference(
    workers: int, keys: tuple[str, ...]
) -> None:
    """Every night of each world runs the parallel engine end to end (its carry feeds the next).
    A pool per night costs ~2–4 s of spawn and imports here, hence the subsets for 1 and 4."""
    frozen = json.loads(GOLDEN.read_text(encoding="utf-8"))
    worlds = night_worlds()
    for key in keys:
        world, days = worlds[key]
        assert golden_nights(world, days, SMALL, engine=_parallel(workers)) == frozen[key], key


def _canon(tallies: Tallies) -> dict[str, object]:
    """Every reduced field exactly; the holds as a multiset (a merge changes their order only)."""
    books = {e: (t.days, t.episodes, t.creator, t.create_block, tuple(t.daily),
                 t.closed_non_neutral, frozenset(t.mints), frozenset(t.active_dates), t.largest,
                 tuple(sorted(h.hex() for h in t.holds)), t.incomplete, t.contaminated,
                 t.sold_atoms, t.unmatched_atoms) for e, t in tallies.books.items()}  # fmt: skip
    return {"books": books, "copies": dict(tallies.copies), "w_pnl": dict(tallies.w_pnl)}


@pytest.mark.parametrize("world_key", ["dense_nights", "random0", "random3"])
def test_partials_reduced_in_any_order_publish_the_serial_snapshot(world_key: str) -> None:
    world, days = night_worlds()[world_key]
    inputs, windows, day = _last_night(world, days)
    serial = stream_snapshot(inputs, day, params=SMALL)
    plan = plan_night(inputs, day, params=SMALL)
    direct = Tallies()  # the serial fold, one tally for every mint
    for w in windows:
        fills = prepared(w, plan.carry.sealed_until, plan.base.start, plan.base.cut)
        replay_mint(w.carry, fills, w.creates, plan.mint_night(w.carry.mint), direct)
    parts = [replay_window(plan, w) for w in windows]
    assert len(parts) >= 3
    rng = random.Random(f"perm:{world_key}")
    orders = [parts[::-1]] + [rng.sample(parts, len(parts)) for _ in range(49)]
    for order in orders:
        tallies = Tallies()
        for part in order:
            tallies.merge(pickle.loads(pickle.dumps(part.tallies)))  # noqa: S301 — our own bytes, as a worker hands them back
        assert _canon(tallies) == _canon(direct)
        carries = tuple(p.carry for p in parts if p.carry is not None)
        _same(finish_night(plan, tallies, carries), serial)


def test_a_failing_emit_stops_the_night_and_leaves_no_process() -> None:
    inputs, windows, day = _last_night(dense_world(7), DAYS[:3])

    def broken(_carry: MintCarry) -> None:
        raise OSError("carry store unavailable (test)")

    with pytest.raises(OSError, match="carry store"):
        stream_snapshot_parallel(inputs, day, params=SMALL, workers=2,
                                 fetch=ByName(by_name(windows)), emit=broken)  # fmt: skip
    assert multiprocessing.active_children() == []


@pytest.mark.parametrize("seed", range(4))
def test_a_shuffled_completion_order_changes_nothing(seed: int) -> None:
    inputs, windows, day = _last_night(dense_world(7), DAYS[:3])
    serial = stream_snapshot(inputs, day, params=SMALL)
    emitted: list[MintCarry] = []
    result = stream_snapshot_parallel(inputs, day, params=SMALL, workers=3,
                                      fetch=Sleepy(by_name(windows), seed), emit=emitted.append)  # fmt: skip
    assert result.mint_carries == ()
    assert sorted(emitted, key=lambda m: m.mint) == sorted(
        serial.mint_carries, key=lambda m: m.mint
    )
    _same(StreamResult(result.snapshot, result.carry, serial.mint_carries), serial)


def test_without_emit_the_carries_come_in_source_order() -> None:
    inputs, windows, day = _last_night(dense_world(7), DAYS[:3])
    serial = stream_snapshot(inputs, day, params=SMALL)
    result = stream_snapshot_parallel(inputs, day, params=SMALL, workers=2,
                                      fetch=Sleepy(by_name(windows), 9))  # fmt: skip
    _same(result, serial)
    assert result.mint_carries == serial.mint_carries


def test_the_largest_mint_is_scheduled_first() -> None:
    inputs, _windows, day = _last_night(dense_world(7), DAYS[:3])
    plan = plan_night(inputs, day, params=SMALL)
    schedule = plan.schedule()
    assert sorted(schedule) == sorted(plan.order)
    costs = [plan.cost(m) for m in schedule]
    assert costs == sorted(costs, reverse=True)
    assert schedule[0] == max(plan.order, key=plan.cost)


@pytest.mark.parametrize("violation", [False, True])
def test_a_worker_failure_reaches_the_caller_and_leaves_no_process(violation: bool) -> None:
    inputs, windows, day = _last_night(dense_world(7), DAYS[:3])
    fetch = Failing(by_name(windows), bad="H", violation=violation)
    expected = ContractViolation if violation else RuntimeError
    with pytest.raises(expected) as err:
        stream_snapshot_parallel(inputs, day, params=SMALL, workers=2, fetch=fetch)
    if violation:
        assert isinstance(err.value, ContractViolation)
        assert err.value.reason == "slot_time_inconsistent"
    assert multiprocessing.active_children() == []


def test_a_fetched_window_unlike_the_surveyed_one_is_refused() -> None:
    inputs, windows, day = _last_night(dense_world(7), DAYS[:3])
    with pytest.raises(ContractViolation) as err:
        stream_snapshot_parallel(inputs, day, params=SMALL, workers=2,
                                 fetch=Tampered(by_name(windows), bad="X"))  # fmt: skip
    assert err.value.reason == "fetch_mismatch"
    assert multiprocessing.active_children() == []


def test_workers_must_be_positive() -> None:
    inputs, windows, day = _last_night(dense_world(7), DAYS[:3])
    with pytest.raises(ValueError, match="workers"):
        stream_snapshot_parallel(inputs, day, params=SMALL, workers=0,
                                 fetch=ByName(by_name(windows)))  # fmt: skip


def test_an_empty_source_needs_no_pool() -> None:
    world = World(origin=T0, fills=())
    inputs, windows, day = _last_night(world, DAYS[:1])
    assert windows == []
    result = stream_snapshot_parallel(inputs, day, params=SMALL, workers=2, fetch=ByName({}))
    _same(result, stream_snapshot(inputs, day, params=SMALL))


def test_two_workers_really_run_at_once_and_finish_out_of_order(tmp_path: Path) -> None:
    """Code review, step 3: the random delays never made two pids run (one ran every mint).
    Here both workers must register before any load proceeds, and the first-scheduled mint is
    held until the coordinator emitted another mint's carry: concurrency and an inverted
    completion are forced, not hoped for."""
    inputs, windows, day = _last_night(dense_world(7), DAYS[:3])
    serial = stream_snapshot(inputs, day, params=SMALL)
    held = plan_night(inputs, day, params=SMALL).schedule()[0]
    emitted: list[str] = []

    def emit(carry: MintCarry) -> None:
        emitted.append(carry.mint)
        (tmp_path / f"emitted-{carry.mint}").touch()

    result = stream_snapshot_parallel(inputs, day, params=SMALL, workers=2, emit=emit,
                                      fetch=Rendezvous(by_name(windows), str(tmp_path), held))  # fmt: skip
    assert len(list(tmp_path.glob("pid-*"))) == 2
    assert held in emitted and emitted[0] != held  # dispatched first, completed later
    assert sorted(emitted) == sorted(m.mint for m in serial.mint_carries)
    _same(StreamResult(result.snapshot, result.carry, serial.mint_carries), serial)
