"""Pure resolution rules of ``derivatives.py`` — no Postgres, no Redis.

Astra's S2-context review named two composite-observation traps: an OI row
whose durable ``ts`` is a poll-round bucket rather than the reading's own
instant, and a realized funding settlement's hot-state write leaving an
unrelated mark price behind it. Both are exercised here against the pure
resolvers, ahead of the integration tests that go through real IO.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import MarketStatus
from hunter_strategy_worker.derivatives import (
    _resolve_funding,  # pyright: ignore[reportPrivateUsage]
    _resolve_open_interest,  # pyright: ignore[reportPrivateUsage]
)
from hunter_strategy_worker.hot_state import DerivRaw
from hunter_strategy_worker.repo import FundingRow, MarketRow, OpenInterestRow

pytestmark = pytest.mark.unit

MARKET = MarketRow(
    id=uuid.UUID(int=1),
    symbol="BTCUSDT",
    exchange="binance",
    is_monitored=True,
    status=MarketStatus.ACTIVE,
)
CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
EMPTY_RAW = DerivRaw(
    funding_rate=None,
    funding_kind=None,
    funding_ts=None,
    mark_price=None,
    mark_ts=None,
    open_interest=None,
    open_interest_ts=None,
)


class TestFunding:
    def test_a_complete_durable_row_is_used_as_realized(self) -> None:
        row = FundingRow(
            ts=CUT - timedelta(hours=1), rate=Decimal("0.0001"), mark_price=Decimal("100")
        )
        funding, source, reason = _resolve_funding(MARKET, row, None)
        assert funding is not None
        assert funding.funding_kind == "realized"
        assert funding.mark_price == Decimal("100")
        assert source == "durable"
        assert reason is None

    def test_a_durable_row_without_mark_price_falls_back_to_hot_state(self) -> None:
        row = FundingRow(ts=CUT - timedelta(hours=1), rate=Decimal("0.0001"), mark_price=None)
        raw = DerivRaw(
            funding_rate=Decimal("0.0002"),
            funding_kind="estimated",
            funding_ts=CUT - timedelta(minutes=1),
            mark_price=Decimal("101"),
            mark_ts=CUT - timedelta(minutes=1),
            open_interest=None,
            open_interest_ts=None,
        )
        funding, source, reason = _resolve_funding(MARKET, row, raw)
        assert funding is not None
        assert funding.funding_rate == Decimal("0.0002")
        assert funding.funding_kind == "estimated"
        assert source == "hot_state"
        assert reason is None

    def test_hot_state_refuses_to_pair_funding_with_an_unrelated_mark(self) -> None:
        """The trap from must-fix 2: a realized settlement write never touches
        the mark fields, so a stale/foreign mark price can still be sitting
        there with its own, different timestamp. Combining them would invent
        an observation that was never actually made together."""
        raw = DerivRaw(
            funding_rate=Decimal("0.0002"),
            funding_kind="realized",
            funding_ts=CUT - timedelta(minutes=1),
            mark_price=Decimal("101"),
            mark_ts=CUT - timedelta(hours=3),  # a much older, unrelated snapshot
            open_interest=None,
            open_interest_ts=None,
        )
        funding, source, reason = _resolve_funding(MARKET, None, raw)
        assert funding is None
        assert source is None
        assert reason == "no_mark_price"

    def test_nothing_anywhere_is_no_data(self) -> None:
        funding, source, reason = _resolve_funding(MARKET, None, EMPTY_RAW)
        assert funding is None
        assert source is None
        assert reason == "no_data"

    def test_no_row_and_no_hot_state_call_is_also_no_data(self) -> None:
        funding, source, reason = _resolve_funding(MARKET, None, None)
        assert (funding, source, reason) == (None, None, "no_data")


class TestOpenInterest:
    """``_resolve_open_interest`` never treats a durable row's ``ts`` as proof
    of ``<= cut`` (Astra, S2-context review round 2, must-fix 1 — a finite
    slack was tried and broken by a concrete counter-example: a poll round
    starting just before a bucket boundary can read a market strictly after
    the boundary while still writing the earlier bucket as ``ts``). Only the
    hot state's own ``oi_ts`` — the reading's real instant — is trusted."""

    def test_a_hot_state_reading_is_used_regardless_of_what_durable_has(self) -> None:
        row = OpenInterestRow(
            ts=CUT - timedelta(minutes=1), open_interest=Decimal("1000"), open_interest_value=None
        )
        raw = DerivRaw(
            funding_rate=None,
            funding_kind=None,
            funding_ts=None,
            mark_price=None,
            mark_ts=None,
            open_interest=Decimal("1200"),
            open_interest_ts=CUT - timedelta(seconds=5),
        )
        oi, source, reason = _resolve_open_interest(MARKET, row, raw)
        assert oi is not None
        assert oi.open_interest == Decimal("1200")
        assert source == "hot_state"
        assert reason is None

    def test_a_durable_row_alone_is_never_trusted_no_matter_how_old(self) -> None:
        """Even a durable row from a day ago is refused on its own: nothing
        about its ``ts`` distinguishes "safely old" from "the round that wrote
        it might still be running" without an assumption this module refuses
        to make (module docstring)."""
        row = OpenInterestRow(
            ts=CUT - timedelta(days=1), open_interest=Decimal("1000"), open_interest_value=None
        )
        oi, source, reason = _resolve_open_interest(MARKET, row, EMPTY_RAW)
        assert oi is None
        assert source is None
        assert reason == "timestamp_unprovable"

    def test_a_null_value_on_an_otherwise_unprovable_row_is_reported_distinctly(self) -> None:
        row = OpenInterestRow(
            ts=CUT - timedelta(days=1), open_interest=None, open_interest_value=None
        )
        oi, _source, reason = _resolve_open_interest(MARKET, row, EMPTY_RAW)
        assert oi is None
        assert reason == "no_open_interest_value"

    def test_nothing_anywhere_is_no_data(self) -> None:
        oi, source, reason = _resolve_open_interest(MARKET, None, EMPTY_RAW)
        assert (oi, source, reason) == (None, None, "no_data")
