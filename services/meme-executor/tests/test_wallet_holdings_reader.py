"""The holdings verdict's lifecycle — fakes only (no network, no DB).

What is pinned: the chain is read **before** the recognized set (so a mint the
engine bought is already in Postgres when the scan saw it), the recognized set
is asked with the 60 s grace, a verdict is published only when the two RPCs and
the SELECT all answered, a failure never renews the stamp, the verdict is
worthless after 30 s (the admission then **defers**, §8.2), one read runs at a
time, a timed-out thread blocks the next read instead of piling up, a read
from an older slot never replaces a newer verdict, and a failure backs every
caller off (guardian F3).

No assertion depends on how fast this machine is (guardian F5): the fakes answer
at once, the fake deadline is a minute, a blocked read is blocked on an event the
test controls, and the only short deadlines guard a read that can never finish."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

import hunter_meme_executor.wallet_holdings as wh
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_meme_executor.chain import HoldingsRead, TokenHolding
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.treasury_rules import USDC_MINT
from hunter_meme_executor.wallet_exceptions import HoldingException
from hunter_meme_executor.wallet_holdings import (
    RECOGNIZED_GRACE_S,
    WalletHoldingsReader,
    admission_holdings,
    holdings_once,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 27, 22, 0, 0, tzinfo=UTC)
GUARD_S = 30.0
"""Only ever a hang guard: a correct reader returns long before it."""
OWN = "OwnPosition111111111111111111111111111111111"
FOREIGN = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"


def _h(mint: str, amount: int = 5_000_000) -> TokenHolding:
    return TokenHolding(mint, TOKEN_PROGRAM_ID, amount, 6, state="initialized")


@dataclass
class FakeChain:
    holdings: tuple[TokenHolding, ...] = ()
    slot: int = 100
    observed_at: datetime = T0
    fail: bool = False
    frozen: bool = False
    """A lagging RPC repeating one snapshot: the slots stop moving."""
    gate: threading.Event | None = None
    entered: threading.Event = field(default_factory=threading.Event)
    """Set the moment a read is inside the RPC (the test waits on it, never sleeps)."""
    log: list[str] = field(default_factory=lambda: list[str]())

    def token_holdings(self, owner: str) -> HoldingsRead:
        self.log.append(f"chain:{owner}")
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(60)
        if self.fail:
            raise RuntimeError("rpc down")
        slots = (self.slot, self.slot)
        if not self.frozen:
            self.slot += 1  # a healthy cluster: every read sees newer slots
        return HoldingsRead(self.holdings, slots, self.observed_at)


@dataclass
class FakeConfig:
    wallet_holdings_timeout_s: float = 60.0
    """Guardian F2: the collector's own deadline. A minute: the fakes answer at
    once, so no test here depends on how loaded the machine is (F5)."""
    wallet_read_timeout_s: float = 0.0
    """The SOL balance's deadline, a trap: any read that used it would time out."""


@dataclass
class FakeSigner:
    pubkey: str = "Wallet1111111111111111111111111111111111111"


@dataclass
class FakeContext:
    chain: FakeChain
    signer: FakeSigner | None = field(default_factory=FakeSigner)
    config: FakeConfig = field(default_factory=FakeConfig)
    session_factory: object = None
    holdings: WalletHoldingsReader = field(default_factory=WalletHoldingsReader)


@dataclass
class Db:
    recognized: frozenset[str] = frozenset()
    fail: bool = False
    since: list[datetime] = field(default_factory=lambda: list[datetime]())
    exceptions: tuple[HoldingException, ...] = ()
    """F1: Everton's audited per-mint exceptions (``wallet_exceptions.py``)."""
    asked: list[tuple[str, object]] = field(default_factory=lambda: list[tuple[str, object]]())
    """Which query ran on which session object, in order."""


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [T0]
    monkeypatch.setattr(wh, "utcnow", lambda: now[0])
    return now


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Db:
    state = Db()

    @asynccontextmanager
    async def session(*_a: Any, **_k: Any) -> AsyncGenerator[object]:
        yield object()

    async def recognized_mints(session: Any, *, since: datetime) -> frozenset[str]:
        state.since.append(since)
        state.asked.append(("recognized", session))
        if state.fail:
            raise RuntimeError("db down")
        return state.recognized

    async def active_exceptions(session: Any, *, wallet: str) -> tuple[HoldingException, ...]:
        state.asked.append((f"exceptions:{wallet}", session))
        return state.exceptions

    monkeypatch.setattr(wh, "role_session", session)
    monkeypatch.setattr(wh, "recognized_mints", recognized_mints)
    monkeypatch.setattr(wh, "active_exceptions", active_exceptions)
    return state


