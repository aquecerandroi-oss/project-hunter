"""No look-ahead, provably — T3.19b, entrega 3.

The claim under test is the one that makes a replay worth anything at all: **a
replayed decision at bar ``t`` never reads a candle that closes after ``t``.**

The proof is a mutation test, not an inspection. One bar is replayed twice over
the same database; between the two runs, every candle *after* that bar is
rewritten into something the strategy could not possibly ignore (fifty times the
volume, half again the price). If the decision moves, the engine read the future.

Two mutations, because "arrives later" has two shapes: a candle whose values
change (a backfill correcting history) and a candle that is not final yet (the
minute still forming). Neither may move a decision already taken.

And a **contra-proof**, which is what makes the test worth running: the same
comparison is applied to a deliberately cheating engine — one whose context cut
is moved thirty minutes into the future while it keeps reporting the honest bar.
The cheat must be caught. A leakage test that cannot fail is decoration.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import AgentSignal
from hunter_core.db.session import role_session
from hunter_core.domain.enums import ShadowCohort
from hunter_strategy_worker import decide
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.context import build_market_context
from hunter_strategy_worker.replay.simulate import ReplayWindow, replay_market
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    isolate_catalogue,
    only_version,
    seed_market,
)
from .test_replay_engine import CUT, TRIGGER_BAR, replay_series

FUTURE_FROM = TRIGGER_BAR + timedelta(minutes=5)
"""Everything from 11:05 on is *after* the bar under test (11:00) — its context
stops at ``open_time <= 10:59`` by construction."""

ONE_BAR = ReplayWindow(TRIGGER_BAR, TRIGGER_BAR + timedelta(minutes=5))
"""Exactly the anomaly bar: one decision, so a difference is unambiguous."""

CHEAT_LOOKAHEAD = timedelta(minutes=30)


def _cohort() -> str:
    return ShadowCohort.replay(uuid.uuid4())


@pytest.fixture
async def lookahead_db(db_session_factory: Any) -> dict[str, Any]:
    key = f"replay_leak_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        for table in ("shadow_outbox", "shadow_episodes", "signal_outcomes", "agent_signals"):
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
        await session.execute(text("DELETE FROM candles"))
        _exchange_id, market_id = await seed_market(session)
        await activate_version(session, key=key)
        await insert_candles(session, market_id, replay_series())
    async with db_session_factory() as owner, owner.begin():
        await isolate_catalogue(owner, keep=key)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    return {
        "factory": db_session_factory,
        "version": only_version(versions, key),
        "market": market,
        "market_id": market_id,
    }


async def _decide_one_bar(db: dict[str, Any], cohort: str) -> dict[str, Any]:
    """Replay the single anomaly bar and return everything it decided."""
    config = ShadowConfig(cohort=cohort, eligibility_max_lag_s=300, context_minutes=1560)
    result = await replay_market(
        db["factory"],
        version=db["version"],
        market=db["market"],
        window=ONE_BAR,
        config=config,
    )
    async with role_session(db["factory"], db_role="hunter_worker") as session:
        rows = (
            await session.execute(
                select(
                    AgentSignal.stop,
                    AgentSignal.targets,
                    AgentSignal.confidence,
                    AgentSignal.reason,
                    AgentSignal.expected_holding_s,
                    AgentSignal.supporting_features["observation_ts"].astext.label("observed"),
                    AgentSignal.supporting_features["features"].label("features"),
                ).where(AgentSignal.supporting_features["cohort"].astext == cohort)
            )
        ).all()
    return {
        "states": dict(result.states),
        "signals": [
            (
                row.stop,
                list(row.targets),
                row.confidence,
                row.reason,
                row.expected_holding_s,
                row.observed,
                row.features,
            )
            for row in rows
        ],
    }


async def _rewrite_the_future(db: dict[str, Any], *, final: bool = True) -> None:
    """Make every candle after the bar under test unmistakably different."""
    async with role_session(db["factory"], db_role="hunter_worker") as session:
        await session.execute(
            text(
                "UPDATE candles SET volume = volume * 50, open = open * 1.5, "
                "high = high * 1.5, low = low * 1.5, close = close * 1.5, "
                "is_final = :final WHERE market_id = :market_id AND open_time >= :cut"
            ),
            {"market_id": db["market_id"], "cut": FUTURE_FROM, "final": final},
        )


@pytest.mark.integration
class TestTheFutureCannotMoveADecision:
    async def test_rewriting_every_later_candle_changes_nothing(
        self, lookahead_db: dict[str, Any]
    ) -> None:
        before = await _decide_one_bar(lookahead_db, _cohort())
        assert before["states"] == {"triggered": 1}, "the bar under test must decide something"
        await _rewrite_the_future(lookahead_db)
        after = await _decide_one_bar(lookahead_db, _cohort())
        assert after == before

    async def test_a_candle_that_is_not_final_changes_nothing_either(
        self, lookahead_db: dict[str, Any]
    ) -> None:
        """The same rewrite, with the later minutes also marked non-final.

        ``repo.load_candles`` filters on ``is_final`` and ``build_context``
        filters again on the cut: the decision must be identical whether the
        future exists, is wrong, or has not settled.
        """
        before = await _decide_one_bar(lookahead_db, _cohort())
        await _rewrite_the_future(lookahead_db, final=False)
        after = await _decide_one_bar(lookahead_db, _cohort())
        assert after == before

    async def test_the_costs_are_the_versions_own_and_not_the_replays(
        self, lookahead_db: dict[str, Any]
    ) -> None:
        """The assumed costs a replay writes are read from the frozen parameters.

        Same source as the live path (``strategies.base.assumed_costs`` over
        ``strategy_versions.default_parameters``), so a replayed R and a live R
        are comparable numbers rather than two hypotheses with one name.
        """
        cohort = _cohort()
        await _decide_one_bar(lookahead_db, cohort)
        params = lookahead_db["version"].params
        async with role_session(lookahead_db["factory"], db_role="hunter_worker") as session:
            meta = (
                await session.execute(
                    text(
                        "SELECT o.meta FROM signal_outcomes o JOIN agent_signals s "
                        "ON s.id = o.signal_id "
                        "WHERE s.supporting_features ->> 'cohort' = :cohort"
                    ),
                    {"cohort": cohort},
                )
            ).scalar_one()
        costs = meta["assumed_costs"]
        assert Decimal(costs["spread_bps"]) == Decimal(str(params["assumed_spread_bps"]))
        assert Decimal(costs["slippage_bps"]) == Decimal(str(params["slippage_bps"]))
        assert Decimal(costs["fee_bps"]) == Decimal(str(params["fee_bps"]))
        assert costs["max_entry_delay_s"] == params["max_entry_delay_s"]


@pytest.mark.integration
class TestTheCheatIsCaught:
    """Contra-proof: an engine that peeks is detected by the same comparison."""

    async def test_a_cut_moved_into_the_future_is_detected(
        self, lookahead_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def cheating_context(
            session: Any, redis: Any, *, source_bar_close: datetime, **kwargs: Any
        ) -> Any:
            # The leak, in one line: the observation is cut thirty minutes late
            # while the run still calls this "the bar that closed at 11:00".
            return await build_market_context(
                session, redis, source_bar_close=source_bar_close + CHEAT_LOOKAHEAD, **kwargs
            )

        monkeypatch.setattr(decide, "build_market_context", cheating_context)
        before = await _decide_one_bar(lookahead_db, _cohort())
        await _rewrite_the_future(lookahead_db)
        after = await _decide_one_bar(lookahead_db, _cohort())
        assert after != before, (
            "the cheating engine read candles after the bar and the test did not notice — "
            "the no-look-ahead proof above would be vacuous"
        )

    async def test_the_same_cheat_is_invisible_without_the_mutation(
        self, lookahead_db: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Why the mutation is the test and not an accessory.

        Run the cheat twice over an unchanged database and it looks perfectly
        deterministic — which is exactly how a leaking backtest looks when
        nobody perturbs the future.
        """

        async def cheating_context(
            session: Any, redis: Any, *, source_bar_close: datetime, **kwargs: Any
        ) -> Any:
            return await build_market_context(
                session, redis, source_bar_close=source_bar_close + CHEAT_LOOKAHEAD, **kwargs
            )

        monkeypatch.setattr(decide, "build_market_context", cheating_context)
        first = await _decide_one_bar(lookahead_db, _cohort())
        second = await _decide_one_bar(lookahead_db, _cohort())
        assert first == second


@pytest.mark.integration
class TestTheWindowItself:
    async def test_a_bar_outside_the_window_is_never_evaluated(
        self, lookahead_db: dict[str, Any]
    ) -> None:
        """The half-open window is what makes sliced runs countable."""
        cohort = _cohort()
        config = ShadowConfig(cohort=cohort, eligibility_max_lag_s=300, context_minutes=1560)
        result = await replay_market(
            lookahead_db["factory"],
            version=lookahead_db["version"],
            market=lookahead_db["market"],
            window=ReplayWindow(TRIGGER_BAR - timedelta(minutes=10), TRIGGER_BAR),
            config=config,
        )
        assert result.bars == 2
        async with role_session(lookahead_db["factory"], db_role="hunter_worker") as session:
            signals = list(
                (
                    await session.execute(
                        select(AgentSignal.id).where(
                            AgentSignal.supporting_features["cohort"].astext == cohort
                        )
                    )
                ).scalars()
            )
        assert signals == [], "the anomaly bar closes at the exclusive end"
