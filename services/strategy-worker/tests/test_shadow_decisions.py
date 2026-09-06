"""Persisting a shadow decision, against a real Postgres and a real Redis.

One transaction, one signal, one outcome, one episode, one outbox row — and a
redelivery, a restart, a second consumer or an out-of-order bar changes none of
those counts. SHADOW-LAB.md §2, §4 and §6.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, text

from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.agents_shadow import ShadowEpisode, ShadowOutbox
from hunter_core.db.session import role_session
from hunter_core.domain.enums import ShadowCohort, ShadowTrackingState, Timeframe
from hunter_core.events.streams import Streams
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import handle_candle
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.outbox import OutboxHealth, dispatch_once
from hunter_strategy_worker.repo import load_market
from hunter_strategy_worker.versions import VersionCache

from .builders import (
    EXCHANGE,
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
CONFIG = ShadowConfig(eligibility_max_lag_s=300, context_minutes=1560)


def clock_at(instant: datetime) -> Any:
    return lambda: instant


@pytest.fixture
async def shadow_db(db_session_factory: Any) -> dict[str, Any]:
    """A market, an activated ``volume_anomaly_v1`` and a triggering series."""
    async with db_session_factory() as owner, owner.begin():
        # DDL as the owner: hunter_worker has no CREATE on public, by design.
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        await session.execute(text("DELETE FROM candles"))
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


async def _counts(factory: Any) -> dict[str, int]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return {
            "signals": await session.scalar(select(func.count()).select_from(AgentSignal)) or 0,
            "outcomes": await session.scalar(select(func.count()).select_from(SignalOutcome)) or 0,
            "episodes": await session.scalar(select(func.count()).select_from(ShadowEpisode)) or 0,
            "outbox": await session.scalar(select(func.count()).select_from(ShadowOutbox)) or 0,
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


class TestOneDecision:
    async def test_a_triggering_bar_writes_exactly_four_rows(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        evaluation = await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        assert evaluation.state.value == "triggered"
        assert await _counts(shadow_db["factory"]) == {
            "signals": 1,
            "outcomes": 1,
            "episodes": 1,
            "outbox": 1,
        }

    async def test_the_outcome_starts_pending_entry_on_the_next_minute_open(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            row = (await session.execute(select(SignalOutcome))).scalar_one()
        assert row.tracking_state is ShadowTrackingState.PENDING_ENTRY
        assert row.meta["entry_plan"]["entry_bar_open"] == (CUT + timedelta(minutes=1)).isoformat()
        assert row.meta["entry_plan"]["delay_s"] == "60"  # canonical form: numbers as strings
        assert row.meta["entry_plan"]["confirmed_at"]

    async def test_a_decision_taken_too_late_is_born_no_entry_and_frees_the_slot(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        """12:00 / 12:05:02 / 12:06 -> 360 s from the reference bar: late.

        The eligibility gate is relaxed here on purpose: at its 300 s default it
        would drop this bar as *unavailable* before the delay rule could speak,
        and this test is about the delay rule.
        """
        await evaluate_slot(
            shadow_db["factory"],
            redis_client,
            version=shadow_db["version"],
            market=shadow_db["market"],
            bar_close=CUT,
            config=ShadowConfig(eligibility_max_lag_s=600),
            clock=clock_at(CUT + timedelta(minutes=5, seconds=2)),
        )
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            outcome = (await session.execute(select(SignalOutcome))).scalar_one()
            episode = (await session.execute(select(ShadowEpisode))).scalar_one()
        assert outcome.tracking_state is ShadowTrackingState.NO_ENTRY
        assert outcome.no_entry_reason == "late:delay"
        assert episode.open_outcome_signal_id is None
        assert episode.armed is False

    async def test_the_envelope_carries_the_run_labels_and_the_provenance(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            signal = (await session.execute(select(AgentSignal))).scalar_one()
        envelope = signal.supporting_features
        assert envelope["purpose"] == "research_only"
        assert envelope["cohort"] == ShadowCohort.PROSPECTIVE
        assert envelope["params_format"] == "1"  # canonical form (params_format 1)
        assert envelope["observation_ts"] == "2026-09-05T12:00:00Z"
        assert int(envelope["provenance"]["bars_in_context"]) > 1400
        assert envelope["provenance"]["eligibility_observed_at"]
        assert envelope["decision_at"] == "2026-09-05T12:00:02Z"
        assert signal.emitted_at == CUT + timedelta(seconds=2)
        assert signal.params_hash == shadow_db["version"].params_hash

    async def test_the_levels_survive_the_numeric_28_10_round_trip(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        """The stop/target the outcome will use after a restart are exactly the
        stored ones — the strategy's 28-digit target1 is put at the column's
        scale *before* the insert, never after."""
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            signal = (await session.execute(select(AgentSignal))).scalar_one()
            outcome = (await session.execute(select(SignalOutcome))).scalar_one()
        assert outcome.virtual_stop == signal.stop
        assert outcome.virtual_stop == Decimal("100.0000000000")
        stored_target = Decimal(outcome.virtual_targets[0])
        assert stored_target == Decimal("100.9214285714")
        assert stored_target.as_tuple().exponent == -10
        plan_target = Decimal(outcome.meta["progress"]["entry"] or "0")
        assert plan_target == 0  # not entered yet: no invented entry price


class TestIdempotence:
    async def test_a_redelivery_of_the_same_bar_changes_nothing(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        before = await _counts(shadow_db["factory"])
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            envelope = (await session.execute(select(AgentSignal.supporting_features))).scalar_one()
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=30))
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            after_envelope = (
                await session.execute(select(AgentSignal.supporting_features))
            ).scalar_one()
        assert await _counts(shadow_db["factory"]) == before
        assert after_envelope == envelope

    async def test_a_failure_before_the_commit_leaves_no_trace_and_is_retried_cleanly(
        self, shadow_db: dict[str, Any], redis_client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """S2 checklist: injected failure **before** the commit.

        The four rows and the slot transition share one transaction, so a crash
        between the signal insert and the slot advance must leave nothing —
        including no half-taken slot that would refuse the retry. The retry then
        produces exactly one signal, with the ``uuid5`` identity it would have
        had the first time (the barrier never moved, so the bar is still due).
        """
        from hunter_strategy_worker import decide as decide_module

        real_advance = decide_module.slots.advance

        async def explode(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("injected before the commit")

        monkeypatch.setattr(decide_module.slots, "advance", explode)
        with pytest.raises(RuntimeError, match="injected"):
            await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        assert await _counts(shadow_db["factory"]) == {
            "signals": 0,
            "outcomes": 0,
            "episodes": 0,
            "outbox": 0,
        }
        monkeypatch.setattr(decide_module.slots, "advance", real_advance)
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=3))
        counts = await _counts(shadow_db["factory"])
        assert counts == {"signals": 1, "outcomes": 1, "episodes": 1, "outbox": 1}

    async def test_a_bar_behind_the_barrier_is_refused(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        """An out-of-order delivery of an older bar never decides."""
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        await evaluate_slot(
            shadow_db["factory"],
            redis_client,
            version=shadow_db["version"],
            market=shadow_db["market"],
            bar_close=CUT - timedelta(minutes=5),
            config=CONFIG,
            clock=clock_at(CUT + timedelta(seconds=40)),
        )
        assert (await _counts(shadow_db["factory"]))["signals"] == 1

    async def test_two_concurrent_consumers_produce_one_tracking(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        """Both take the slot lock; the loser's insert conflicts and is dropped."""
        await asyncio.gather(
            _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2)),
            _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=3)),
        )
        counts = await _counts(shadow_db["factory"])
        assert counts["signals"] == 1
        assert counts["episodes"] == 1
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            open_outcomes = await session.scalar(
                select(func.count())
                .select_from(SignalOutcome)
                .where(SignalOutcome.tracking_state == ShadowTrackingState.ACTIVE)
            )
        assert open_outcomes == 0

    async def test_another_cohort_has_its_own_identity(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        import uuid

        replay = ShadowCohort.replay(uuid.UUID("55555555-5555-5555-8555-555555555555"))
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        await evaluate_slot(
            shadow_db["factory"],
            redis_client,
            version=shadow_db["version"],
            market=shadow_db["market"],
            bar_close=CUT,
            config=ShadowConfig(cohort=replay, eligibility_max_lag_s=300),
            clock=clock_at(CUT + timedelta(seconds=2)),
        )
        counts = await _counts(shadow_db["factory"])
        assert counts["signals"] == 2
        assert counts["episodes"] == 2


class TestOutbox:
    async def test_the_event_reaches_the_stream_once_and_says_research_only(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        health = OutboxHealth()
        assert await dispatch_once(shadow_db["factory"], redis_client, health) == 1
        entries = await redis_client.xrange(Streams.SHADOW_SIGNALS_EMITTED)
        assert len(entries) == 1
        import orjson

        payload = orjson.loads(entries[0][1][b"data"])["payload"]
        assert payload["purpose"] == "research_only"
        assert payload["cohort"] == ShadowCohort.PROSPECTIVE
        assert payload["tracking_state"] == "pending_entry"
        assert await dispatch_once(shadow_db["factory"], redis_client, health) == 0
        assert len(await redis_client.xrange(Streams.SHADOW_SIGNALS_EMITTED)) == 1
        assert health.pending == 0

    async def test_a_crash_between_commit_and_publication_is_recovered(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        """The decision commits, the process dies before the sweep. The row is
        still pending, and the next sweep publishes it."""
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            pending = (await session.execute(select(ShadowOutbox))).scalar_one()
        assert pending.dispatched_at is None
        health = OutboxHealth()
        assert await dispatch_once(shadow_db["factory"], redis_client, health) == 1

    async def test_a_crash_after_publication_before_the_mark_republishes_once(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        """``event_id`` is the signal id, so the duplicate on the stream is a
        no-op for any consumer that de-duplicates on it (``events.consume``)."""
        await _decide(shadow_db, redis_client, at=CUT + timedelta(seconds=2))
        health = OutboxHealth()
        await dispatch_once(shadow_db["factory"], redis_client, health)
        async with role_session(shadow_db["factory"], db_role="hunter_worker") as session:
            await session.execute(text("UPDATE shadow_outbox SET dispatched_at = NULL"))
        await dispatch_once(shadow_db["factory"], redis_client, health)
        entries = await redis_client.xrange(Streams.SHADOW_SIGNALS_EMITTED)
        assert len(entries) == 2
        import orjson

        ids = {orjson.loads(entry[1][b"data"])["event_id"] for entry in entries}
        assert len(ids) == 1


class TestConsumerEntry:
    async def test_the_candle_event_drives_the_whole_decision(
        self, shadow_db: dict[str, Any], redis_client: Any
    ) -> None:
        from hunter_core.domain.market import NormalizedCandle, to_wire
        from hunter_strategy_worker.consumer import ConsumerHealth

        from .builders import MINUTE

        candle_payload = to_wire(
            NormalizedCandle(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                timeframe=Timeframe.M1,
                open_time=CUT - MINUTE,
                close_time=CUT,
                open=Decimal("100"),
                high=Decimal("100.4"),
                low=Decimal("100.0"),
                close=Decimal("100.3"),
                volume=Decimal("60"),
                is_final=True,
            )
        )
        health = ConsumerHealth()
        await handle_candle(
            shadow_db["factory"],
            redis_client,
            payload=candle_payload,
            versions=VersionCache(60.0),
            config=CONFIG,
            health=health,
            clock=clock_at(CUT + timedelta(seconds=2)),
        )
        assert health.states == {"triggered": 1}
        assert (await _counts(shadow_db["factory"]))["signals"] == 1
