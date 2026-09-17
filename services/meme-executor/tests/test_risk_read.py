"""T4.45 Part A — the executor's own ``/in-memory-coin`` read on the admission
path: bounded, deadlined, and never a pass on missing data.

Measured (16/09/2026): the radar's row landed a median 103 s **after** the
decision that needed it, and 36 of the 39 in-window real orders had no bundle
measured. Waiting (T4.28g) stopped burning proposals but did not buy the coin;
reading costs one HTTP call on the path that is already waiting for an RPC.

No network and no database here: a fake client answers, and the session the
persistence uses is a fake whose executed statements are inspected.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pytest

from hunter_exchanges.pumpfun.board_models import RISK_SOURCE, NormalizedRiskSnapshot
from hunter_meme_executor import risk_read
from hunter_meme_executor.context import ExecutorState
from hunter_meme_executor.repo import RISK_SNAPSHOT_MAX_AGE_S
from hunter_meme_executor.risk_read import (
    DEFAULT_TIMEOUT_S,
    ON_DEMAND_MIN_INTERVAL_S,
    ON_DEMAND_SOURCE,
    due_for_on_demand_read,
    ensure_snapshots,
    fetch_risk_snapshot,
    read_risk_snapshot_on_demand,
)

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 16, 20, 30, tzinfo=UTC)
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"


def snapshot(**overrides: Any) -> NormalizedRiskSnapshot:
    values: dict[str, Any] = {
        "mint": MINT,
        "bundled_share": Decimal("0.05"),
        "dev_share": Decimal("0.03"),
        "top10_share": Decimal("0.2"),
        "raw": {"mint": MINT, "bundlerOwnedPercentageV2": 5},
        "observed_at": NOW,
        "received_at": NOW,
    }
    values.update(overrides)
    return NormalizedRiskSnapshot(**values)


class FakeClient:
    """One answer, one exception, or a sleep longer than any deadline."""

    def __init__(self, *, answer: Any = None, raises: Exception | None = None, hang: bool = False):
        self.answer, self.raises, self.hang = answer, raises, hang
        self.calls: list[str] = []

    async def get_risk_snapshot(self, mint: str) -> NormalizedRiskSnapshot:
        self.calls.append(mint)
        if self.hang:
            await asyncio.sleep(60)
        if self.raises is not None:
            raise self.raises
        assert self.answer is not None
        return self.answer


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.statements.append((str(statement), params))

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[FakeSession]:
        yield self


@dataclass
class FakeConfig:
    risk_read_timeout_s: float = DEFAULT_TIMEOUT_S


@dataclass
class FakeKillSwitch:
    blocks_entries: bool = False


@dataclass
class FakeContext:
    risk_client: Any
    config: FakeConfig = field(default_factory=FakeConfig)
    state: ExecutorState = field(default_factory=ExecutorState)
    session_factory: Any = None
    kill: FakeKillSwitch = field(default_factory=FakeKillSwitch)


@pytest.fixture
def persisted(monkeypatch: pytest.MonkeyPatch) -> FakeSession:
    """``role_session`` replaced by a fake transaction — the statement under test
    is the shared one in ``hunter_core.db.meme_risk_snapshots``, and what matters
    here is that it ran with this row's values."""
    session = FakeSession()

    @asynccontextmanager
    async def fake_role_session(*args: Any, **kwargs: Any) -> AsyncGenerator[FakeSession]:
        yield session

    monkeypatch.setattr(risk_read, "role_session", fake_role_session)
    return session


async def _read(ctx: FakeContext, *, now: datetime) -> bool:
    """The call under test, with the fake context the production signature does
    not know about — one ``cast`` here instead of an ignore on every line."""
    return await read_risk_snapshot_on_demand(cast("ExecutorContext", ctx), MINT, now=now)


class TestTheDeadline:
    @pytest.mark.asyncio
    async def test_a_hanging_endpoint_costs_the_deadline_and_nothing_more(self) -> None:
        """The entry loop also owes the exits their tick and the kill switch its
        10 s: a third party that stops answering must cost one admission, not the
        process. The read returns ``None``, which the caller turns into the
        refusal that already existed."""
        client = FakeClient(hang=True)
        started = asyncio.get_running_loop().time()
        result = await fetch_risk_snapshot(client, MINT, timeout_s=0.05)
        elapsed = asyncio.get_running_loop().time() - started
        assert result is None
        assert elapsed < 1.0, "the call must not outlive its deadline"

    @pytest.mark.asyncio
    async def test_the_default_deadline_is_a_second_and_a_half(self) -> None:
        assert DEFAULT_TIMEOUT_S == 1.5

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "error", [RuntimeError("boom"), ValueError("malformed"), ConnectionError("down")]
    )
    async def test_any_failure_is_the_same_answer_no_reading(self, error: Exception) -> None:
        assert await fetch_risk_snapshot(FakeClient(raises=error), MINT, timeout_s=1.0) is None

    @pytest.mark.asyncio
    async def test_a_good_answer_comes_back_whole(self) -> None:
        got = await fetch_risk_snapshot(FakeClient(answer=snapshot()), MINT, timeout_s=1.0)
        assert got is not None and got.bundled_share == Decimal("0.05")