def _ctx(**chain: Any) -> FakeContext:
    return FakeContext(FakeChain(**chain))


def _as(ctx: FakeContext) -> ExecutorContext:
    return cast(ExecutorContext, ctx)


async def test_a_signerless_process_reads_nothing(clock: list[datetime], db: Db) -> None:
    ctx = _ctx(holdings=(_h(FOREIGN),))
    ctx.signer = None
    assert await admission_holdings(_as(ctx)) is None
    await holdings_once(_as(ctx))
    assert ctx.chain.log == [] and db.since == []


async def test_the_first_admission_reads_chain_then_postgres_with_the_grace(
    clock: list[datetime], db: Db
) -> None:
    db.recognized = frozenset({OWN})
    ctx = _ctx(holdings=(_h(OWN), _h(USDC_MINT), _h(FOREIGN)), slot=321)
    verdict = await admission_holdings(_as(ctx))
    assert verdict is not None
    assert verdict.unrecognized == (FOREIGN,)
    assert (verdict.slots, verdict.accounts, verdict.read_at) == ((321, 321), 3, T0)
    assert ctx.chain.log == ["chain:Wallet1111111111111111111111111111111111111"]
    assert db.since == [T0 - timedelta(seconds=RECOGNIZED_GRACE_S)]
    assert verdict.as_json()["unrecognized"] == [FOREIGN]


async def test_the_exceptions_come_from_the_same_session_and_are_reported_apart(
    clock: list[datetime], db: Db
) -> None:
    """F1: chain first, then the recognized set **and** the wallet's active
    exceptions in one transaction; the excepted mint leaves ``unrecognized`` and
    is reported apart — never added to the recognized set."""
    scam = "DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg"
    rule = HoldingException(TOKEN_PROGRAM_ID, scam, 5_000_000, 6, False, "exc-1", T0)
    db.exceptions = (rule,)
    ctx = _ctx(holdings=(_h(scam), _h(FOREIGN)))
    verdict = await admission_holdings(_as(ctx))
    assert verdict is not None
    assert verdict.unrecognized == (FOREIGN,) and verdict.excepted == (rule,)
    wallet = "Wallet1111111111111111111111111111111111111"
    assert [name for name, _ in db.asked] == ["recognized", f"exceptions:{wallet}"]
    assert db.asked[0][1] is db.asked[1][1], "one session, one transaction"
    fields = ctx.holdings.describe(clock[0])
    assert (fields["wallet_excepted_mints"], fields["wallet_excepted_count"]) == (scam, "1")
    assert fields["wallet_unrecognized_mints"] == FOREIGN


async def test_a_valid_verdict_is_reused_without_io_and_the_tick_always_rereads(
    clock: list[datetime], db: Db
) -> None:
    ctx = _ctx()
    await holdings_once(_as(ctx))
    clock[0] = T0 + timedelta(seconds=29)
    assert await admission_holdings(_as(ctx)) is not None
    assert len(ctx.chain.log) == 1
    await holdings_once(_as(ctx))
    assert len(ctx.chain.log) == 2


async def test_past_thirty_seconds_the_admission_rereads(clock: list[datetime], db: Db) -> None:
    ctx = _ctx()
    await holdings_once(_as(ctx))
    clock[0] = T0 + timedelta(seconds=31)
    ctx.chain.observed_at = clock[0]
    verdict = await admission_holdings(_as(ctx))
    assert verdict is not None and verdict.read_at == clock[0]
    assert len(ctx.chain.log) == 2


@pytest.mark.parametrize("where", ["chain", "db"])
async def test_a_failure_keeps_the_last_verdict_only_while_it_is_young(
    clock: list[datetime], db: Db, where: str
) -> None:
    ctx = _ctx()
    await holdings_once(_as(ctx))  # clean wallet at T0
    ctx.chain.holdings = (_h(FOREIGN),)  # would have been seen...
    ctx.chain.fail, db.fail = where == "chain", where == "db"
    clock[0] = T0 + timedelta(seconds=10)
    await holdings_once(_as(ctx))  # ...but the read failed: nothing published
    kept = ctx.holdings.valid(clock[0])
    assert kept is not None and kept.unrecognized == () and kept.read_at == T0
    assert ctx.holdings.failures == 1
    clock[0] = T0 + timedelta(seconds=31)
    assert await admission_holdings(_as(ctx)) is None  # defer, never "clean"
    assert ctx.holdings.deferrals == 1
    assert ctx.holdings.describe(clock[0])["wallet_holdings_state"] == "stale"


