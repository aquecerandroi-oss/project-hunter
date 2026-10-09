"""Copy-trade pilot (H-037): the combinator (NATS first, the chain confirms) against scripted fakes."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Collection
from datetime import UTC, datetime, timedelta

import pytest

from hunter_exchanges.pumpfun.leader_events import LeaderConfirmation, LeaderEvent, LeaderGap
from hunter_exchanges.pumpfun.leader_source import CombinedLeaderSource
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats

pytestmark = pytest.mark.unit

W, W2, M = "WalletA", "WalletB", "MintA"
T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
Item = LeaderEvent | LeaderGap | LeaderConfirmation


def ev(
    source: str = "nats",
    *,
    sig: str = "s1",
    wallet: str = W,
    mint: str = M,
    delta: int = 1_000_000,
    sol: int | None = None,
    at: datetime = T0,
) -> LeaderEvent:
    chain = source != "nats"
    return LeaderEvent(
        wallet=wallet,
        mint=mint,
        side="buy" if delta > 0 else "sell",
        token_delta_atoms=delta,
        sol_delta_lamports=sol,
        position_after_atoms=abs(delta),
        signature=sig,
        slot=10,
        block_time=T0 if chain else None,
        first_seen_at=at,
        fields_complete_at=at,
        source="chain" if chain else "nats",
        confirmed=chain,
        kind="swap" if chain else "unknown",
    )


def conf(
    preview: LeaderEvent, status: str = "confirmed", reason: str | None = None, *, at: datetime
) -> LeaderConfirmation:
    return LeaderConfirmation(
        wallet=preview.wallet,
        mint=preview.mint,
        signature=preview.signature,
        slot=preview.slot,
        status=status,  # type: ignore[arg-type]
        reason=reason,
        confirmed_at=at,
        block_time=T0,
    )


class FakeSource:
    """A scripted LeaderSource: whatever the test pushes comes out of ``stream``."""

    def __init__(self, clock: Clock) -> None:
        self.inbox: asyncio.Queue[Item] = asyncio.Queue()
        self.wallets: Collection[str] = ()
        self.closed = False
        self.confirms: list[LeaderEvent] = []
        self.gate: asyncio.Event | None = None
        self.answers: list[LeaderConfirmation | BaseException] = []
        self.clock = clock

    def push(self, item: Item) -> None:
        self.inbox.put_nowait(item)

    async def stream(self, wallets: Collection[str]) -> AsyncIterator[Item]:
        self.wallets = wallets
        try:
            while True:
                yield await self.inbox.get()
        finally:
            self.closed = True

    async def confirm(self, event: LeaderEvent) -> LeaderConfirmation:
        self.confirms.append(event)
        if self.gate is not None:
            await self.gate.wait()
        answer = self.answers.pop(0) if self.answers else None
        if isinstance(answer, BaseException):
            raise answer
        return answer or conf(event, at=self.clock())


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def build() -> tuple[CombinedLeaderSource, FakeSource, FakeSource, Clock, LeaderSourceStats]:
    clock, stats = Clock(), LeaderSourceStats()
    nats, chain = FakeSource(clock), FakeSource(clock)
    src = CombinedLeaderSource(nats=nats, chain=chain, stats=stats, wall=clock)
    return src, nats, chain, clock, stats


class Reader:
    """Reads an async generator without ever cancelling it (a timed-out ``__anext__`` would kill it)."""

    def __init__(self, agen: AsyncIterator[Item]) -> None:
        self.agen = agen
        self.task: asyncio.Future[Item] | None = None

    def _pending(self) -> asyncio.Future[Item]:
        if self.task is None:
            self.task = asyncio.ensure_future(self.agen.__anext__())
        return self.task

    async def __anext__(self) -> Item:
        done, _ = await asyncio.wait({self._pending()}, timeout=2)
        if not done:
            raise TimeoutError("nothing emitted")
        task, self.task = self.task, None
        assert task is not None
        return task.result()

    async def quiet(self) -> None:
        done, _ = await asyncio.wait({self._pending()}, timeout=0.1)
        assert not done, f"unexpected emission: {self.task.result() if self.task else None}"

    async def aclose(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await self.task
        await self.agen.aclose()  # type: ignore[attr-defined]


async def take(agen: Reader, n: int = 1) -> list[Item]:
    return [await agen.__anext__() for _ in range(n)]


# --------------------------------------------------------------------------- events and confirmations
async def test_the_provisional_event_goes_out_at_once_and_the_confirmation_follows_the_chain() -> (
    None
):
    src, nats, chain, clock, stats = build()
    chain.gate = asyncio.Event()
    agen = Reader(src.stream([W, W2]))
    nats.push(ev("nats", delta=3_000_000))
    (preview,) = await take(agen)  # while the chain check is still running
    assert isinstance(preview, LeaderEvent) and (preview.source, preview.confirmed) == (
        "nats",
        False,
    )
    assert sorted(nats.wallets) == sorted(chain.wallets) == [W, W2]
    clock.now = T0 + timedelta(milliseconds=420)
    chain.gate.set()
    (done,) = await take(agen)
    assert isinstance(done, LeaderConfirmation) and done.status == "confirmed"
    assert (done.wallet, done.signature, done.mint) == (
        preview.wallet,
        preview.signature,
        preview.mint,
    )
    assert done.confirmed_at == clock.now  # local reception of the result
    snap = stats.snapshot()["nats_to_confirm"]
    assert snap["n"] == 1 and snap["p50_ms"] == 420.0
    await agen.aclose()


async def test_every_confirmation_state_reaches_the_consumer_and_only_confirmed_is_timed() -> None:
    src, nats, chain, clock, stats = build()
    agen = Reader(src.stream([W]))
    preview = ev("nats", sig="a")
    for status, reason in (
        ("divergent", "token_delta"),
        ("failed_tx", "tx_failed"),
        ("not_found", "not_found"),
        ("rpc_error", "rate_limited"),
    ):
        chain.answers.append(conf(preview, status, reason, at=clock.now))
    for sig in "abcd":
        nats.push(ev("nats", sig=sig))
    got = await take(agen, 8)
    confirmations = [g for g in got if isinstance(g, LeaderConfirmation)]
    assert sorted(c.status for c in confirmations) == [
        "divergent",
        "failed_tx",
        "not_found",
        "rpc_error",
    ]
    assert stats.snapshot()["nats_to_confirm"]["n"] == 0
    await agen.aclose()


async def test_a_trade_only_the_chain_saw_is_emitted_confirmed_and_a_late_nats_copy_is_dropped() -> (
    None
):
    src, nats, chain, _, stats = build()
    agen = Reader(src.stream([W]))
    chain.push(ev("chain"))
    (e,) = await take(agen)
    assert isinstance(e, LeaderEvent) and e.confirmed and e.source == "chain"
    assert stats.counters["chain_only"] == 1
    nats.push(ev("nats"))
    await agen.quiet()
    assert stats.counters["nats_after_chain"] == 1 and chain.confirms == []
    await agen.aclose()


async def test_when_the_logs_path_sees_the_same_trade_the_pending_confirmation_answers_not_a_duplicate() -> (
    None
):
    src, nats, chain, _, stats = build()
    chain.gate = asyncio.Event()
    agen = Reader(src.stream([W]))
    nats.push(ev("nats", delta=5))
    await take(agen)
    chain.push(ev("chain", delta=5))  # the logsSubscribe path got there too
    await agen.quiet()
    chain.gate.set()
    (c,) = await take(agen)
    assert isinstance(c, LeaderConfirmation) and c.status == "confirmed"
    assert stats.counters["chain_duplicate"] == 1
    await agen.quiet()  # exactly one confirmation for the key
    await agen.aclose()


async def test_a_failed_confirmation_is_retried_when_the_logs_path_later_proves_the_trade() -> None:
    src, nats, chain, clock, stats = build()
    preview = ev("nats", delta=5)
    chain.answers.append(conf(preview, "rpc_error", "rate_limited", at=clock.now))
    agen = Reader(src.stream([W]))
    nats.push(preview)
    got = await take(agen, 2)
    assert isinstance(got[1], LeaderConfirmation) and got[1].status == "rpc_error"
    chain.push(ev("chain", delta=5))  # the truth arrives by the other road
    (late,) = await take(agen)
    assert isinstance(late, LeaderConfirmation) and late.status == "confirmed"
    assert stats.counters["late_confirmation"] == 1 and len(chain.confirms) == 2
    await agen.aclose()


async def test_a_duplicate_preview_is_dropped() -> None:
    src, nats, chain, _, stats = build()
    agen = Reader(src.stream([W]))
    nats.push(ev("nats"))
    nats.push(ev("nats"))
    await take(agen, 2)  # preview + one confirmation
    await agen.quiet()
    assert stats.counters["duplicate_preview"] == 1 and len(chain.confirms) == 1
    await agen.aclose()


async def test_two_mints_in_one_transaction_are_two_keys() -> None:
    src, nats, _, _, _ = build()
    agen = Reader(src.stream([W]))
    nats.push(ev("nats", mint="M1"))
    nats.push(ev("nats", mint="M2"))
    got = await take(agen, 4)
    assert sorted({e.mint for e in got if isinstance(e, LeaderEvent)}) == ["M1", "M2"]
    await agen.aclose()


async def test_a_crash_in_the_confirmation_is_an_rpc_error_confirmation_and_the_stream_survives() -> (
    None
):
    src, nats, chain, _, _ = build()
    chain.answers.append(RuntimeError("boom"))
    agen = Reader(src.stream([W]))
    nats.push(ev("nats", sig="a"))
    got = await take(agen, 2)
    assert isinstance(got[1], LeaderConfirmation)
    assert (got[1].status, got[1].reason) == ("rpc_error", "confirm_crashed")
    nats.push(ev("nats", sig="b"))
    after = await take(agen, 2)
    assert isinstance(after[1], LeaderConfirmation) and after[1].status == "confirmed"
    await agen.aclose()


async def test_unresolved_previews_are_never_evicted_by_the_bound() -> None:
    src, nats, chain, _, _ = build()
    chain.gate = asyncio.Event()  # no confirmation ever finishes
    agen = Reader(src.stream([W]))
    import hunter_exchanges.pumpfun.leader_source as module

    original = module.STATES_MAX
    module.STATES_MAX = 3
    try:
        for i in range(6):
            nats.push(ev("nats", sig=f"s{i}"))
        await take(agen, 6)
        chain.gate.set()
        got = await take(agen, 6)
    finally:
        module.STATES_MAX = original
    assert sorted(c.signature for c in got if isinstance(c, LeaderConfirmation)) == [
        f"s{i}" for i in range(6)
    ]
    await agen.aclose()


async def test_the_whole_in_process_path_is_timed_for_the_consumer() -> None:
    src, nats, _, clock, stats = build()
    agen = Reader(src.stream([W]))
    nats.push(ev("nats"))
    clock.now = T0 + timedelta(milliseconds=3)
    await take(agen, 2)
    assert stats.snapshot()["first_seen_to_deliver"]["n"] == 1
    await agen.aclose()


# --------------------------------------------------------------------------- coverage gaps
def gap(
    reason: str,
    *,
    wallet: str | None = None,
    end: datetime | None = None,
    start: datetime = T0,
) -> LeaderGap:
    return LeaderGap(wallet, start, end, reason)


async def test_a_child_gap_passes_through_with_its_own_reason_and_the_other_side_stays_quiet() -> (
    None
):
    """The decision of 06/10: losing the NATS path is an explicit, named gap even while the chain still
    covers it — the chain's slower confirmations resume, but the lane is told the fast path was down."""
    src, nats, _, _, _ = build()
    agen = Reader(src.stream([W]))
    nats.push(gap("nats_disconnect"))
    (g,) = await take(agen)
    assert g == gap("nats_disconnect")
    closed = gap("nats_disconnect", end=T0 + timedelta(seconds=1))
    nats.push(closed)
    assert (await take(agen)) == [closed]
    await agen.aclose()


