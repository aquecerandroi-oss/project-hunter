"""The replay engine end to end — T3.19b, entrega 1 and entrega 3's third half.

Three things are proved here against a real Postgres:

1. **the run happens**: every aligned bar of the window is evaluated by the live
   ``evaluate_slot``, the decisions land in ``agent_signals``/``signal_outcomes``
   under ``replay:<run_id>``, the episode slot is keyed on that cohort, and the
   outcomes are resolved by the live walker;
2. **the run publishes nothing**: not one ``shadow_outbox`` row, contrasted with
   the same decision under ``prospective``, which writes one;
3. **same code, same answer**: the live path and the replay path, over the same
   window and the same candles, produce the same decision at the same bar with
   the same frozen levels and the same outcome.

The series is real in shape (the frozen ``volume_anomaly_v1`` fires on it) and
labelled test data, as CLAUDE.md requires.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.agents_shadow import ShadowEpisode, ShadowOutbox
from hunter_core.db.session import role_session
from hunter_core.domain.enums import ShadowCohort, ShadowTrackingState
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.replay.candles import load_window
from hunter_strategy_worker.replay.ledger import (
    COMPONENT,
    EVENT_FINISHED,
    ReplayRun,
    append_jsonl,
    record_run,
    record_slice,
)
from hunter_strategy_worker.replay.simulate import (
    ReplayWindow,
    bar_closes,
    count_population,
    drain_cohort,
    replay_market,
)
from hunter_strategy_worker.repo import load_candles, load_market

from .builders import (
    EXCHANGE,
    MINUTE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    insert_funding_rate,
    isolate_catalogue,
    only_version,
    seed_market,
)

CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
"""End of the seeded series. In the past on any real clock, so the drain's
``min(horizon, utcnow())`` is the horizon and not the wall clock."""

HISTORY_MINUTES = 1620
"""1560 of context (``ShadowConfig.context_minutes``) plus the hour the window
itself spans."""

WINDOW = ReplayWindow(CUT - timedelta(minutes=60), CUT)
TRIGGER_BAR = CUT - timedelta(minutes=60)
"""The 5m bar closing at 11:00 carries the volume anomaly."""

RUN_ID = uuid.UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
REPLAY_COHORT = ShadowCohort.replay(RUN_ID)
CONFIG = ShadowConfig(cohort=REPLAY_COHORT, eligibility_max_lag_s=300, context_minutes=1560)
LIVE_CONFIG = ShadowConfig(
    cohort=ShadowCohort.PROSPECTIVE, eligibility_max_lag_s=300, context_minutes=1560
)


def replay_series(cut: datetime = CUT) -> list[dict[str, Any]]:
    """1620 quiet 1m candles ending at ``cut``, with one anomaly and one rally.

    The anomaly sits in the five minutes ending at ``TRIGGER_BAR`` (six times the
    quiet volume, closing above its own midpoint) so the 5m bar that closes there
    is the one ``volume_anomaly_v1`` fires on. From that close onward the price
    walks up two ticks a minute: enough for the frozen target to be reached
    within the horizon, gently enough that the entry bar's own geometry check
    (``stop < entry < target1``) still passes — a gap straight through the target
    would produce ``no_entry: geometry`` and prove nothing about exits.
    """
    rows: list[dict[str, Any]] = []
    for index in range(HISTORY_MINUTES):
        open_time = cut - MINUTE * (HISTORY_MINUTES - index)
        spike = TRIGGER_BAR - MINUTE * 5 <= open_time < TRIGGER_BAR
        if open_time >= TRIGGER_BAR:
            step = int((open_time - TRIGGER_BAR).total_seconds() // 60)
            base = Decimal("100.3") + Decimal("0.2") * step
            rows.append(
                {
                    "open_time": open_time,
                    "open": base,
                    "high": base + Decimal("0.3"),
                    "low": base - Decimal("0.1"),
                    "close": base + Decimal("0.2"),
                    "volume": Decimal("12"),
                }
            )
            continue
        rows.append(
            {
                "open_time": open_time,
                "open": Decimal("100"),
                "high": Decimal("100.4") if spike else Decimal("100.2"),
                "low": Decimal("100.0") if spike else Decimal("99.8"),
                "close": Decimal("100.3") if spike else Decimal("100"),
                "volume": Decimal("60") if spike else Decimal("10"),
            }
        )
    return rows


@pytest.fixture
async def replay_db(db_session_factory: Any) -> dict[str, Any]:
    """A market, a series and one runnable version — the Lab, emptied first."""
    key = f"replay_engine_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        for table in ("shadow_outbox", "shadow_episodes", "signal_outcomes", "agent_signals"):
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
        await session.execute(text("DELETE FROM candles"))
        await session.execute(text("DELETE FROM funding_rates"))
        _exchange_id, market_id = await seed_market(session)
        await activate_version(session, key=key)
        await insert_candles(session, market_id, replay_series())
        # Three days of 8-hourly settlements: enough for ``resolve_funding`` to
        # measure the market's own cadence and conclude that none of them falls
        # inside the trade, which is the only way a *zero* funding charge is
        # ever written (settle.py). Without them the replay would be honest and
        # useless here: ``r_multiple`` NULL with ``funding_schedule_unknown``.
        for hours in range(0, 73, 8):
            await insert_funding_rate(
                session,
                market_id,
                funding_time=CUT - timedelta(hours=72 - hours),
                rate=Decimal("0.0001"),
                mark_price=Decimal("100"),
            )
    async with db_session_factory() as owner, owner.begin():
        await isolate_catalogue(owner, keep=key)
        # ``system_events`` is append-only for ``hunter_worker`` (ddl/grants.py)
        # and ``replay_runs`` is append-only for it too (0013, DATABASE.md §25.4):
        # only the owner may clear the previous scenario's receipts. That the
        # worker cannot is the point of the table, not an inconvenience here.
        await owner.execute(
            text("DELETE FROM system_events WHERE component = :component"),
            {"component": COMPONENT},
        )
        await owner.execute(text("DELETE FROM replay_runs"))
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


async def _run_replay(db: dict[str, Any], *, cohort: str = REPLAY_COHORT) -> Any:
    config = ShadowConfig(cohort=cohort, eligibility_max_lag_s=300, context_minutes=1560)
    result = await replay_market(
        db["factory"],
        version=db["version"],
        market=db["market"],
        window=WINDOW,
        config=config,
    )
    await drain_cohort(db["factory"], cohort=cohort, config=config)
    return result


@pytest.mark.integration
class TestTheRunHappens:
    async def test_every_aligned_bar_of_the_window_is_evaluated(
        self, replay_db: dict[str, Any]
    ) -> None:
        expected = len(list(bar_closes(WINDOW, replay_db["version"].timeframe)))
        assert expected == 12, "one hour of 5m closes"
        result = await _run_replay(replay_db)
        assert result.bars == expected
        assert result.errors == 0
        assert sum(result.states.values()) == expected

    async def test_the_anomaly_bar_decides_and_the_rest_do_not(
        self, replay_db: dict[str, Any]
    ) -> None:
        result = await _run_replay(replay_db)
        assert result.states.get("triggered") == 1
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            signal = (await session.execute(select(AgentSignal))).scalar_one()
        assert signal.supporting_features["provenance"]["strategy_version_id"] == str(
            replay_db["version"].id
        )
        assert signal.emitted_at == TRIGGER_BAR + timedelta(seconds=2)

    async def test_the_signal_and_the_slot_carry_the_replay_cohort(
        self, replay_db: dict[str, Any]
    ) -> None:
        await _run_replay(replay_db)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            signal = (await session.execute(select(AgentSignal))).scalar_one()
            outcome = (await session.execute(select(SignalOutcome))).scalar_one()
            episode = (await session.execute(select(ShadowEpisode))).scalar_one()
        assert signal.supporting_features["cohort"] == REPLAY_COHORT
        assert outcome.meta["cohort"] == REPLAY_COHORT
        assert episode.cohort == REPLAY_COHORT
        assert ShadowCohort.is_valid(episode.cohort)

    async def test_the_outcome_is_resolved_by_the_live_walker(
        self, replay_db: dict[str, Any]
    ) -> None:
        """The rally reaches the frozen target, so the tracking ends ``terminal``.

        Nothing about that number is written here: the target is
        ``volume_anomaly_v1``'s own ``target_atr`` applied to the reference
        close, the exit is ``walker.walk``'s and the R is ``settle.settle``'s.
        """
        await _run_replay(replay_db)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            outcome = (await session.execute(select(SignalOutcome))).scalar_one()
            population = await count_population(session, cohort=REPLAY_COHORT)
        assert outcome.tracking_state is ShadowTrackingState.TERMINAL
        assert outcome.result.value == "target"
        assert outcome.r_multiple is not None
        assert population.signals == 1
        assert population.outcomes == 1
        assert population.open == 0

    async def test_a_second_run_of_the_same_window_writes_nothing_new(
        self, replay_db: dict[str, Any]
    ) -> None:
        """The identity is a ``uuid5`` of (version, market, params, bar, cohort),
        so re-running a slice is idempotent — which is what makes ``--from``/
        ``--to`` slicing safe when a slice has to be repeated."""
        await _run_replay(replay_db)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            before = await count_population(session, cohort=REPLAY_COHORT)
            first_id = (await session.execute(select(AgentSignal.id))).scalar_one()
        await _run_replay(replay_db)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            after = await count_population(session, cohort=REPLAY_COHORT)
            ids = list((await session.execute(select(AgentSignal.id))).scalars())
        assert after == before
        assert ids == [first_id]


@pytest.mark.integration
class TestTheRunPublishesNothing:
    async def test_a_replay_writes_no_outbox_row(self, replay_db: dict[str, Any]) -> None:
        await _run_replay(replay_db)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            rows = list((await session.execute(select(ShadowOutbox))).scalars())
        assert rows == []

    async def test_the_same_decision_under_prospective_does_publish(
        self, replay_db: dict[str, Any]
    ) -> None:
        """Contra-proof: the outbox is empty because of the cohort, not because
        this fixture never produces an event."""
        await _run_replay(replay_db, cohort=ShadowCohort.PROSPECTIVE)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            rows = list((await session.execute(select(ShadowOutbox))).scalars())
        assert len(rows) == 1
        assert rows[0].stream == "shadow.signals.emitted"


@pytest.mark.integration
class TestSameCodeSameAnswer:
    async def test_live_and_replay_agree_bar_by_bar_over_the_same_window(
        self, replay_db: dict[str, Any]
    ) -> None:
        """The live cohort's own window, run through the replay.

        Both populations are produced by ``evaluate_slot``; the only difference
        is the clock the run reads and the label it stamps. If they disagreed,
        one of the two would be reading something the other does not.
        """
        live = await _run_replay(replay_db, cohort=ShadowCohort.PROSPECTIVE)
        replay = await _run_replay(replay_db, cohort=REPLAY_COHORT)
        assert live.bars == replay.bars
        assert live.states == replay.states

        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            rows = (
                await session.execute(
                    select(
                        AgentSignal.supporting_features["cohort"].astext.label("cohort"),
                        AgentSignal.stop,
                        AgentSignal.targets,
                        AgentSignal.confidence,
                        AgentSignal.reason,
                        AgentSignal.expected_holding_s,
                        SignalOutcome.tracking_state,
                        SignalOutcome.result,
                        SignalOutcome.virtual_entry,
                        SignalOutcome.exit_price,
                        SignalOutcome.exit_ts,
                        SignalOutcome.r_multiple,
                        SignalOutcome.meta["entry_plan"]["source_bar_close"].astext.label("bar"),
                    ).join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
                )
            ).all()
        by_cohort = {row.cohort: row for row in rows}
        assert set(by_cohort) == {ShadowCohort.PROSPECTIVE, REPLAY_COHORT}
        live_row = by_cohort[ShadowCohort.PROSPECTIVE]
        replay_row = by_cohort[REPLAY_COHORT]
        assert live_row.bar == replay_row.bar == TRIGGER_BAR.isoformat()
        assert (live_row.stop, live_row.targets) == (replay_row.stop, replay_row.targets)
        assert (live_row.confidence, live_row.reason) == (replay_row.confidence, replay_row.reason)
        assert live_row.expected_holding_s == replay_row.expected_holding_s
        assert (live_row.tracking_state, live_row.result) == (
            replay_row.tracking_state,
            replay_row.result,
        )
        assert (live_row.virtual_entry, live_row.exit_price, live_row.exit_ts) == (
            replay_row.virtual_entry,
            replay_row.exit_price,
            replay_row.exit_ts,
        )
        assert live_row.r_multiple == replay_row.r_multiple


@pytest.mark.integration
class TestTheCandleCache:
    """The optimisation that makes a replay affordable may not change a number.

    ``WindowCache`` exists so a run reads each market's slice once instead of
    once per bar. It is only legitimate if it answers exactly what
    ``repo.load_candles`` answers, so that is what is asserted — for every cut
    the window visits, not for one.
    """

    async def test_the_cache_answers_exactly_what_the_database_answers(
        self, replay_db: dict[str, Any]
    ) -> None:
        market = replay_db["market"]
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            cache = await load_window(
                session,
                market=market,
                window_start=WINDOW.start,
                window_end=WINDOW.end,
                context_minutes=1560,
            )
            for cut in bar_closes(WINDOW, replay_db["version"].timeframe):
                start = cut - timedelta(minutes=1560)
                expected = await load_candles(session, market=market, start=start, end=cut)
                cached = await cache(session, market=market, start=start, end=cut)
                assert [c.open_time for c in cached] == [c.open_time for c in expected]
                assert cached == expected
        assert cache.hits == 12
        assert cache.misses == 0

    async def test_a_request_outside_the_slice_goes_to_the_database(
        self, replay_db: dict[str, Any]
    ) -> None:
        """The outcome engine reads past the window's end; the cache must not
        answer a shorter list for it."""
        market = replay_db["market"]
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            cache = await load_window(
                session,
                market=market,
                window_start=WINDOW.start,
                window_end=WINDOW.end,
                context_minutes=1560,
            )
            beyond = await cache(
                session, market=market, start=WINDOW.end, end=WINDOW.end + timedelta(minutes=30)
            )
        assert cache.misses == 1
        assert beyond == []


def _ledger_row(db: dict[str, Any], *, result: Any, population: Any) -> ReplayRun:
    """The receipt of the slice ``_run_replay`` just executed."""
    return ReplayRun(
        run_id=RUN_ID,
        cohort=REPLAY_COHORT,
        strategy_version_id=db["version"].id,
        version_label="volume_anomaly v1",
        window_from=WINDOW.start,
        window_to=WINDOW.end,
        markets=(f"{EXCHANGE}:{SYMBOL}",),
        started_at=CUT,
        finished_at=CUT + timedelta(seconds=5),
        bars_evaluated=result.bars,
        signals=population.signals,
        outcomes_resolved=population.outcomes,
        outcomes_open=population.open,
        seconds=5.0,
        decision_lag_s=2,
        workers=1,
        evaluations_by_state=dict(result.states),
    )


@pytest.mark.integration
class TestTheLedger:
    async def test_the_run_leaves_a_receipt_in_system_events_and_on_disk(
        self, replay_db: dict[str, Any], tmp_path: Path
    ) -> None:
        result = await _run_replay(replay_db)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            population = await count_population(session, cohort=REPLAY_COHORT)
            run = _ledger_row(replay_db, result=result, population=population)
            await record_run(session, run)
        ledger = tmp_path / "replay.jsonl"
        append_jsonl(ledger, run)
        append_jsonl(ledger, run)
        lines = ledger.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2, "the JSONL ledger appends, it never rewrites"
        assert json.loads(lines[0])["run_id"] == str(RUN_ID)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            row = (
                await session.execute(
                    text(
                        "SELECT event, level::text AS level, data FROM system_events "
                        "WHERE component = :component ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"component": COMPONENT},
                )
            ).one()
        assert row.event == EVENT_FINISHED
        assert row.level == "info"
        assert row.data["cohort"] == REPLAY_COHORT
        assert row.data["bars_evaluated"] == 12
        assert row.data["signals"] == 1
        assert row.data["market_count"] == 1
        # ``record_run`` writes the durable half first, in the same transaction:
        # a published event no stored row explains is the disagreement the outbox
        # pattern exists to prevent, one table over.
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            stored = await session.scalar(
                text("SELECT count(*) FROM replay_runs WHERE run_id = :run"), {"run": RUN_ID}
            )
        assert stored == 1

    async def test_the_run_is_written_to_replay_runs_once_per_slice(
        self, replay_db: dict[str, Any]
    ) -> None:
        """The third branch of the receipt — ``0013_replay_runs``, DATABASE.md §25.

        It is the durable one: ``system_events`` keeps the same JSON for 30 days
        and the JSONL only exists if somebody kept the file. Two assertions,
        because the table makes two promises: the row is written **as the
        worker** (``SELECT``/``INSERT`` and nothing else), and re-running the
        same slice writes one receipt, not two — the idempotence
        ``uq_replay_runs_slice`` states and ``ON CONFLICT DO NOTHING`` honours.
        """
        result = await _run_replay(replay_db)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            population = await count_population(session, cohort=REPLAY_COHORT)
            run = _ledger_row(replay_db, result=result, population=population)
            first = await record_slice(session, run)
            second = await record_slice(session, run)
        assert first is not None, "the first slice writes its receipt"
        assert second is None, "the same slice twice is one receipt"

        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            row = (
                await session.execute(
                    text(
                        "SELECT id, run_id, cohort, strategy_version_id, markets, "
                        "bars_evaluated, signals, outcomes_resolved, seconds, decision_lag_s, "
                        "workers, evaluations_by_state, errors, window_from, window_to "
                        "FROM replay_runs WHERE run_id = :run"
                    ),
                    {"run": RUN_ID},
                )
            ).one()
        assert row.id == first
        assert row.cohort == REPLAY_COHORT
        assert row.strategy_version_id == replay_db["version"].id
        assert row.markets == [f"{EXCHANGE}:{SYMBOL}"]
        assert row.bars_evaluated == 12
        assert row.signals == 1
        assert row.window_from == WINDOW.start
        assert row.window_to == WINDOW.end
        assert row.decision_lag_s == 2
        assert row.workers == 1
        assert row.errors == 0
        assert row.evaluations_by_state == dict(result.states)
        assert row.seconds == Decimal("5.000"), "seconds is NUMERIC(12,3), never a float"

    async def test_a_second_slice_of_the_same_run_is_its_own_receipt(
        self, replay_db: dict[str, Any]
    ) -> None:
        """One row per slice (§25.1): the window is what tells two apart, and
        ``bars_evaluated`` is the column that sums back into the run."""
        result = await _run_replay(replay_db)
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            population = await count_population(session, cohort=REPLAY_COHORT)
            base = _ledger_row(replay_db, result=result, population=population)
            await record_slice(session, base)
            await record_slice(
                session,
                replace(
                    base,
                    window_from=WINDOW.end,
                    window_to=WINDOW.end + timedelta(minutes=60),
                ),
            )
        async with role_session(replay_db["factory"], db_role="hunter_worker") as session:
            slices, bars = (
                await session.execute(
                    text(
                        "SELECT count(*), sum(bars_evaluated) FROM replay_runs WHERE run_id = :run"
                    ),
                    {"run": RUN_ID},
                )
            ).one()
        assert slices == 2
        assert bars == 24
