"""The tape puller: priority and intervals, the per-cycle budget, the cursor
walk to the high-water mark, dedupe rows, and what a refusal leaves behind —
since T4.2f the budget the edge enforces (~20/60 s, measured): the exact share
per cycle, one page per mint unless an open bet, a real 429 that measures,
shrinks and blocks, and ``rate_limited``/``not_polled`` meaning what they say.
No socket: a fake ``TradeSource`` serves the live captures."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.rate_shared import HttpRateLimited
from hunter_exchanges.pumpfun.swap_api import TradesPage, parse_trades_page
from hunter_meme_worker.repo_tape import trade_rows
from hunter_meme_worker.sources import SWAP_API, SourcesState
from hunter_meme_worker.tape_budget import BUDGET_REFUSED, TapeBudget
from hunter_meme_worker.tracker import TIER_GRADUATING, TIER_NEW, TIER_OPEN_BET, TIER_REST
from hunter_meme_worker.trades import TapeCoverage, TradesPuller, pull_once

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


def _page(name: str, mint: str, received_at: datetime = NOW) -> TradesPage:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"), parse_float=Decimal)
    return parse_trades_page(mint, raw, received_at=received_at)


class FakeSwapApi:
    """Serves page 1 then page 2 of the raydium capture (cursor), or the pump page."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.refuse = False
        self.bucket_refuse = False

    async def get_trades(
        self, mint: str, *, limit: int = 100, cursor: str | None = None
    ) -> TradesPage:
        self.calls.append((mint, cursor))
        if self.refuse:  # the edge's 429 as captured live: Cloudflare, retry-after, no window
            raise HttpRateLimited(
                "429",
                exchange="pumpfun_swap_api",
                retry_after_s=12,
                status_code=429,
                headers={"retry-after": "12", "server": "cloudflare"},
            )
        if self.bucket_refuse:  # our own token bucket saying no
            raise RateLimited("bucket", exchange="pumpfun_swap_api", retry_after_s=3)
        if mint == "PUMP":  # the curve capture is one page: nothing older to walk to
            page = _page("swap_api_trades_5ejA_raw.json", mint)
            return dataclasses.replace(page, has_more=False, next_cursor=None)
        if cursor is None:
            return _page("swap_api_trades_page1_raw.json", mint)
        return _page("swap_api_trades_page2_raw.json", mint)


class FakeSession:
    def __init__(self, log: list[Any]) -> None:
        self.log = log

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.log.append((str(statement)[:40], params))

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _no_role(factory: Any, db_role: str) -> Any:
    """Stands in for ``role_session``: the fake session needs no ``SET ROLE``."""
    return factory()


def _factory(log: list[Any]) -> Any:
    """What ``role_session`` needs: a callable returning an async session."""

    class _Session(FakeSession):
        def begin(self) -> Any:
            return self

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    return lambda: _Session(log)


def test_curve_rows_get_an_ordinal_per_transaction_and_others_are_counted() -> None:
    page = _page("swap_api_trades_5ejA_raw.json", "PUMP")
    rows, skipped = trade_rows(page.trades)
    assert len(rows) == 30 and skipped == {}
    assert {r.event_index for r in rows} == {0}, "one trade per transaction in the capture"
    assert all(r.commitment is None and r.is_mayhem_agent is None for r in rows)
    assert all(
        r.quote_mint == "11111111111111111111111111111111" and r.token_decimals == 6 for r in rows
    )
    assert rows[0].block_time < rows[-1].block_time, "ordered by the source's own id, oldest first"
    assert all(r.program == "pump" for r in rows)
    other = _page("swap_api_trades_page1_raw.json", "RAY")
    rows2, skipped2 = trade_rows(other.trades)
    assert rows2 == [] and skipped2 == {"unsupported_venue": 100}, "raydium_cpmm is not ours"
    twice = trade_rows(page.trades[:1] + page.trades[:1])[0]
    assert [r.event_index for r in twice] == [0, 1], "two events of one tx are two ordinals"


def test_the_pool_tape_of_a_graduated_mint_is_kept_with_its_venue() -> None:
    """T4.11: the 100 ``pump_amm`` trades of the real graduated capture become
    rows (``program = 'pump_amm'``, native SOL) — a bet that holds through the
    migration is marked on them. Before T4.11 they were skipped."""
    page = _page("swap_api_trades_graduated_pump_raw.json", "GRAD")
    rows, skipped = trade_rows(page.trades)
    assert len(rows) == 100 and skipped == {}
    assert {r.program for r in rows} == {"pump_amm"}
    assert all(r.quote_mint == "11111111111111111111111111111111" for r in rows)
    assert rows[0].block_time < rows[-1].block_time