async def test_both_sources_lost_adds_one_no_coverage_gap_that_closes_when_either_recovers() -> (
    None
):
    src, nats, chain, clock, _ = build()
    agen = Reader(src.stream([W]))
    t1, t2 = T0 + timedelta(seconds=1), T0 + timedelta(seconds=2)
    nats.push(gap("nats_disconnect", start=t1))
    await take(agen)
    chain.push(gap("chain_ws_down", start=t2))
    got = await take(agen, 2)  # the chain's own gap + the intersection
    both = next(g for g in got if isinstance(g, LeaderGap) and g.reason.startswith("no_coverage"))
    assert (both.wallet, both.start, both.end) == (None, t2, None)  # lost from when BOTH were out
    assert both.reason == "no_coverage:nats_disconnect+chain_ws_down"
    clock.now = T0 + timedelta(seconds=9)
    nats.push(gap("nats_disconnect", start=t1, end=clock.now))
    got = await take(agen, 2)
    closed = next(g for g in got if isinstance(g, LeaderGap) and g.reason.startswith("no_coverage"))
    assert (closed.start, closed.end) == (t2, clock.now)
    await agen.aclose()


async def test_a_wallet_lost_on_one_side_and_everything_on_the_other_is_a_wallet_no_coverage() -> (
    None
):
    src, nats, chain, _, _ = build()
    agen = Reader(src.stream([W, W2]))
    nats.push(gap("nats_subscription_refused", wallet=W2))
    chain.push(gap("chain_ws_down"))
    got = await take(agen, 3)
    both = [g for g in got if isinstance(g, LeaderGap) and g.reason.startswith("no_coverage")]
    assert len(both) == 1 and both[0].wallet == W2 and both[0].end is None
    await agen.aclose()


