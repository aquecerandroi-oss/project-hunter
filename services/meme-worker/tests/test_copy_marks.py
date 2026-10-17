"""The safety stop (H-037, R2 fix B4): decided from the state that was read, before and independently of any
database write, and never from an old state arriving late. Plus the boundary of the stop itself."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_meme_worker.copy_bets import bet_state_of, build_entry, snapshot_of
from hunter_meme_worker.copy_book import CopyBook
from hunter_meme_worker.copy_events import CloseIntent, OpenIntent, leader_ref
from hunter_meme_worker.copy_marks import mark_pass, stop_hit
from hunter_meme_worker.copy_position import Live
from hunter_meme_worker.copy_stats import CopyStats

from .copy_fakes import Curve, FakeChain, FakeClock
from .copy_support import LEADER_A, MINT_1, T0, buy, make_spec
from .test_copy_exec_unit import _state  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit


def test_the_stop_fires_at_exactly_the_fraction_and_not_above_it() -> None:
    spent, fraction = Decimal("0.05"), Decimal("0.4")
    assert stop_hit(spent * fraction, spent, fraction)  # equal: the touch counts
    assert not stop_hit(spent * fraction + Decimal("0.0000000001"), spent, fraction)
    assert stop_hit(Decimal(0), spent, fraction)


def _open_copy(
    last_slot: int,
) -> tuple[Any, CopyBook, dict[str, Live], list[CloseIntent], CopyStats, FakeChain]:
    spec = make_spec(stop_fraction="0.5")
    book = CopyBook(spec, t0=T0 - timedelta(hours=1))
    intent = book.on_event(buy(at=T0), T0).jobs[0]
    assert isinstance(intent, OpenIntent)
    entry = build_entry(
        spec, snapshot_of(_state(100, T0 + timedelta(seconds=5))), intent, queued_at=T0, slot=100
    )
    state = bet_state_of(bet_id="b", rule_set_id="rs", mint=MINT_1, entry=entry, mayhem=False)
    live = {intent.key: Live(bet_id="b", state=state, leader=LEADER_A, last_slot=last_slot)}
    book.mark_open(intent.key, bet_id="b", entry_at=T0 + timedelta(seconds=5))
    clock = FakeClock(T0 + timedelta(seconds=20))
    chain = FakeChain(clock)
    chain.set(MINT_1, Curve(vsol="10", vtok="3200000000", real_sol="0.1"))  # the price collapsed
    return spec, book, live, [], CopyStats([LEADER_A]), chain


def _dead_database() -> Any:
    def factory() -> Any:
        raise RuntimeError("database down")

    return factory


async def test_a_database_error_on_the_mark_does_not_skip_the_stop() -> None:
    spec, book, live, submitted, stats, chain = _open_copy(last_slot=100)
    marked = await mark_pass(
        spec=spec,
        chain=chain,  # type: ignore[arg-type]
        session_factory=_dead_database(),
        book=book,
        live=live,
        submit=submitted.append,
        now=lambda: T0 + timedelta(seconds=21),
        stats=stats,
    )
    assert marked == 0 and stats.mark_write_failed == 1  # the write failed, and was counted
    assert (
        len(submitted) == 1 and submitted[0].reason == "safety_stop"
    )  # the stop did not wait for it


async def test_a_state_older_than_the_last_accepted_slot_is_ignored() -> None:
    spec, book, live, submitted, stats, chain = _open_copy(last_slot=5_000_000_000)
    chain.slot_override[MINT_1] = 1_000  # an old read arriving late: far below the copy's last slot
    await mark_pass(
        spec=spec,
        chain=chain,  # type: ignore[arg-type]
        session_factory=_dead_database(),
        book=book,
        live=live,
        submit=submitted.append,
        now=lambda: T0 + timedelta(seconds=21),
        stats=stats,
    )
    assert submitted == [] and stats.stale_states_ignored == 1
    assert next(iter(live.values())).last_slot == 5_000_000_000  # and it did not move the slot back


async def test_a_state_at_or_above_the_last_slot_moves_it_forward_and_can_stop() -> None:
    spec, book, live, submitted, stats, chain = _open_copy(last_slot=100)
    await mark_pass(
        spec=spec,
        chain=chain,  # type: ignore[arg-type]
        session_factory=_dead_database(),
        book=book,
        live=live,
        submit=submitted.append,
        now=lambda: T0 + timedelta(seconds=21),
        stats=stats,
    )
    assert next(iter(live.values())).last_slot > 100 and len(submitted) == 1
    assert leader_ref(buy(at=T0), "regra").wallet == LEADER_A