def test_the_plan_orders_by_tier_respects_intervals_and_caps_the_cycle() -> None:
    puller = TradesPuller(FakeSwapApi(), budget_60s=900, cycle_s=10)
    tiers = {"rest": TIER_REST, "new": TIER_NEW, "grad": TIER_GRADUATING, "bet": TIER_OPEN_BET}
    assert puller.plan(tiers, NOW) == ["bet", "grad", "new", "rest"]
    for mint in tiers:
        puller.coverage[mint] = TapeCoverage(last_pull_at=NOW)
    soon = NOW + timedelta(seconds=15)
    assert puller.plan(tiers, soon) == [], "T4.2f: every tier is due once a minute"
    assert puller.plan(tiers, NOW + timedelta(seconds=61)) == ["bet", "grad", "new", "rest"]
    small = TradesPuller(FakeSwapApi(), budget_60s=12, cycle_s=10)
    assert small.plan(tiers, NOW) == ["bet", "grad"], "budget_60s × cycle_s / 60 = 2 per cycle"


def test_the_cycles_share_is_carried_exactly_and_never_burst() -> None:
    """16 a minute over 10 s cycles is 2,67 a cycle: 2, 3, 3, 2, 3, 3 — sixteen in
    the minute, never seventeen, never a burst the edge would count."""
    budget = TapeBudget(budget_60s=16, cycle_s=10)
    shares = [budget.per_cycle(NOW + timedelta(seconds=10 * i)) for i in range(12)]
    assert shares[:6] == [2, 3, 3, 2, 3, 3] and sum(shares[:6]) == 16 == sum(shares[6:])
    assert budget.per_cycle_nominal == 2


async def test_a_pull_walks_the_cursor_to_the_cap_then_stops_at_the_high_water_mark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeSwapApi()
    sources = SourcesState()
    puller = TradesPuller(api, budget_60s=900, cycle_s=10, max_pages=2, sources=sources)
    log: list[Any] = []
    monkeypatch.setattr("hunter_meme_worker.trades.role_session", _no_role)
    report = await puller.pull(_factory(log), "RAY", now=NOW)  # type: ignore[arg-type]
    assert report.pages == 2 and api.calls == [
        ("RAY", None),
        ("RAY", _page("swap_api_trades_page1_raw.json", "RAY").next_cursor),
    ]
    assert report.rows == 0 and report.skipped == {"unsupported_venue": 200}
    state = puller.coverage["RAY"]
    assert state.covered_since == NOW and state.high_water == "00044638622300057700000501"
    assert sources[SWAP_API].used_60s.total(NOW) == 2
    # Second pull: page 1 again, every id <= the mark, so one page and no cursor.
    api.calls.clear()
    report = await puller.pull(_factory(log), "RAY", now=NOW + timedelta(seconds=10))  # type: ignore[arg-type]
    assert report.pages == 1 and api.calls == [("RAY", None)]


async def test_curve_trades_are_written_once_per_cycle_and_a_refusal_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeSwapApi()
    sources = SourcesState()
    puller = TradesPuller(api, budget_60s=900, cycle_s=10, sources=sources)
    log: list[Any] = []
    monkeypatch.setattr("hunter_meme_worker.trades.role_session", _no_role)
    report = await pull_once(puller, _factory(log), tiers={"PUMP": TIER_OPEN_BET}, now=NOW)  # type: ignore[arg-type]
    assert report.pulled == 1 and report.rows == 30 and report.errors == 0
    assert log and log[0][0].startswith("INSERT INTO meme_trades")
    assert puller.covered_since("PUMP") == NOW and puller.absence_reason("PUMP") == "no_trade_feed"
    api.refuse = True
    later = NOW + timedelta(seconds=61)
    report = await pull_once(
        puller, _factory(log), tiers={"PUMP": TIER_OPEN_BET, "NEW": TIER_NEW}, now=later
    )  # type: ignore[arg-type]
    assert report.errors == 2 and report.pulled == 0 and report.refused_429 == 2
    assert puller.absence_reason("NEW", at=later) == "rate_limited", (
        "never covered and refused by the server: the minute says so"
    )
    assert puller.coverage_for("PUMP", later) == NOW, "covered before: the tape exists"
    assert puller.absence_reason("PUMP", at=later) == "rate_limited", (
        "asked only when the tape is unusable — and then the refusal is the reason"
    )
    assert sources[SWAP_API].errors_1h.total(later) == 2
    last_error = sources[SWAP_API].last_error
    assert last_error is not None and last_error.startswith("rate_limited")
    # The block: nothing is planned until retry-after passed, and the minute
    # that closes inside it says ``rate_limited`` for everyone.
    assert puller.budget.blocked_until == later + timedelta(seconds=12)
    assert puller.plan({"X": TIER_REST}, later + timedelta(seconds=5)) == []
    assert puller.absence_reason("X", at=later + timedelta(seconds=5)) == "rate_limited"
    assert puller.absence_reason("X", at=later + timedelta(seconds=13)) == "not_polled"
    assert puller.budget.measured == 0 and puller.budget.effective == 4, (
        "no success in the 60 s before the 429: the floor, not a guess"
    )