async def test_a_nats_unseeded_wallet_with_the_chain_down_is_no_coverage_for_that_wallet() -> None:
    """Astra's scenario: the socket is up but cannot derive a delta (seed failed) and the chain is out."""
    src, nats, chain, _, _ = build()
    agen = Reader(src.stream([W, W2]))
    nats.push(gap("nats_unseeded", wallet=W))
    chain.push(gap("chain_ws_down"))
    got = await take(agen, 3)
    both = [g for g in got if isinstance(g, LeaderGap) and g.reason.startswith("no_coverage")]
    assert [g.wallet for g in both] == [W]
    await agen.aclose()


async def test_the_startup_window_is_no_coverage_until_either_source_is_ready() -> None:
    src, nats, chain, _, _ = build()
    agen = Reader(src.stream([W]))
    nats.push(gap("nats_connect"))
    chain.push(gap("chain_connect"))
    got = await take(agen, 3)
    both = next(g for g in got if isinstance(g, LeaderGap) and g.reason.startswith("no_coverage"))
    assert both.end is None
    chain.push(gap("chain_connect", end=T0 + timedelta(seconds=1)))
    got = await take(agen, 2)
    assert any(
        isinstance(g, LeaderGap) and g.reason.startswith("no_coverage") and g.end for g in got
    )
    await agen.aclose()