async def test_never_read_defers_by_name(clock: list[datetime], db: Db) -> None:
    ctx = _ctx(fail=True)
    assert await admission_holdings(_as(ctx)) is None
    fields = ctx.holdings.describe(clock[0])
    assert fields["wallet_holdings_state"] == "unread"
    assert fields["wallet_holdings_error"] == "RuntimeError"
    assert fields["wallet_holdings_deferrals"] == "1"


async def test_an_older_slot_never_replaces_a_newer_verdict(clock: list[datetime], db: Db) -> None:
    ctx = _ctx(slot=500)
    await holdings_once(_as(ctx))
    ctx.chain.slot, ctx.chain.holdings = 499, (_h(FOREIGN),)
    clock[0] = ctx.chain.observed_at = T0 + timedelta(seconds=10)
    await holdings_once(_as(ctx))
    kept = ctx.holdings.valid(clock[0])
    assert kept is not None and kept.slots == (500, 500)
    assert ctx.holdings.last_error == "slot_not_advanced"


async def test_one_program_regressing_is_enough_to_refuse_the_read(
    clock: list[datetime], db: Db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Astra: SPL 110->105 while Token-2022 100->120 - a minimum would have risen."""
    ctx = _ctx()
    answers = iter([((110, 100), ()), ((105, 120), (_h(FOREIGN),))])

    def token_holdings(owner: str) -> HoldingsRead:
        ctx.chain.log.append(owner)
        slots, held = next(answers)
        return HoldingsRead(held, slots, clock[0])

    monkeypatch.setattr(ctx.chain, "token_holdings", token_holdings)
    await holdings_once(_as(ctx))
    clock[0] = T0 + timedelta(seconds=10)
    await holdings_once(_as(ctx))
    kept = ctx.holdings.valid(clock[0])
    assert kept is not None and kept.slots == (110, 100) and kept.unrecognized == ()
    assert ctx.holdings.last_error == "slot_not_advanced"


async def test_a_frozen_snapshot_is_never_restamped_and_ages_out(
    clock: list[datetime], db: Db
) -> None:
    """Astra: an RPC repeating one clean snapshot must not keep the verdict alive."""
    ctx = _ctx(frozen=True)
    await holdings_once(_as(ctx))
    for s in (10, 20, 31):
        clock[0] = ctx.chain.observed_at = T0 + timedelta(seconds=s)
        await holdings_once(_as(ctx))
    assert ctx.holdings.last is not None and ctx.holdings.last.read_at == T0
    assert await admission_holdings(_as(ctx)) is None  # stale: defer
    assert ctx.holdings.last_error == "slot_not_advanced"


async def test_the_deadline_covers_the_wait_for_the_lock(clock: list[datetime], db: Db) -> None:
    """Astra: without a valid verdict, an admission waiting behind a slow read
    gives up at its own deadline - never deadline + another full read."""
    ctx = _ctx()
    ctx.config.wallet_holdings_timeout_s = 0.05
    await ctx.holdings.lock.acquire()  # someone holds the lock and never lets go
    try:
        # Without the deadline covering the wait, this would hang until the guard.
        verdict = await asyncio.wait_for(admission_holdings(_as(ctx)), timeout=GUARD_S)
    finally:
        ctx.holdings.lock.release()
    assert verdict is None and ctx.chain.log == []
    assert ctx.holdings.last_error == "TimeoutError"
    # It never read: not a failed read, no backoff (whoever holds the lock owns that).
    assert (ctx.holdings.failures, ctx.holdings.retry_at) == (0, None)


async def test_a_timed_out_read_blocks_the_next_one_and_never_publishes_late(
    clock: list[datetime], db: Db
) -> None:
    gate = threading.Event()
    ctx = _ctx(holdings=(_h(FOREIGN),), gate=gate)
    ctx.config.wallet_holdings_timeout_s = 0.05  # the gated read can never beat it
    try:
        await holdings_once(_as(ctx))
        assert ctx.holdings.last_error == "TimeoutError"
        # Astra: a saturated executor may start the thread after the deadline.
        assert await asyncio.to_thread(ctx.chain.entered.wait, GUARD_S)
        clock[0] = T0 + timedelta(seconds=10)  # past the first failure's backoff
        await holdings_once(_as(ctx))  # the first thread is still stuck in the RPC
        assert ctx.holdings.last_error == "holdings_read_in_flight"
        assert len(ctx.chain.log) == 1
    finally:
        gate.set()
    inflight = ctx.holdings.inflight
    assert inflight is not None
    await asyncio.wait([inflight], timeout=GUARD_S)  # the abandoned thread finishes...
    assert inflight.done() and ctx.holdings.last is None  # ...and its answer is dropped
    ctx.chain.gate = None
    clock[0] = T0 + timedelta(seconds=30)  # past the second failure's backoff (20 s)
    await holdings_once(_as(ctx))
    assert ctx.holdings.last is not None and ctx.holdings.last.unrecognized == (FOREIGN,)


async def test_concurrent_admissions_share_one_read(clock: list[datetime], db: Db) -> None:
    ctx = _ctx()
    first, second = await asyncio.gather(admission_holdings(_as(ctx)), admission_holdings(_as(ctx)))
    assert first is not None and first is second
    assert len(ctx.chain.log) == 1


async def test_the_heartbeat_names_five_mints_and_counts_them_all(
    clock: list[datetime], db: Db
) -> None:
    mints = [f"Mint{i}" for i in range(7)]
    ctx = _ctx(holdings=tuple(_h(m) for m in mints))
    await holdings_once(_as(ctx))
    fields = ctx.holdings.describe(clock[0])
    assert fields["wallet_holdings_state"] == "valid"
    assert fields["wallet_unrecognized_count"] == "7"
    assert fields["wallet_unrecognized_mints"] == ",".join(sorted(mints)[:5])
    assert fields["wallet_holdings_read_at"] == T0.isoformat()
    assert fields["wallet_holdings_error"] == ""


async def test_the_kill_switch_tick_reads_the_holdings_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main.kill_switch_once`` (10 s) — the verdict ages out in 30 s, so the tick
    must refresh it even when no candidate arrives (and the heartbeat stays true);
    guardian F6: **last**, so a slow read never delays the balance, the treasury
    or the launch blockhash of the same tick."""
    import hunter_meme_executor.main as main

    calls: list[str] = []

    class Blockhash:
        def refresh_if_stale(self, *_a: Any, **_k: Any) -> None:
            calls.append("launch_blockhash")

    def step(name: str) -> Any:
        async def run(*_a: Any, **_k: Any) -> None:
            calls.append(name)

        return run

    for name in (
        "gates_reload_once", "program_check_once", "wallet_refresh_once", "treasury_once",
        "treasury_inflow_once", "holdings_once",
    ):  # fmt: skip
        monkeypatch.setattr(main, name, step(name))

    @dataclass
    class Kill:
        async def refresh(self) -> None:
            calls.append("kill")

    @dataclass
    class LaunchConfig:
        enabled: bool = True

    @dataclass
    class LaunchStats:
        blockhash: Blockhash = field(default_factory=Blockhash)

    @dataclass
    class Config:
        launch: LaunchConfig = field(default_factory=LaunchConfig)

    @dataclass
    class Ctx:
        kill: Kill = field(default_factory=Kill)
        config: Config = field(default_factory=Config)
        launch: LaunchStats = field(default_factory=LaunchStats)
        signer: FakeSigner = field(default_factory=FakeSigner)
        chain: None = None

    await main.kill_switch_once(cast(ExecutorContext, Ctx()))
    assert calls == [
        "kill", "gates_reload_once", "program_check_once", "wallet_refresh_once",
        "treasury_once", "treasury_inflow_once", "launch_blockhash", "holdings_once",
    ]  # fmt: skip


async def test_an_admission_never_waits_behind_the_ticks_read_while_valid(
    clock: list[datetime], db: Db
) -> None:
    """The launch lane decides in the second after ``create``: a valid verdict is
    answered at once, even while the tick holds the lock on a slow RPC."""
    ctx = _ctx()
    await holdings_once(_as(ctx))  # a valid verdict at T0
    gate, ctx.chain.entered = threading.Event(), threading.Event()
    ctx.chain.gate = gate
    tick = asyncio.create_task(holdings_once(_as(ctx)))
    try:
        assert await asyncio.to_thread(ctx.chain.entered.wait, GUARD_S)  # in the RPC now
        assert ctx.holdings.lock.locked()
        verdict = await asyncio.wait_for(admission_holdings(_as(ctx)), timeout=GUARD_S)
        assert ctx.holdings.lock.locked()  # answered while the tick still held the lock
    finally:
        gate.set()
        await tick
    assert verdict is not None and verdict.read_at == T0


# ---- guardian F3: a failure backs every caller off ----------------------------------
async def test_one_failure_holds_every_read_for_ten_seconds(clock: list[datetime], db: Db) -> None:
    """The failed read's RPC client is the exits' too: nobody retries at once."""
    ctx = _ctx(fail=True)
    await holdings_once(_as(ctx))
    assert ctx.holdings.failures == 1 and len(ctx.chain.log) == 1
    clock[0] = T0 + timedelta(seconds=9)
    assert await admission_holdings(_as(ctx)) is None  # the admission respects it...
    await holdings_once(_as(ctx))  # ...and so does the tick
    assert len(ctx.chain.log) == 1 and ctx.holdings.failures == 1
    assert ctx.holdings.deferrals == 1  # still a deferral, by name
    ctx.chain.fail = False
    clock[0] = ctx.chain.observed_at = T0 + timedelta(seconds=10)
    assert await admission_holdings(_as(ctx)) is not None
    assert len(ctx.chain.log) == 2


async def test_consecutive_failures_double_the_wait_up_to_a_minute(
    clock: list[datetime], db: Db
) -> None:
    ctx = _ctx(fail=True)
    waits: list[float] = []
    for _ in range(6):
        failed_at = clock[0]
        await holdings_once(_as(ctx))
        retry_at = ctx.holdings.retry_at
        assert retry_at is not None
        waits.append((retry_at - failed_at).total_seconds())
        clock[0] = retry_at - timedelta(seconds=1)
        await holdings_once(_as(ctx))  # one second early: skipped, not a failure
        clock[0] = retry_at
    assert waits == [10.0, 20.0, 40.0, 60.0, 60.0, 60.0]
    assert ctx.holdings.failures == 6 and len(ctx.chain.log) == 6


async def test_days_of_failures_still_wait_one_minute_and_never_raise(
    clock: list[datetime], db: Db
) -> None:
    """``10.0 * 2**9999`` would be an OverflowError out of a "never raises" path."""
    ctx = _ctx(fail=True)
    ctx.holdings.streak = 10_000
    await holdings_once(_as(ctx))
    assert ctx.holdings.retry_at == T0 + timedelta(seconds=60)


async def test_a_published_read_clears_the_backoff(clock: list[datetime], db: Db) -> None:
    ctx = _ctx(fail=True)
    for s in (0, 10, 30):  # three failures: the next wait would be 40 s
        clock[0] = T0 + timedelta(seconds=s)
        await holdings_once(_as(ctx))
    ctx.chain.fail = False
    clock[0] = ctx.chain.observed_at = T0 + timedelta(seconds=70)
    await holdings_once(_as(ctx))
    assert ctx.holdings.valid(clock[0]) is not None
    assert (ctx.holdings.streak, ctx.holdings.retry_at) == (0, None)
    ctx.chain.fail = True
    clock[0] = T0 + timedelta(seconds=80)
    await holdings_once(_as(ctx))
    assert ctx.holdings.retry_at == clock[0] + timedelta(seconds=10)  # back to the first step


async def test_admissions_queued_behind_a_failing_read_do_not_retry_it(
    clock: list[datetime], db: Db
) -> None:
    """Two candidates, no valid verdict, the RPC down: one call, not one per caller."""
    ctx = _ctx(fail=True)
    first, second = await asyncio.gather(admission_holdings(_as(ctx)), admission_holdings(_as(ctx)))
    assert first is None and second is None
    assert len(ctx.chain.log) == 1 and ctx.holdings.failures == 1
    assert ctx.holdings.deferrals == 2


async def test_callers_timing_out_behind_one_stuck_read_count_it_once(
    clock: list[datetime], db: Db
) -> None:
    """Astra (F3 review): three deadlines expiring on one stuck collection are one
    failed read — 10 s of backoff, never 40 s that outlive a recovered RPC."""
    gate = threading.Event()
    ctx = _ctx(gate=gate)
    ctx.config.wallet_holdings_timeout_s = 0.05  # the gated read can never beat it
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(admission_holdings(_as(ctx)) for _ in range(3))), timeout=GUARD_S
        )
        assert results == [None, None, None] and ctx.holdings.deferrals == 3
        assert (ctx.holdings.failures, ctx.holdings.streak) == (1, 1)
        assert ctx.holdings.retry_at == T0 + timedelta(seconds=10)
    finally:
        gate.set()
    inflight = ctx.holdings.inflight
    assert inflight is not None
    await asyncio.wait([inflight], timeout=GUARD_S)
    assert len(ctx.chain.log) == 1


async def test_the_heartbeat_says_until_when_reads_are_held(clock: list[datetime], db: Db) -> None:
    ctx = _ctx(fail=True)
    await holdings_once(_as(ctx))
    fields = ctx.holdings.describe(clock[0])
    assert fields["wallet_holdings_retry_at"] == (T0 + timedelta(seconds=10)).isoformat()
    ctx.chain.fail = False
    clock[0] = T0 + timedelta(seconds=10)
    await holdings_once(_as(ctx))
    assert ctx.holdings.describe(clock[0])["wallet_holdings_retry_at"] == ""
