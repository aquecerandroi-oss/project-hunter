"""Step 1 against a real Postgres: the replay must land on the outcome the
worker itself wrote.

The reference is not a hand-written fixture — the decision is taken by
``evaluate_slot`` and the outcome is advanced by ``sweep_outcomes``, exactly as
in production. Then the replay reads the frozen record back and re-walks it. If
those two disagree, every contrast built on top is a comparison between two
bugs.

Also pinned here: the replay's transaction is ``READ ONLY`` (Postgres refuses a
write, so "the Lab's tables are never touched" is enforced and not merely
intended), and the series it folds contains **final candles only**.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import SignalOutcome
from hunter_core.db.models.market_data import Candle
from hunter_core.db.session import role_session
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState, Timeframe
from hunter_indicators.replay.policies import POLICIES, policy
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import sweep_outcomes
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.replay.engine import load_series, replay_case
from hunter_strategy_worker.replay.load import load_cases, load_manifest, read_only_session
from hunter_strategy_worker.replay.reproduce import audit_case
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    MINUTE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    isolate_catalogue,
    only_version,
    seed_market,
    series,
)

pytestmark = pytest.mark.integration

CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
CONFIG = ShadowConfig(eligibility_max_lag_s=300, censor_after_s=1800, gap_recovery_max_s=7200)


def _row(minute: int, o: str, h: str, low: str, c: str) -> dict[str, Any]:
    return {
        "open_time": CUT + MINUTE * minute,
        "open": Decimal(o),
        "high": Decimal(h),
        "low": Decimal(low),
        "close": Decimal(c),
        "volume": Decimal("10"),
    }


AFTER_CUT = [
    _row(0, "100", "100.2", "99.8", "100"),
    _row(1, "100.2", "100.3", "100.1", "100.2"),  # entry bar
    _row(2, "100.2", "100.25", "99.9", "100.0"),  # low 99.9 <= stop 100.0
    _row(3, "100", "100.2", "99.9", "100"),
]


@pytest.fixture
async def replayable(db_session_factory: Any, redis_client: Any) -> dict[str, Any]:
    """One decision taken by the worker and followed to a terminal outcome."""
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        await session.execute(text("DELETE FROM candles"))
        await session.execute(text("DELETE FROM funding_rates"))
        await session.execute(text("DELETE FROM ingestion_gaps"))
        _exchange_id, market_id = await seed_market(session)
        await activate_version(session)
        await isolate_catalogue(session)
        await insert_candles(session, market_id, series(CUT))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    await evaluate_slot(
        db_session_factory,
        redis_client,
        version=only_version(versions),
        market=market,
        bar_close=CUT,
        config=CONFIG,
        clock=lambda: CUT + timedelta(seconds=2),
    )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await insert_candles(session, market_id, AFTER_CUT)
    await sweep_outcomes(db_session_factory, CONFIG, now=CUT + timedelta(minutes=5, seconds=5))
    return {"factory": db_session_factory, "market_id": market_id}


async def _stored(factory: Any) -> Any:
    async with role_session(factory, db_role="hunter_worker") as session:
        return (await session.execute(select(SignalOutcome))).scalar_one()


async def test_the_replay_reproduces_the_outcome_the_worker_wrote(
    replayable: dict[str, Any],
) -> None:
    stored = await _stored(replayable["factory"])
    assert stored.tracking_state is ShadowTrackingState.TERMINAL
    assert stored.result is OutcomeResult.STOP

    async with read_only_session(replayable["factory"]) as session:
        versions = await load_manifest(session, keys=["volume_anomaly"])
        cases = await load_cases(session, versions=versions, as_of=CUT + timedelta(hours=3))
        assert len(cases) == 1
        case = cases[0]
        replay_series = await load_series(session, case, as_of=CUT + timedelta(hours=3))
        outcomes = await replay_case(
            session,
            case,
            policies=[policy(key) for key in POLICIES],
            series=replay_series,
        )
    base = outcomes["base"]
    verdict, divergences = audit_case(case, base)
    assert (verdict, divergences) == ("reproduced", [])
    assert base.result is OutcomeResult.STOP
    assert base.exit_price is not None
    assert base.exit_price.quantize(Decimal("1.0000000000")) == stored.exit_price
    assert base.entry_ts == stored.entry_ts
    assert base.exit_ts == stored.exit_ts
    assert base.r_net is None and stored.r_multiple is None, "no funding history: null, never zero"
    assert base.funding_reason == stored.meta["r_net_reason"]
    assert base.r_ex_funding == Decimal(stored.meta["r_ex_funding"])


async def test_every_arm_is_paired_on_the_same_entry(replayable: dict[str, Any]) -> None:
    async with read_only_session(replayable["factory"]) as session:
        versions = await load_manifest(session, keys=["volume_anomaly"])
        cases = await load_cases(session, versions=versions, as_of=CUT + timedelta(hours=3))
        replay_series = await load_series(session, cases[0], as_of=CUT + timedelta(hours=3))
        outcomes = await replay_case(
            session,
            cases[0],
            policies=[policy(key) for key in POLICIES],
            series=replay_series,
        )
    assert set(outcomes) == set(POLICIES)
    entries = {o.entry for o in outcomes.values() if o.entry is not None}
    assert len(entries) == 1, "every arm enters at the same price or does not enter at all"
    stopped = [key for key, o in outcomes.items() if o.result is OutcomeResult.STOP]
    assert "base" in stopped, "the stop is shared by every arm that keeps the same stop"


async def test_the_replay_transaction_cannot_write(replayable: dict[str, Any]) -> None:
    with pytest.raises(Exception, match="read-only transaction"):
        async with read_only_session(replayable["factory"]) as session:
            await session.execute(text("UPDATE signal_outcomes SET tracked_until = now()"))


async def test_the_replay_reads_one_snapshot(replayable: dict[str, Any]) -> None:
    """The Lab keeps writing while a replay runs; every arm must see the same
    database or a difference between arms could be a difference in timing."""
    async with read_only_session(replayable["factory"]) as session:
        isolation = await session.scalar(text("SHOW transaction_isolation"))
    assert isolation == "repeatable read"


async def test_the_as_of_cut_keeps_later_candles_out_of_the_fold(
    replayable: dict[str, Any],
) -> None:
    """``as_of`` is a data cut, not only a population filter: a run "as of
    12:02" cannot resolve anything with the 12:03 candle, even though the row
    is already in the table (Astra, R1 diff review, must-fix 1)."""
    async with read_only_session(replayable["factory"]) as session:
        versions = await load_manifest(session, keys=["volume_anomaly"])
        cases = await load_cases(session, versions=versions, as_of=CUT + timedelta(hours=3))
        early = await load_series(session, cases[0], as_of=CUT + timedelta(minutes=2))
        late = await load_series(session, cases[0], as_of=CUT + timedelta(hours=3))
        outcome = await replay_case(session, cases[0], policies=[policy("base")], series=early)
    assert [bar.open_time for bar in early.bars] == [CUT + MINUTE]
    assert early.truncated == "immature"
    assert max(candle.open_time for candle in early.candles) == CUT + MINUTE
    assert len(late.bars) > len(early.bars)
    assert outcome["base"].tracking_state is ShadowTrackingState.ACTIVE
    assert outcome["base"].reason == "immature", "not a stop it could not have seen yet"


async def test_a_non_final_candle_never_reaches_the_fold(replayable: dict[str, Any]) -> None:
    """Anti look-ahead at the storage boundary: the minute exists in the table
    but is not final, so it is not part of the series the arms fold."""
    minute = CUT + MINUTE * 6
    async with role_session(replayable["factory"], db_role="hunter_worker") as session:
        session.add(
            Candle(
                market_id=replayable["market_id"],
                timeframe=Timeframe.M1,
                open_time=minute,
                open=Decimal("100"),
                high=Decimal("999"),
                low=Decimal("1"),
                close=Decimal("999"),
                volume=Decimal("10"),
                is_final=False,
                source="test",
            )
        )
    async with read_only_session(replayable["factory"]) as session:
        versions = await load_manifest(session, keys=["volume_anomaly"])
        cases = await load_cases(session, versions=versions, as_of=CUT + timedelta(hours=3))
        replay_series = await load_series(session, cases[0], as_of=CUT + timedelta(hours=3))
    assert minute not in {candle.open_time for candle in replay_series.candles}
    assert minute not in {bar.open_time for bar in replay_series.bars}
