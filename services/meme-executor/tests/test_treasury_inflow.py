"""T4.60 — the daily-loss brake counts treasury inflows.

Defect (18/09/2026 13:12 BRT): position YOU lost 0.0395 SOL (bought 0.0516,
sold 0.0121, trailing exit, -0.77 R). At 13:12:06 the treasury swapped 5.75
USDC -> 0.0516 SOL because the wallet had fallen below the floor. The next
heartbeat published ``daily_loss_sol = 0`` (``equity_sol 0.732 >
day_start_sol_equity 0.686``): the brake was ``day_start - equity``, blind to
the USDC that refilled the wallet, so ``MEME_DAILY_LOSS_CAP_SOL`` could never
trip while the treasury kept topping up.

Three things are proved here: the reader (one bounded SELECT per tick, cached
10 s, the **last known** value on a failed read — never zero), the day anchor
(a top-up that landed before the first anchor of the day is taken out of
``day_start_sol_equity``, so it is not counted twice), and the heartbeat's
``daily_loss_sol`` (the YOU case gives 0.0395, not 0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_meme_executor import treasury_inflow
from hunter_meme_executor.admission import day_start_utc
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.heartbeat import daily_loss_fields
from hunter_meme_executor.kill_switch import DayAnchor
from hunter_meme_executor.treasury_inflow import TreasuryInflowReader, ensure_anchor

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 18, 16, 12, 6, tzinfo=UTC)  # 13:12:06 BRT
DAY_START = day_start_utc(NOW)
INFLOW_YOU = Decimal("0.0516")
LOSS_YOU = Decimal("0.0395")
EQUITY_DAY_START = Decimal("0.686")


class _Session:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


@dataclass
class FakeDb:
    """What ``treasury_db.sol_inflow_since`` answers, and how often it was asked."""

    inflow: Decimal = INFLOW_YOU
    down: bool = False
    calls: list[datetime] = field(default_factory=lambda: list[datetime]())

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def sol_inflow_since(_session: Any, *, since: datetime) -> Decimal:
            self.calls.append(since)
            if self.down:
                raise RuntimeError("postgres down")
            return self.inflow

        def fake_session(_factory: Any, *, db_role: str) -> _Session:
            return _Session()

        monkeypatch.setattr(treasury_inflow, "role_session", fake_session)
        monkeypatch.setattr(treasury_inflow.treasury_db, "sol_inflow_since", sol_inflow_since)


async def test_the_first_read_sums_since_the_sao_paulo_day_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()
    db.install(monkeypatch)
    reader = TreasuryInflowReader()
    got = await reader.refresh(cast(Any, None), day_start_utc=DAY_START, now=NOW)
    assert got == INFLOW_YOU and reader.inflow_sol == INFLOW_YOU
    assert db.calls == [DAY_START]
    assert reader.read_at == NOW and reader.read_failures == 0


async def test_the_read_is_cached_for_ten_seconds_then_repeated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()
    db.install(monkeypatch)
    reader = TreasuryInflowReader()
    await reader.refresh(cast(Any, None), day_start_utc=DAY_START, now=NOW)
    db.inflow = INFLOW_YOU * 2
    within = await reader.refresh(
        cast(Any, None), day_start_utc=DAY_START, now=NOW + timedelta(seconds=9)
    )
    assert within == INFLOW_YOU and len(db.calls) == 1, "one bounded SELECT per tick, not more"
    after = await reader.refresh(
        cast(Any, None), day_start_utc=DAY_START, now=NOW + timedelta(seconds=10)
    )
    assert after == INFLOW_YOU * 2 and len(db.calls) == 2


async def test_a_new_day_forces_a_fresh_read_even_inside_the_cache_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()
    db.install(monkeypatch)
    reader = TreasuryInflowReader()
    await reader.refresh(cast(Any, None), day_start_utc=DAY_START, now=NOW)
    db.inflow = Decimal(0)
    tomorrow = DAY_START + timedelta(days=1)
    got = await reader.refresh(
        cast(Any, None), day_start_utc=tomorrow, now=NOW + timedelta(seconds=1)
    )
    assert got == Decimal(0) and db.calls[-1] == tomorrow


async def test_a_failed_read_keeps_the_last_known_inflow_never_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()
    db.install(monkeypatch)
    reader = TreasuryInflowReader()
    await reader.refresh(cast(Any, None), day_start_utc=DAY_START, now=NOW)
    db.down = True
    later = NOW + timedelta(seconds=30)
    got = await reader.refresh(cast(Any, None), day_start_utc=DAY_START, now=later)
    assert got == INFLOW_YOU, "a Postgres that cannot answer must not erase the inflow"
    assert reader.inflow_sol == INFLOW_YOU
    assert reader.read_failures == 1 and reader.last_error == "RuntimeError"
    assert reader.read_at == NOW, "the age of the number is the desk's own signal"


async def test_a_failure_before_any_read_answers_none_not_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb(down=True)
    db.install(monkeypatch)
    reader = TreasuryInflowReader()
    got = await reader.refresh(cast(Any, None), day_start_utc=DAY_START, now=NOW)
    assert got is None and reader.inflow_sol is None
    assert reader.read_failures == 1


# ------------------------------------------------------------------ the anchor
@dataclass
class FakeKill:
    anchor: DayAnchor | None = None
    anchored: list[tuple[datetime, Decimal]] = field(default_factory=lambda: list[Any]())
    peaks: list[Decimal] = field(default_factory=lambda: list[Decimal]())

    async def anchor_day(self, day_start_utc: datetime, equity: Decimal) -> DayAnchor:
        self.anchored.append((day_start_utc, equity))
        self.anchor = DayAnchor(day_start_utc, equity, equity, NOW)
        return self.anchor

    async def raise_peak(self, equity: Decimal) -> None:
        self.peaks.append(equity)


@dataclass
class FakeContext:
    kill: FakeKill = field(default_factory=FakeKill)
    treasury_inflow: TreasuryInflowReader = field(default_factory=TreasuryInflowReader)
    session_factory: Any = None


async def test_a_top_up_before_the_first_anchor_of_the_day_is_not_counted_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """00:05 BRT: the treasury swaps 0.0516 SOL in; 09:00 BRT: the first
    candidate anchors the day. The anchor must be the equity **before** the
    top-up, or ``day_start + inflow - equity`` would report a 0.0516 loss the
    desk never had."""
    db = FakeDb(inflow=INFLOW_YOU)
    db.install(monkeypatch)
    ctx = FakeContext()
    equity_now = EQUITY_DAY_START + INFLOW_YOU
    await ensure_anchor(cast(ExecutorContext, ctx), NOW, equity_now)
    assert ctx.kill.anchored == [(DAY_START, EQUITY_DAY_START)]
    anchor = ctx.kill.anchor
    assert anchor is not None
    assert anchor.day_start_sol_equity + INFLOW_YOU - equity_now == Decimal(0)


async def test_an_anchor_with_the_inflow_unreadable_is_refused_not_guessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb(down=True)
    db.install(monkeypatch)
    ctx = FakeContext()
    await ensure_anchor(cast(ExecutorContext, ctx), NOW, EQUITY_DAY_START)
    assert ctx.kill.anchored == [] and ctx.kill.anchor is None


async def test_an_existing_anchor_of_the_same_day_only_raises_the_peak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()
    db.install(monkeypatch)
    existing = DayAnchor(DAY_START, EQUITY_DAY_START, EQUITY_DAY_START, NOW)
    ctx = FakeContext(kill=FakeKill(anchor=existing))
    got = await ensure_anchor(cast(ExecutorContext, ctx), NOW, Decimal("0.7"))
    assert got is existing
    assert ctx.kill.anchored == [] and ctx.kill.peaks == [Decimal("0.7")]
    # A restart mid-day: the anchor row is already today's, and the admission
    # still needs the inflow — it is read on this branch too (one SELECT).
    assert ctx.treasury_inflow.inflow_sol == INFLOW_YOU and db.calls == [DAY_START]


async def test_yesterdays_anchor_is_never_returned_for_today(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb(down=True)
    db.install(monkeypatch)
    yesterday = DayAnchor(DAY_START - timedelta(days=1), Decimal("1"), Decimal("1"), NOW)
    ctx = FakeContext(kill=FakeKill(anchor=yesterday))
    got = await ensure_anchor(cast(ExecutorContext, ctx), NOW, Decimal("0.7"))
    assert got is None and ctx.kill.anchored == [] and ctx.kill.peaks == []


# ------------------------------------------------------------------ the heartbeat
def test_the_you_case_publishes_the_loss_not_zero() -> None:
    anchor = DayAnchor(DAY_START, EQUITY_DAY_START, EQUITY_DAY_START, NOW)
    equity = EQUITY_DAY_START - LOSS_YOU + INFLOW_YOU  # what the wallet showed after the swap
    blind = daily_loss_fields(anchor, equity, None)
    assert blind["daily_loss_sol"] == "", "an unknown inflow is published as unknown, never 0"
    assert blind["treasury_inflow_today_sol"] == ""
    seen = daily_loss_fields(anchor, equity, INFLOW_YOU)
    assert Decimal(seen["daily_loss_sol"]) == LOSS_YOU
    assert Decimal(seen["treasury_inflow_today_sol"]) == INFLOW_YOU


def test_the_cap_of_0_15_is_reached_with_three_top_ups() -> None:
    anchor = DayAnchor(DAY_START, Decimal("1.0"), Decimal("1.0"), NOW)
    inflow = INFLOW_YOU * 3
    equity = Decimal("1.0") - Decimal("0.15") + inflow
    assert Decimal(daily_loss_fields(anchor, equity, inflow)["daily_loss_sol"]) == Decimal("0.15")


def test_without_an_anchor_or_an_equity_nothing_is_published() -> None:
    assert daily_loss_fields(None, Decimal("1"), INFLOW_YOU)["daily_loss_sol"] == ""
    anchor = DayAnchor(DAY_START, Decimal("1.0"), Decimal("1.0"), NOW)
    assert daily_loss_fields(anchor, None, INFLOW_YOU)["daily_loss_sol"] == ""