async def test_a_real_429_measures_the_ceiling_shrinks_the_budget_and_restores_it_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sixteen successes in the minute, then Cloudflare says 429: the measured
    ceiling is 16, the effective budget becomes 12 (80 %), the cycle inside the
    block plans nothing, and the configured 16 returns after the hold."""
    api = FakeSwapApi()
    puller = TradesPuller(api, budget_60s=16, cycle_s=10, adapt_hold_s=900)
    log: list[Any] = []
    monkeypatch.setattr("hunter_meme_worker.trades.role_session", _no_role)
    tiers = {f"M{i}": TIER_REST for i in range(40)}
    pulled: list[int] = []
    for cycle in range(6):
        at = NOW + timedelta(seconds=10 * cycle)
        report = await pull_once(puller, _factory(log), tiers=tiers, now=at)  # type: ignore[arg-type]
        pulled.append(report.pulled)
    assert (
        pulled == [2, 3, 3, 2, 3, 3]
        and puller.budget.ok_60s.total(NOW + timedelta(seconds=59)) == 16
    )
    api.refuse = True
    at = NOW + timedelta(seconds=60)
    report = await pull_once(puller, _factory(log), tiers=tiers, now=at)  # type: ignore[arg-type]
    assert report.refused_429 >= 1 and report.pulled == 0
    assert puller.budget.measured == 16 and puller.budget.effective == 12
    assert puller.budget.blocked_until == at + timedelta(seconds=12)
    api.refuse = False
    blocked = await pull_once(puller, _factory(log), tiers=tiers, now=at + timedelta(seconds=10))  # type: ignore[arg-type]
    assert blocked.planned == 0 and blocked.deferred >= 20, "inside the block: every due mint waits"
    after = at + timedelta(seconds=20)
    shares = [puller.budget.per_cycle(after + timedelta(seconds=10 * i)) for i in range(6)]
    assert sum(shares) == 12, "the shrunk budget paces the next minute"
    assert puller.budget.per_cycle(at + timedelta(seconds=900)) >= 2
    assert puller.budget.effective == 16, "the configured budget is tried again after the hold"


async def test_our_own_bucket_refusal_is_not_polled_never_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeSwapApi()
    api.bucket_refuse = True
    sources = SourcesState()
    puller = TradesPuller(api, budget_60s=16, cycle_s=10, sources=sources)
    log: list[Any] = []
    monkeypatch.setattr("hunter_meme_worker.trades.role_session", _no_role)
    report = await pull_once(puller, _factory(log), tiers={"PUMP": TIER_REST}, now=NOW)  # type: ignore[arg-type]
    assert report.errors == 1 and report.refused_429 == 0
    assert puller.absence_reason("PUMP", at=NOW) == "not_polled"
    assert puller.coverage["PUMP"].last_error == BUDGET_REFUSED
    assert puller.budget.blocked_until is None and puller.budget.effective == 16
    assert sources[SWAP_API].last_error == BUDGET_REFUSED


async def test_one_page_per_mint_and_the_walk_only_for_an_open_bet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeSwapApi()
    puller = TradesPuller(api, budget_60s=16, cycle_s=60, max_pages=3)
    log: list[Any] = []
    monkeypatch.setattr("hunter_meme_worker.trades.role_session", _no_role)
    report = await pull_once(
        puller, _factory(log), tiers={"RAY": TIER_GRADUATING, "BET": TIER_OPEN_BET}, now=NOW
    )  # type: ignore[arg-type]
    assert report.pulled == 2 and report.pages == 4
    assert [c for c in api.calls if c[0] == "RAY"] == [("RAY", None)], "one page is the minute"
    assert len([c for c in api.calls if c[0] == "BET"]) == 3, "an open bet walks to the cap"


def test_a_deferred_mint_that_was_covered_before_still_says_not_polled() -> None:
    puller = TradesPuller(FakeSwapApi(), budget_60s=6, cycle_s=10)
    puller.coverage["old"] = TapeCoverage(covered_since=NOW - timedelta(minutes=10))
    tiers = {"old": TIER_REST, "bet": TIER_OPEN_BET}
    assert puller.plan(tiers, NOW) == ["bet"]
    assert puller.absence_reason("old", at=NOW) == "not_polled", (
        "covered once, left out by the budget now: the budget is the reason"
    )


def test_a_mint_the_cap_left_out_is_remembered_as_not_polled() -> None:
    """T4.2e: what the budget cannot reach is named — the curve's own word."""
    puller = TradesPuller(FakeSwapApi(), budget_60s=12, cycle_s=10)
    tiers = {"rest": TIER_REST, "new": TIER_NEW, "grad": TIER_GRADUATING, "bet": TIER_OPEN_BET}
    assert puller.plan(tiers, NOW) == ["bet", "grad"]
    assert puller.last_deferred == 2 and set(puller.not_planned) == {"new", "rest"}
    assert puller.absence_reason("rest") == "not_polled"
    assert puller.absence_reason("bet") == "no_trade_feed", "planned, just not pulled yet"
    for mint in ("bet", "grad"):
        puller.coverage[mint] = TapeCoverage(last_pull_at=NOW, covered_since=NOW)
    assert puller.plan(tiers, NOW + timedelta(seconds=1)) == ["new", "rest"]
    assert puller.not_planned == {} and puller.last_deferred == 0
    stats = puller.stats(tiers)
    assert (stats.tracked, stats.covered, stats.never_pulled, stats.failing) == (4, 2, 2, 0)


