"""``agent_signals.regime_id`` actually getting stamped — notes-S2.md §"o
regime não chega ao sinal" (KB-0030) and this task's item (c).

Against a real Postgres and a real Redis: the global regime in force at
``source_bar_close`` is looked up under the same slot lock that persists the
signal, and never blocks the decision. Anti-look-ahead applies to the regime
exactly as it does to candles/derivatives: a regime that only starts after the
bar's close must not be picked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import AgentSignal
from hunter_core.db.session import role_session
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    insert_regime,
    isolate_catalogue,
    only_version,
    seed_market,
    series,
)

pytestmark = pytest.mark.integration

CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
CONFIG = ShadowConfig(eligibility_max_lag_s=300, context_minutes=1560)


def clock_at(instant: datetime) -> Any:
    return lambda: instant


@pytest.fixture
async def shadow_db(db_session_factory: Any) -> dict[str, Any]:
    """Same recipe as ``test_shadow_decisions.py``'s fixture: a market, an
    activated ``volume_anomaly_v1`` and a triggering series, plus a clean
    ``market_regimes`` table (session-scoped database, other tests may have
    left rows behind)."""
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        await session.execute(text("DELETE FROM candles"))
        await session.execute(text("DELETE FROM market_regimes"))
        _exchange_id, market_id = await seed_market(session)
        _strategy_id, version_id = await activate_version(session)
        await isolate_catalogue(session)
        await insert_candles(session, market_id, series(CUT))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    version = only_version(versions)
    return {
        "factory": db_session_factory,
        "version": version,
        "market": market,
        "market_id": market_id,
        "version_id": version_id,
    }


async def _decide(shadow_db: dict[str, Any], redis_client: Any, *, at: datetime) -> Any:
    return await evaluate_slot(
        shadow_db["factory"],
        redis_client,
        version=shadow_db["version"],
        market=shadow_db["market"],
        bar_close=CUT,
        config=CONFIG,
        clock=clock_at(at),
    )


async def _signal(factory: Any) -> AgentSignal:
    async with role_session(factory, db_role="hunter_worker") as session:
        return (await session.execute(select(AgentSignal))).scalar_one()


class TestRegimeInForce:
    async def test_the_global_regime_in_force_at_the_cut_is_stamped(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            regime_id = await insert_regime(session, start_time=CUT - timedelta(days=1))
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        signal = await _signal(shadow_db["factory"])
        assert signal.regime_id == regime_id
        assert signal.supporting_features["provenance"]["regime_reason"] is None

    async def test_the_newer_of_two_non_overlapping_regimes_wins(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            await insert_regime(
                session,
                start_time=CUT - timedelta(days=2),
                end_time=CUT - timedelta(hours=1),
                regime="BTC_BEAR",
            )
            current_id = await insert_regime(
                session, start_time=CUT - timedelta(hours=1), regime="BTC_BULL"
            )
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        signal = await _signal(shadow_db["factory"])
        assert signal.regime_id == current_id

    async def test_the_classifiers_unknown_state_is_stamped_like_any_other_regime(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        """``UNKNOWN`` is a classification, not a missing value
        (``hunter_core.domain.enums.MarketRegime`` docstring): a row that says
        "the classifier could not tell" still gets stamped, distinct from no
        row existing at all."""
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            regime_id = await insert_regime(
                session, start_time=CUT - timedelta(days=1), regime="UNKNOWN"
            )
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        signal = await _signal(shadow_db["factory"])
        assert signal.regime_id == regime_id
        assert signal.supporting_features["provenance"]["regime_reason"] is None


class TestRegimeWarmup:
    async def test_no_row_at_all_leaves_regime_id_null_with_a_reason(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        signal = await _signal(shadow_db["factory"])
        assert signal.regime_id is None
        assert signal.supporting_features["provenance"]["regime_reason"] == "no_regime_asof"

    async def test_it_never_blocks_the_signal(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        evaluation = await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        assert evaluation.state.value == "triggered"


class TestRegimeLookAhead:
    async def test_a_regime_starting_after_the_cut_is_not_picked(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            await insert_regime(session, start_time=CUT + timedelta(seconds=1))
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        signal = await _signal(shadow_db["factory"])
        assert signal.regime_id is None
        assert signal.supporting_features["provenance"]["regime_reason"] == "no_regime_asof"

    async def test_a_regime_that_had_already_ended_before_the_cut_is_not_picked(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            await insert_regime(
                session,
                start_time=CUT - timedelta(days=2),
                end_time=CUT - timedelta(days=1),
            )
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        signal = await _signal(shadow_db["factory"])
        assert signal.regime_id is None
        assert signal.supporting_features["provenance"]["regime_reason"] == "no_regime_asof"

    async def test_a_regime_starting_exactly_at_the_cut_is_picked(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        """``start_time <= cut`` is inclusive: the regime that started at
        exactly this bar's close is already in force."""
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            regime_id = await insert_regime(session, start_time=CUT)
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        signal = await _signal(shadow_db["factory"])
        assert signal.regime_id == regime_id

    async def test_a_regime_ending_exactly_at_the_cut_is_not_picked(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        """The half-open interval is ``[start_time, end_time)``: a regime
        whose ``end_time`` is exactly the cut has already ended by then."""
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            await insert_regime(session, start_time=CUT - timedelta(days=1), end_time=CUT)
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        signal = await _signal(shadow_db["factory"])
        assert signal.regime_id is None
        assert signal.supporting_features["provenance"]["regime_reason"] == "no_regime_asof"