class TestTheBound:
    def test_a_mint_never_read_is_due(self) -> None:
        state = ExecutorState()
        assert due_for_on_demand_read(state, MINT, now=NOW, min_interval_s=600)

    def test_a_mint_just_attempted_is_not(self) -> None:
        """Including a **failed** attempt: the 1 s entry loop would otherwise
        re-read a mint the endpoint refuses once per second, and the shared
        60 req/min budget is gone in a minute."""
        state = ExecutorState(risk_read_attempts={MINT: NOW - timedelta(seconds=30)})
        assert not due_for_on_demand_read(state, MINT, now=NOW, min_interval_s=600)

    def test_past_the_window_it_is_due_again(self) -> None:
        state = ExecutorState(risk_read_attempts={MINT: NOW - timedelta(seconds=601)})
        assert due_for_on_demand_read(state, MINT, now=NOW, min_interval_s=600)

    def test_the_window_is_the_admissions_own(self) -> None:
        """One read per mint per 600 s, which is exactly how long a row stays
        usable: a second read inside it could not change any answer."""
        assert ON_DEMAND_MIN_INTERVAL_S == RISK_SNAPSHOT_MAX_AGE_S == 600

    @pytest.mark.asyncio
    async def test_the_second_call_in_the_window_does_not_touch_the_endpoint(
        self, persisted: FakeSession
    ) -> None:
        client = FakeClient(answer=snapshot())
        ctx = FakeContext(risk_client=client)
        assert await _read(ctx, now=NOW) is True
        assert await _read(ctx, now=NOW + timedelta(seconds=5)) is False
        assert client.calls == [MINT]

    @pytest.mark.asyncio
    async def test_the_book_of_attempts_is_pruned_to_its_own_window(
        self, persisted: FakeSession
    ) -> None:
        """An executor runs for days over hundreds of mints; the bound must not
        grow with every coin the desk ever proposed."""
        ctx = FakeContext(risk_client=FakeClient(answer=snapshot()))
        ctx.state.risk_read_attempts = {f"old{i}": NOW - timedelta(seconds=900) for i in range(50)}
        await _read(ctx, now=NOW)
        assert set(ctx.state.risk_read_attempts) == {MINT}


class TestWhatIsWritten:
    @pytest.mark.asyncio
    async def test_the_row_is_persisted_by_the_shared_writer_naming_its_reader(
        self, persisted: FakeSession
    ) -> None:
        """Same table, same column list, same ``ON CONFLICT`` — the radar's
        writer. Only ``source`` says who asked, so the admission reads this row
        exactly like the radar's and an audit can still tell them apart."""
        ctx = FakeContext(risk_client=FakeClient(answer=snapshot()))
        assert await _read(ctx, now=NOW) is True
        insert = [s for s in persisted.statements if "meme_risk_snapshots" in s[0]]
        assert len(insert) == 1
        statement, params = insert[0]
        assert "INSERT INTO meme_risk_snapshots" in statement
        assert "ON CONFLICT (observed_at, mint) DO NOTHING" in statement
        assert params["source"] == ON_DEMAND_SOURCE != RISK_SOURCE
        assert params["mint"] == MINT
        assert params["bundled_share"] == Decimal("0.05")
        assert ctx.state.risk_reads_on_demand == 1
        assert ctx.state.risk_reads_on_demand_failed == 0

    @pytest.mark.asyncio
    async def test_a_timeout_writes_nothing_and_counts_as_failed(
        self, persisted: FakeSession
    ) -> None:
        ctx = FakeContext(risk_client=FakeClient(hang=True), config=FakeConfig(0.05))
        assert await _read(ctx, now=NOW) is False
        assert persisted.statements == []
        assert (ctx.state.risk_reads_on_demand, ctx.state.risk_reads_on_demand_failed) == (0, 1)

    @pytest.mark.asyncio
    async def test_a_reading_without_the_bundle_is_kept_but_never_reported_as_measured(
        self, persisted: FakeSession
    ) -> None:
        """The endpoint answers 65 fields and sometimes not that one. The row is
        evidence and is stored; reporting it as measured would hand check 11 a
        ``None`` it must refuse — the refusal this task removes only when the
        number is really there."""
        ctx = FakeContext(risk_client=FakeClient(answer=snapshot(bundled_share=None)))
        assert await _read(ctx, now=NOW) is False
        assert [s for s in persisted.statements if "meme_risk_snapshots" in s[0]]
        assert (ctx.state.risk_reads_on_demand, ctx.state.risk_reads_on_demand_failed) == (1, 1)

    @pytest.mark.asyncio
    async def test_without_a_client_nothing_happens_at_all(self, persisted: FakeSession) -> None:
        """A paper-inert executor, or a deployment that has not wired the client:
        the T4.28g behaviour stands, no attempt is recorded, no row is written."""
        ctx = FakeContext(risk_client=None)
        assert await _read(ctx, now=NOW) is False
        assert persisted.statements == [] and ctx.state.risk_read_attempts == {}


