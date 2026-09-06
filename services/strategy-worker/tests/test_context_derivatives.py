"""``build_market_context`` actually receiving funding/open interest —
notes-S2.md "o que o contexto da estratégia nunca recebe".

Against a real Postgres and a real Redis: the two holes the brief measured
were that ``StrategyContext.funding``/``.open_interest`` were always ``None``
in every evaluation. These tests prove the context now carries them, that
nothing from strictly after ``source_bar_close`` ever enters (the decision
already had by S1, extended here to the two new inputs), and that the
provenance records where each reading came from — or why there is none.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import redis.asyncio as redis_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.redis import keys
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.context import build_market_context
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    SYMBOL,
    insert_funding_rate,
    insert_open_interest,
    seed_market,
)

pytestmark = pytest.mark.integration

CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
CONFIG = ShadowConfig(context_minutes=30, hot_state_tail=5)


@pytest.fixture
async def market_ctx(db_session_factory: Any) -> dict[str, Any]:
    """A market with no candles: these tests are only about the funding/OI
    plumbing, and an empty ``candles_1m`` is a valid ``StrategyContext``.

    The underlying database is session-scoped (``migrated_db_url``), so the
    market from an earlier test in this file is reused (``seed_market`` is
    ``ON CONFLICT DO NOTHING``) — its ``funding_rates``/``open_interest_history``
    rows are cleared here so each test starts from a clean durable state, the
    same pattern ``test_shadow_decisions.py``'s ``shadow_db`` fixture uses.
    """
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        _exchange_id, market_id = await seed_market(session)
        await session.execute(
            text("DELETE FROM funding_rates WHERE market_id = :id"), {"id": market_id}
        )
        await session.execute(
            text("DELETE FROM open_interest_history WHERE market_id = :id"), {"id": market_id}
        )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    return {"factory": db_session_factory, "market": market, "market_id": market_id}


class TestFundingFromDurable:
    async def test_a_settlement_safely_before_the_cut_is_used(
        self, market_ctx: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            await insert_funding_rate(
                session,
                market_ctx["market_id"],
                funding_time=CUT - timedelta(hours=1),
                rate=Decimal("0.0001"),
                mark_price=Decimal("100"),
            )
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            ctx, provenance = await build_market_context(
                session,
                redis_client,
                market=market_ctx["market"],
                source_bar_close=CUT,
                config=CONFIG,
            )
        assert ctx.funding is not None
        assert ctx.funding.funding_rate == Decimal("0.0001")
        assert ctx.funding.funding_kind == "realized"
        assert provenance.funding_source == "durable"
        assert provenance.funding_ts == CUT - timedelta(hours=1)
        assert provenance.funding_reason is None

    async def test_a_settlement_one_second_after_the_cut_never_enters(
        self, market_ctx: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            await insert_funding_rate(
                session,
                market_ctx["market_id"],
                funding_time=CUT + timedelta(seconds=1),
                rate=Decimal("0.0001"),
                mark_price=Decimal("100"),
            )
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            ctx, provenance = await build_market_context(
                session,
                redis_client,
                market=market_ctx["market"],
                source_bar_close=CUT,
                config=CONFIG,
            )
        assert ctx.funding is None
        assert provenance.funding_ts is None
        assert provenance.funding_reason == "no_data"


class TestFundingFromHotState:
    async def test_an_estimated_snapshot_is_used_when_durable_has_nothing(
        self, market_ctx: dict[str, Any], redis_client: redis_asyncio.Redis
    ) -> None:
        key = keys.derivatives(EXCHANGE, SYMBOL)
        ts = (CUT - timedelta(minutes=2)).isoformat()
        await redis_client.hset(
            key,
            mapping={
                "funding_rate": "0.0003",
                "funding_kind": "estimated",
                "funding_ts": ts,
                "mark_price": "101.5",
                "mark_ts": ts,
            },
        )
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            ctx, provenance = await build_market_context(
                session,
                redis_client,
                market=market_ctx["market"],
                source_bar_close=CUT,
                config=CONFIG,
            )
        assert ctx.funding is not None
        assert ctx.funding.funding_rate == Decimal("0.0003")
        assert ctx.funding.mark_price == Decimal("101.5")
        assert provenance.funding_source == "hot_state"

    async def test_a_hot_state_reading_one_second_after_the_cut_never_enters(
        self, market_ctx: dict[str, Any], redis_client: redis_asyncio.Redis
    ) -> None:
        key = keys.derivatives(EXCHANGE, SYMBOL)
        ts = (CUT + timedelta(seconds=1)).isoformat()
        await redis_client.hset(
            key,
            mapping={
                "funding_rate": "0.0003",
                "funding_kind": "estimated",
                "funding_ts": ts,
                "mark_price": "101.5",
                "mark_ts": ts,
                "open_interest": "1234",
                "oi_ts": ts,
            },
        )
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            ctx, provenance = await build_market_context(
                session,
                redis_client,
                market=market_ctx["market"],
                source_bar_close=CUT,
                config=CONFIG,
            )
        assert ctx.funding is None
        assert ctx.open_interest is None
        assert provenance.funding_reason == "no_data"
        assert provenance.open_interest_reason == "no_data"

    async def test_a_rate_with_only_a_future_mark_is_refused_not_backfilled(
        self, market_ctx: dict[str, Any], redis_client: redis_asyncio.Redis
    ) -> None:
        """The funding rate itself is eligible (``funding_ts <= cut``), but the
        only mark price in the hash is from strictly after the cut — the mark
        group has its own, independent freshness gate
        (``hunter_market_worker/hot_state.py``), and this must not silently
        pair an eligible rate with an ineligible mark, nor invent one."""
        key = keys.derivatives(EXCHANGE, SYMBOL)
        eligible_ts = (CUT - timedelta(minutes=1)).isoformat()
        future_ts = (CUT + timedelta(seconds=1)).isoformat()
        await redis_client.hset(
            key,
            mapping={
                "funding_rate": "0.0003",
                "funding_kind": "estimated",
                "funding_ts": eligible_ts,
                "mark_price": "101.5",
                "mark_ts": future_ts,
                "open_interest": "1234",
                "oi_ts": eligible_ts,
            },
        )
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            ctx, provenance = await build_market_context(
                session,
                redis_client,
                market=market_ctx["market"],
                source_bar_close=CUT,
                config=CONFIG,
            )
        assert ctx.funding is None
        assert provenance.funding_reason == "no_mark_price"
        # the open interest group is independent and still eligible
        assert ctx.open_interest is not None
        assert ctx.open_interest.open_interest == Decimal("1234")


class TestOpenInterest:
    """A durable-only sample is never trusted, no matter how old (Astra,
    S2-context review round 2, must-fix 1): its ``ts`` is a poll-round bucket
    start, not the reading's own instant, and no finite margin closes that gap
    (a concrete 3-second counter-example broke the first, slack-based
    attempt). Only the hot state's own ``oi_ts`` is trusted."""

    async def test_a_durable_only_sample_is_never_used_no_matter_how_old(
        self, market_ctx: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            await insert_open_interest(
                session,
                market_ctx["market_id"],
                ts=CUT - timedelta(days=1),
                open_interest=Decimal("5000"),
                open_interest_value=Decimal("500000"),
            )
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            ctx, provenance = await build_market_context(
                session,
                redis_client,
                market=market_ctx["market"],
                source_bar_close=CUT,
                config=CONFIG,
            )
        assert ctx.open_interest is None
        assert provenance.open_interest_source is None
        assert provenance.open_interest_reason == "timestamp_unprovable"

    async def test_a_hot_state_reading_is_used_even_with_a_durable_row_present(
        self, market_ctx: dict[str, Any], redis_client: redis_asyncio.Redis
    ) -> None:
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            await insert_open_interest(
                session,
                market_ctx["market_id"],
                ts=CUT - timedelta(days=1),
                open_interest=Decimal("5000"),
            )
        key = keys.derivatives(EXCHANGE, SYMBOL)
        await redis_client.hset(
            key,
            mapping={
                "open_interest": "7000",
                "oi_ts": (CUT - timedelta(minutes=1)).isoformat(),
            },
        )
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            ctx, provenance = await build_market_context(
                session,
                redis_client,
                market=market_ctx["market"],
                source_bar_close=CUT,
                config=CONFIG,
            )
        assert ctx.open_interest is not None
        assert ctx.open_interest.open_interest == Decimal("7000")
        assert provenance.open_interest_source == "hot_state"
        assert provenance.open_interest_reason is None

    async def test_a_sample_one_second_after_the_cut_never_enters(
        self, market_ctx: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            await insert_open_interest(
                session,
                market_ctx["market_id"],
                ts=CUT + timedelta(seconds=1),
                open_interest=Decimal("5000"),
            )
        async with role_session(market_ctx["factory"], db_role="hunter_worker") as session:
            ctx, provenance = await build_market_context(
                session,
                redis_client,
                market=market_ctx["market"],
                source_bar_close=CUT,
                config=CONFIG,
            )
        assert ctx.open_interest is None
        assert provenance.open_interest_ts is None
        assert provenance.open_interest_reason == "no_data"