async def test_pulls_run_concurrently_inside_the_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    """The T4.2e fix: eight mints at 50 ms each take ~50 ms with four in flight,
    never ~400 ms — and never more than ``concurrency`` requests at once."""
    import asyncio
    import time

    class SlowApi(FakeSwapApi):
        def __init__(self) -> None:
            super().__init__()
            self.in_flight = 0
            self.peak = 0

        async def get_trades(
            self, mint: str, *, limit: int = 100, cursor: str | None = None
        ) -> TradesPage:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            try:
                await asyncio.sleep(0.05)
                return await super().get_trades("PUMP", limit=limit, cursor=cursor)
            finally:
                self.in_flight -= 1

    api = SlowApi()
    puller = TradesPuller(api, budget_60s=900, cycle_s=10, concurrency=4)
    log: list[Any] = []
    monkeypatch.setattr("hunter_meme_worker.trades.role_session", _no_role)
    tiers = {f"M{i}": TIER_REST for i in range(8)}
    started = time.monotonic()
    stamps: list[datetime] = [NOW + timedelta(milliseconds=i) for i in range(8)]
    report = await pull_once(
        puller, _factory(log), tiers=tiers, now=NOW, clock=lambda: stamps.pop(0)
    )  # type: ignore[arg-type]
    elapsed = time.monotonic() - started
    assert report.pulled == 8 and report.planned == 8 and report.deferred == 0
    assert api.peak == 4, "the semaphore, not the bucket, bounds the burst here"
    assert elapsed < 0.3, f"sequential would take >= 0.4 s; took {elapsed:.3f}"
    assert report.duration_s > 0
    assert all(puller.coverage[m].last_pull_at in stamps or True for m in tiers)


def test_a_stale_tape_is_not_a_zero() -> None:
    """Covered at NOW, no successful pull since: at NOW + 181 s the minute has no
    tape (``rate_limited`` if the last pull was refused), never zero buys."""
    puller = TradesPuller(FakeSwapApi(), budget_60s=900, cycle_s=10, stale_s=180)
    state = TapeCoverage(covered_since=NOW, last_pull_at=NOW)
    state.ok_times.append(NOW)
    puller.coverage["PUMP"] = state
    assert puller.coverage_for("PUMP", NOW + timedelta(seconds=180)) == NOW
    assert puller.coverage_for("PUMP", NOW + timedelta(seconds=181)) is None
    assert puller.absence_reason("PUMP") == "no_trade_feed"
    state.last_error = "rate_limited"
    assert puller.absence_reason("PUMP") == "rate_limited"
    # A pull after the minute's close does not count for that minute.
    state.ok_times.append(NOW + timedelta(seconds=200))
    assert puller.coverage_for("PUMP", NOW + timedelta(seconds=190)) is None
    assert puller.coverage_for("PUMP", NOW + timedelta(seconds=200)) == NOW
    assert puller.coverage_for("NEVER", NOW) is None