class TestReadFirstThenWait:
    """``ensure_snapshots`` — the T4.28g *wait* becomes a *read*, and the wait
    stays behind it as the fallback."""

    OTHER = "So11111111111111111111111111111111111111112"

    @pytest.mark.asyncio
    async def test_a_mint_already_measured_is_not_read_again(self, persisted: FakeSession) -> None:
        """The radar's row is as good as ours — spending a shared 60 req/min
        budget to re-learn it would be the opposite of the fix."""
        client = FakeClient(answer=snapshot())
        ctx = FakeContext(risk_client=client)
        measured = await ensure_snapshots(
            cast("ExecutorContext", ctx), [MINT], frozenset({MINT}), now=NOW
        )
        assert measured == frozenset({MINT})
        assert client.calls == []

    @pytest.mark.asyncio
    async def test_an_unmeasured_mint_is_read_and_joins_the_measured_set(
        self, persisted: FakeSession
    ) -> None:
        client = FakeClient(answer=snapshot())
        ctx = FakeContext(risk_client=client)
        measured = await ensure_snapshots(
            cast("ExecutorContext", ctx), [MINT], frozenset(), now=NOW
        )
        assert measured == frozenset({MINT})
        assert client.calls == [MINT]

    @pytest.mark.asyncio
    async def test_a_failed_read_leaves_the_mint_unmeasured_so_the_wait_still_applies(
        self, persisted: FakeSession
    ) -> None:
        """This is the whole safety of Part A: when the read fails the planner
        sees the same ``frozenset()`` it saw before T4.45 and skips
        ``risk_snapshot_pending`` — the proposal stays ``proposed`` for the human
        instead of being opened and refused ``bundled_share_unmeasurable``."""
        ctx = FakeContext(risk_client=FakeClient(raises=RuntimeError("503")))
        measured = await ensure_snapshots(
            cast("ExecutorContext", ctx), [MINT], frozenset(), now=NOW
        )
        assert measured == frozenset()

    @pytest.mark.asyncio
    async def test_only_the_mints_handed_in_are_read(self, persisted: FakeSession) -> None:
        """The caller hands in the picks the planner *would* open, never the whole
        candidate list: a proposal that is too old, on a busy mint or in refusal
        cooldown gets no read, because nothing would use the answer."""
        client = FakeClient(answer=snapshot())
        ctx = FakeContext(risk_client=client)
        await ensure_snapshots(cast("ExecutorContext", ctx), [MINT], frozenset(), now=NOW)
        assert client.calls == [MINT] and self.OTHER not in client.calls


class TestTheKillSwitch:
    @pytest.mark.asyncio
    async def test_a_blocking_switch_spends_no_read_at_all(self, persisted: FakeSession) -> None:
        """``TRADING_DISABLED``/``EMERGENCY`` refuse the entry by name a few lines
        later (check 1), so a read taken now can only be thrown away — and the
        ``/in-memory-coin`` budget it would spend is **shared with the radar**,
        which is still marking open positions while entries are off."""
        client = FakeClient(answer=snapshot())
        ctx = FakeContext(risk_client=client, kill=FakeKillSwitch(blocks_entries=True))
        assert await _read(ctx, now=NOW) is False
        assert client.calls == []
        assert persisted.statements == []
        assert ctx.state.risk_read_attempts == {}, "not an attempt: it never happened"
        assert ctx.state.risk_reads_on_demand_failed == 0, "not a failure either"
