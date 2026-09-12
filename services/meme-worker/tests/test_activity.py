# pyright: reportPrivateUsage=false
"""T4.2g — the tape by batch (``activity.py``, ``repo_activity.py``,
``features_tape.activity_minute``): 130 coins become three requests of 50
reserved off the tape's budget; a ``null`` window is a stated zero only in
a cycle that filled it for someone, dark otherwise; a real 429 measures,
shrinks, blocks and skips the next cycle; USD becomes SOL only with a quote
and says ``no_sol_quote`` without; the fold prefers the per-mint tape and
falls back to the batch with its provenance on both series; a reading that
reached us after the instant is not its tape; the loop fires ``lead_s``
before the minute. No socket, no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.market_activity import (
    ActivityBatch,
    NormalizedMarketActivity,
    parse_activity_batch,
)
from hunter_exchanges.pumpfun.models import NormalizedSolPrice
from hunter_exchanges.pumpfun.rate_shared import HttpRateLimited
from hunter_meme_worker import activity as activity_module
from hunter_meme_worker.activity import (
    ActivityPuller,
    activity_mints,
    batch_minute,
    seconds_until_fire,
)
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.features import NO_TRADE_FEED, MinuteInputs, build_row
from hunter_meme_worker.features_fast import FastInputs, build_fast_row
from hunter_meme_worker.features_tape import (
    ACTIVITY_1M,
    NO_SOL_QUOTE,
    SWAP_API_TRADES,
    ActivityReading,
    TapeTrade,
    activity_for,
    activity_minute,
    tape_for,
)
from hunter_meme_worker.repo_activity import SolQuote, activity_rows
from hunter_meme_worker.sources import SWAP_API, SWAP_API_ACTIVITY, SourcesState
from hunter_meme_worker.tape_budget import TapeBudget
from hunter_meme_worker.tracker import MintTracker, TrackedMint

from .test_chain import _no_role, _Session

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 12, 20, 24, 57, tzinfo=UTC)
STAMP = NOW - timedelta(seconds=1)
MINUTE = datetime(2026, 9, 12, 20, 25, tzinfo=UTC)
QUOTE = SolQuote(price_usd=Decimal("200"), observed_at=NOW - timedelta(seconds=20))
LIVE_BLOCK: dict[str, Any] = {
    "numTxs": 5,
    "volumeUSD": Decimal("120.5"),
    "numUsers": 4,
    "numBuys": 3,
    "numSells": 2,
    "buyVolumeUSD": Decimal("80.5"),
    "sellVolumeUSD": Decimal("40"),
    "numBuyers": 3,
    "numSellers": 2,
    "priceChangePercent": Decimal("12.5"),
}


class FakeSwapApi:
    """Answers a batch like the route: ``null`` for every window unless the
    coin is in ``live`` (then ``LIVE_BLOCK`` for ``1m``); the same request
    shape the client sends, the same ceiling of 50."""

    def __init__(self, *, live: set[str] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.live = live or set()
        self.refuse: Exception | None = None
        self.refuse_on_call: int | None = None

    async def market_activity_batch(
        self, mints: Any, *, windows: Any = ("1m", "5m")
    ) -> ActivityBatch:
        assert 1 <= len(mints) <= 50
        self.calls.append(list(mints))
        if self.refuse is not None and (
            self.refuse_on_call is None or self.refuse_on_call == len(self.calls)
        ):
            raise self.refuse
        raw = {
            mint: {
                w: (dict(LIVE_BLOCK) if mint in self.live and w == "1m" else None) for w in windows
            }
            for mint in mints
        }
        return parse_activity_batch(
            raw, mints=mints, windows=windows, observed_at=STAMP, received_at=NOW
        )


class FakeQuotes:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def get_sol_price(self) -> NormalizedSolPrice:
        self.calls += 1
        if self.fail:
            raise RuntimeError("quote down")
        return NormalizedSolPrice(
            price_usd=Decimal("200"),
            as_of=NOW - timedelta(seconds=30),
            stale=False,
            observed_at=NOW - timedelta(seconds=20),
            received_at=NOW - timedelta(seconds=20),
        )


def _puller(
    client: FakeSwapApi, *, quotes: FakeQuotes | None = None, budget_60s: int = 16
) -> tuple[ActivityPuller, SourcesState, TapeBudget]:
    sources = SourcesState()
    budget = TapeBudget(budget_60s=budget_60s, cycle_s=10.0)
    puller = ActivityPuller(client, budget=budget, quotes=quotes or FakeQuotes(), sources=sources)
    return puller, sources, budget


def _factory(log: list[Any]) -> Any:
    return lambda: _Session(log)


def _reading(
    mint: str = "M",
    *,
    end_time: datetime = STAMP,
    received_at: datetime = NOW,
    quote: SolQuote | None = QUOTE,
    empty: bool = False,
) -> ActivityReading:
    return ActivityReading(
        mint=mint,
        end_time=end_time,
        received_at=received_at,
        window_s=60,
        buys=0 if empty else 3,
        sells=0 if empty else 2,
        unique_buyers=0 if empty else 3,
        buy_volume_usd=Decimal(0) if empty else Decimal("80.5"),
        sell_volume_usd=Decimal(0) if empty else Decimal("40"),
        sol_usd=None if quote is None else quote.price_usd,
        sol_usd_observed_at=None if quote is None else quote.observed_at,
        empty=empty,
    )


async def test_a_dark_window_writes_nothing_and_a_live_one_makes_every_null_a_stated_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activity_module, "role_session", _no_role)
    mints = [f"MINT{i:03d}" for i in range(130)]
    log: list[Any] = []
    client = FakeSwapApi()
    puller, sources, budget = _puller(client)
    report = await puller.pull_once(_factory(log), mints, now=NOW)
    assert [len(c) for c in client.calls] == [50, 50, 30], "50 a request, the measured ceiling"
    assert report.asked == 130 and report.calls == 3 and report.errors == 0
    assert report.rows == 0 and report.covered == 0 and report.dark == 130
    assert report.live == {} and log == [], "nobody's 1m was filled: no zero is claimed"
    assert budget.reserved == 3 and budget.available == 13, "three off the top of sixteen"
    assert puller.reading_for("MINT000", at=MINUTE) is None
    fields = sources.heartbeat_fields(MINUTE, tracked=130)
    assert fields["activity_dark_60s"] == "130" and fields["activity_live_1m"] == "0"
    assert fields["activity_coverage_pct"] == "0.0" and fields["activity_batch_calls_60s"] == "3"
    assert sources[SWAP_API].used_60s.total(MINUTE) == 3, "the edge's budget counts the batch"
    assert sources[SWAP_API_ACTIVITY].used_60s.total(MINUTE) == 3

    client = FakeSwapApi(live={"MINT007", "MINT099"})
    puller, sources, budget = _puller(client)
    report = await puller.pull_once(_factory(log), mints, now=NOW)
    assert report.live == {"1m": 2} and report.dark == 0 and report.covered == 130
    assert report.rows == 130, "two numbers and 128 stated zeros for 1m; 5m stays dark"
    rows = log[0][1]
    assert log[0][0].startswith("INSERT INTO meme_market_activity_1m")
    by_mint = {r["mint"]: r for r in rows}
    assert all(r["window_name"] == "1m" and r["window_s"] == 60 for r in rows)
    live = by_mint["MINT007"]
    assert (live["buys"], live["sells"], live["unique_buyers"], live["empty"]) == (3, 2, 3, False)
    assert live["buy_volume_usd"] == Decimal("80.5") and live["sol_usd"] == Decimal("200")
    assert live["buy_volume_sol"] == Decimal("0.4025") and live["sell_volume_sol"] == Decimal("0.2")
    assert live["end_time"] == STAMP and live["received_at"] == NOW
    zero = by_mint["MINT000"]
    assert zero["empty"] is True and zero["buys"] == 0 and zero["price_change_pct"] is None
    assert zero["buy_volume_sol"] == 0 and zero["sol_usd"] == Decimal("200")
    reading = puller.reading_for("MINT000", at=MINUTE)
    assert reading is not None and reading.empty and reading.end_time == STAMP
    fields = sources.heartbeat_fields(MINUTE, tracked=130)
    assert fields["activity_coverage_pct"] == "100.0" and fields["activity_live_1m"] == "2"
    assert fields["activity_quote_age_s"] == "20.0"


async def test_a_real_429_measures_shrinks_blocks_and_the_next_cycle_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activity_module, "role_session", _no_role)
    mints = [f"MINT{i:03d}" for i in range(80)]
    client = FakeSwapApi(live={"MINT001"})
    client.refuse = HttpRateLimited(
        "429",
        exchange="pumpfun_swap_api",
        retry_after_s=60,
        status_code=429,
        headers={"retry-after": "60", "server": "cloudflare"},
    )
    client.refuse_on_call = 2
    puller, sources, budget = _puller(client)
    log: list[Any] = []
    report = await puller.pull_once(_factory(log), mints, now=NOW)
    assert report.calls == 2 and report.errors == 1 and report.refused_429 == 1
    assert report.covered == 50, "the first chunk landed; the second was the edge's no"
    assert budget.blocked_until == NOW + timedelta(seconds=60) and budget.per_cycle(NOW) == 0
    assert sources[SWAP_API].last_error == "rate_limited:60s"
    assert sources[SWAP_API_ACTIVITY].errors_1h.total(NOW) == 1
    later = NOW + timedelta(seconds=30)
    skipped = await puller.pull_once(_factory(log), mints, now=later)
    assert skipped.skipped == "blocked" and skipped.calls == 0 and len(client.calls) == 2
    assert sources.heartbeat_fields(later, tracked=80)["activity_skipped_60s"] == "1"
    client.refuse = RateLimited("bucket", exchange="pumpfun_swap_api", retry_after_s=3)
    client.refuse_on_call = None
    after = NOW + timedelta(seconds=61)
    own = await puller.pull_once(_factory(log), mints, now=after)
    assert own.errors == 1 and own.refused_429 == 0 and budget.blocked_at(after) is False
    assert sources[SWAP_API_ACTIVITY].last_error == "budget_refused"
    empty = await puller.pull_once(_factory(log), [], now=after)
    assert empty.skipped == "no_mints" and budget.reserved == 0


async def test_without_a_quote_the_sol_columns_are_null_and_the_minute_says_no_sol_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(activity_module, "role_session", _no_role)
    client = FakeSwapApi(live={"A"})
    quotes = FakeQuotes(fail=True)
    puller, _, _ = _puller(client, quotes=quotes)
    log: list[Any] = []
    report = await puller.pull_once(_factory(log), ["A", "B"], now=NOW)
    assert report.rows == 2 and puller.quote is None and puller.quote_error == "RuntimeError"
    row = {r["mint"]: r for r in log[0][1]}["A"]
    assert row["sol_usd"] is None and row["buy_volume_sol"] is None
    assert row["buy_volume_usd"] == Decimal("80.5"), "the USD the route said stays"
    reading = puller.reading_for("A", at=MINUTE)
    assert reading is not None and reading.sol_usd is None
    assert activity_minute(reading) is None
    tracker = MintTracker(window_minutes=1440, cap=10)
    ctx = RadarContext(
        config=MemeConfig(),
        session_factory=None,  # type: ignore[arg-type]
        tracker=tracker,
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
        activity=puller,
    )
    minute, reason = batch_minute(ctx, "A", at=MINUTE, absence="not_polled")
    assert minute is None and reason == NO_SOL_QUOTE
    minute, reason = batch_minute(ctx, "ZZZ", at=MINUTE, absence="not_polled")
    assert minute is None and reason == "not_polled", "no reading: the tape's own reason stands"
    # A quote that comes back is used, and a stale one is kept for five minutes, no longer.
    quotes.fail = False
    quote = await puller.sol_usd(NOW)
    assert quote is not None and quote.price_usd == Decimal("200") and quotes.calls == 2
    quotes.fail = True
    assert await puller.sol_usd(NOW + timedelta(seconds=279)) is not None, "299 s old: kept"
    assert await puller.sol_usd(NOW + timedelta(seconds=281)) is None, "301 s old: gone"


def test_usd_becomes_sol_with_the_quote_and_the_creator_stays_unknown() -> None:
    minute = activity_minute(_reading())
    assert minute is not None
    assert (minute.buys, minute.sells, minute.unique_buyers) == (3, 2, 3)
    assert minute.net_sol_flow == Decimal("0.2025") and minute.volume_sol == Decimal("0.6025")
    assert minute.creator_sold is None and minute.creator_net_seller is None
    assert minute.source == ACTIVITY_1M and minute.window_s == 60 and minute.as_of == STAMP
    zero = activity_minute(_reading(empty=True))
    assert zero is not None and zero.buys == 0 and zero.net_sol_flow == 0
    rows, dark = activity_rows(
        [
            ActivityBatch(
                readings=(
                    NormalizedMarketActivity(
                        mint="A",
                        window="5m",
                        window_s=300,
                        num_txs=1,
                        buys=1,
                        sells=0,
                        unique_users=1,
                        unique_buyers=1,
                        unique_sellers=0,
                        volume_usd=Decimal(10),
                        buy_volume_usd=Decimal(10),
                        sell_volume_usd=Decimal(0),
                        price_change_pct=None,
                        observed_at=STAMP,
                        received_at=NOW,
                    ),
                ),
                empty={"1m": ("A", "B"), "5m": ("B",)},
                windows_live=frozenset({"5m"}),
                observed_at=STAMP,
                received_at=NOW,
            )
        ],
        quote=None,
    )
    assert [(r.mint, r.window_name, r.empty) for r in rows] == [
        ("A", "5m", False),
        ("B", "5m", True),
    ]
    assert dark == {"1m": 2}, "1m unfilled for everyone: dark, not zero"


def test_the_minute_prefers_the_per_mint_tape_and_falls_back_to_the_batch_with_provenance() -> None:
    trade = TapeTrade(
        block_time=MINUTE - timedelta(seconds=30),
        received_at=MINUTE - timedelta(seconds=25),
        trader="CREATOR",
        side="sell",
        sol_lamports=1_000_000_000,
    )
    own = tape_for(
        [trade], end_time=MINUTE, creator="CREATOR", covered_since=MINUTE - timedelta(minutes=5)
    )
    assert own is not None and own.source == SWAP_API_TRADES and own.as_of == MINUTE
    inputs = MinuteInputs(
        mint="A", end_time=MINUTE, created_at=None, initial_real_token_reserves=None, snapshot=None
    )
    from dataclasses import replace

    from_tape = build_row(replace(inputs, tape=own))
    assert (from_tape.tape_source, from_tape.tape_window_s, from_tape.tape_as_of) == (
        SWAP_API_TRADES,
        60,
        MINUTE,
    )
    assert from_tape.creator_net_seller is True and from_tape.creator_net_seller_reason is None
    batch = activity_minute(_reading("A"))
    from_batch = build_row(replace(inputs, tape=batch))
    assert (from_batch.tape_source, from_batch.tape_window_s, from_batch.tape_as_of) == (
        ACTIVITY_1M,
        60,
        STAMP,
    )
    assert (from_batch.buys_1m, from_batch.sells_1m, from_batch.unique_buyers) == (3, 2, 3)
    assert from_batch.net_sol_flow_1m == Decimal("0.2025") and from_batch.tape_reason is None
    assert from_batch.creator_net_seller is None
    assert from_batch.creator_net_seller_reason == NO_TRADE_FEED, "the batch never says who sold"
    assert from_batch.creator_sold is None and from_batch.creator_sold_reason == NO_TRADE_FEED
    without = build_row(replace(inputs, tape=None, tape_absence_reason=NO_SOL_QUOTE))
    assert without.tape_source is None and without.tape_as_of is None
    assert without.tape_reason == NO_SOL_QUOTE and without.buys_1m is None
    fast = build_fast_row(
        FastInputs(
            mint="A",
            as_of=MINUTE,
            created_at=MINUTE - timedelta(seconds=90),
            initial_real_token_reserves=None,
            points=[],
            snapshot_source=None,
            tape=batch,
        )
    )
    assert (fast.tape_source, fast.tape_window_s, fast.tape_as_of) == (ACTIVITY_1M, 60, STAMP)
    assert (fast.buys_60s, fast.sells_60s, fast.unique_buyers_60s) == (3, 2, 3)
    assert fast.creator_net_seller_reason == NO_TRADE_FEED and fast.tape_reason is None


def test_a_reading_received_after_the_instant_or_older_than_a_minute_is_not_its_tape() -> None:
    early = _reading(
        end_time=MINUTE - timedelta(seconds=63), received_at=MINUTE - timedelta(seconds=62)
    )
    fresh = _reading(
        end_time=MINUTE - timedelta(seconds=3), received_at=MINUTE - timedelta(seconds=2)
    )
    late = _reading(
        end_time=MINUTE + timedelta(seconds=57), received_at=MINUTE + timedelta(seconds=58)
    )
    assert activity_for([early, fresh, late], at=MINUTE, max_age_s=60) is fresh
    assert activity_for([early, late], at=MINUTE, max_age_s=60) is None, (
        "one window ended over a minute before, the other reached us after the close"
    )
    assert activity_for([early], at=MINUTE, max_age_s=120) is early
    stamped_after = _reading(end_time=MINUTE + timedelta(seconds=1), received_at=MINUTE)
    assert activity_for([stamped_after], at=MINUTE, max_age_s=60) is stamped_after, (
        "the server's second-precision stamp may sit a moment ahead; receipt decides"
    )


def test_the_loop_fires_lead_seconds_before_every_minute_and_never_at_once() -> None:
    base = datetime(2026, 9, 12, 20, 24, 0, tzinfo=UTC)
    assert seconds_until_fire(base, cycle_s=60, lead_s=3) == pytest.approx(57.0)
    assert seconds_until_fire(base + timedelta(seconds=56), cycle_s=60, lead_s=3) == pytest.approx(
        1.0
    )
    assert seconds_until_fire(base + timedelta(seconds=57), cycle_s=60, lead_s=3) == pytest.approx(
        60.0
    ), "at the instant itself the next grid point is a full cycle away"
    assert seconds_until_fire(base + timedelta(seconds=58), cycle_s=60, lead_s=3) == pytest.approx(
        59.0
    )
    assert seconds_until_fire(base + timedelta(seconds=10), cycle_s=30, lead_s=3) == pytest.approx(
        17.0
    )


def test_the_batch_asks_for_every_coin_on_the_curve_quoted_in_sol() -> None:
    tracker = MintTracker(window_minutes=1440, cap=50)
    t0 = NOW - timedelta(minutes=5)
    for t in (
        TrackedMint(mint="young", first_seen_at=t0, created_at=t0),
        TrackedMint(mint="usdc", first_seen_at=t0, created_at=t0, quote_unsupported=True),
        TrackedMint(mint="done", first_seen_at=t0, created_at=t0, complete=True),
        TrackedMint(mint="gone", first_seen_at=t0, created_at=t0, migrated=True),
        TrackedMint(mint="ageless", first_seen_at=t0),
    ):
        tracker.observe(t)
    assert sorted(activity_mints(tracker)) == ["ageless", "young"]