async def test_a_transaction_level_loss_passes_through_unannounced() -> None:
    src, _, chain, _, _ = build()
    agen = Reader(src.stream([W]))
    single = gap("chain_tx_not_found", wallet=W, end=T0 + timedelta(seconds=3))
    chain.push(single)
    assert (await take(agen)) == [single]
    await agen.aclose()


async def test_a_crashed_child_is_a_named_gap_not_a_dead_stream() -> None:
    src, nats, _, _, stats = build()

    async def boom(wallets: Collection[str]) -> AsyncIterator[Item]:
        raise RuntimeError("child died")
        yield  # pragma: no cover

    nats.stream = boom  # type: ignore[method-assign]
    agen = Reader(src.stream([W]))
    (g,) = await take(agen)
    assert isinstance(g, LeaderGap) and g.reason == "nats_crashed" and g.end is None
    assert stats.counters["nats_crashed"] == 1
    await agen.aclose()


async def test_closing_the_stream_closes_both_sources_and_stops_the_tasks() -> None:
    src, nats, chain, _, _ = build()
    chain.gate = asyncio.Event()
    agen = Reader(src.stream([W]))
    nats.push(ev("nats"))
    await take(agen)  # a confirmation is now in flight
    before = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
    await agen.aclose()
    await asyncio.sleep(0.02)
    assert nats.closed and chain.closed and all(t.done() for t in before)


async def test_an_empty_wallet_set_is_refused() -> None:
    src, *_ = build()
    with pytest.raises(ValueError, match="wallet"):
        await src.stream([]).__anext__()
