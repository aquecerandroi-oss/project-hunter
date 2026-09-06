"""Following a shadow decision to its outcome, against a real Postgres.

Entry at the chosen open, stop before target, honest excursions, funding that
cannot be established, an unrecoverable minute that censors instead of
inventing, a decision that lost its confirmation, and the re-arm barrier that
makes an out-of-order bar unable to re-arm a slot on stale evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import SignalOutcome
from hunter_core.db.models.agents_shadow import ShadowEpisode
from hunter_core.db.session import role_session
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import sweep_outcomes
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.metrics import shadow_funding_unresolved_total, shadow_trackings_unswept
from hunter_strategy_worker.repo import load_market
from hunter_strategy_worker.tracking_repo import count_open_trackings, load_open_trackings

from .builders import (
    EXCHANGE,
    MINUTE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    isolate_catalogue,
    only_version,
    register_gap,
    seed_market,
    series,
)

pytestmark = pytest.mark.integration

CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
CONFIG = ShadowConfig(eligibility_max_lag_s=300, censor_after_s=1800, gap_recovery_max_s=7200)
"""Spelled out rather than defaulted: these scenarios are *about* the budgets,
so a later change to the production defaults must not silently rewrite what they
prove."""


def clock_at(instant: datetime) -> Any:
    return lambda: instant


def _row(minute: int, o: str, h: str, low: str, c: str, volume: str = "10") -> dict[str, Any]:
    return {
        "open_time": CUT + MINUTE * minute,
        "open": Decimal(o),
        "high": Decimal(h),
        "low": Decimal(low),
        "close": Decimal(c),
        "volume": Decimal(volume),
    }


AFTER_CUT = [
    _row(0, "100", "100.2", "99.8", "100"),
    _row(1, "100.2", "100.3", "100.1", "100.2"),  # entry bar
    _row(2, "100.2", "100.25", "99.9", "100.0"),  # low 99.9 <= stop 100.0
    _row(3, "100", "100.2", "99.9", "100"),
    _row(4, "100", "100.2", "99.9", "100"),
]


@pytest.fixture
async def tracked(db_session_factory: Any, redis_client: Any) -> dict[str, Any]:
    """One decision already taken at 12:00, with 12:00-12:04 also persisted."""
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
        clock=clock_at(CUT + timedelta(seconds=2)),
    )
    return {
        "factory": db_session_factory,
        "redis": redis_client,
        "version": only_version(versions),
        "market": market,
        "market_id": market_id,
    }


async def _add(
    tracked: dict[str, Any], rows: list[dict[str, Any]], skip: set[Any] | None = None
) -> None:
    async with role_session(tracked["factory"], db_role="hunter_worker") as session:
        await insert_candles(session, tracked["market_id"], rows, skip=skip)


async def _outcome(tracked: dict[str, Any]) -> Any:
    async with role_session(tracked["factory"], db_role="hunter_worker") as session:
        return (await session.execute(select(SignalOutcome))).scalar_one()


async def _episode(tracked: dict[str, Any]) -> Any:
    async with role_session(tracked["factory"], db_role="hunter_worker") as session:
        return (await session.execute(select(ShadowEpisode))).scalar_one()


def _unresolved_total(reason: str) -> float:
    metric = shadow_funding_unresolved_total.labels(reason=reason)
    value = cast("float", metric._value.get())  # pyright: ignore[reportPrivateUsage]
    return value


class TestEntryAndStop:
    async def test_the_entry_is_taken_at_the_open_of_the_chosen_bar(
        self, tracked: dict[str, Any]
    ) -> None:
        await _add(tracked, AFTER_CUT[:2])
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=2, seconds=5))
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.ACTIVE
        assert outcome.virtual_entry == Decimal("100.2601200000")
        assert outcome.entry_ts == CUT + MINUTE

    async def test_the_stop_closes_the_tracking_and_frees_the_slot(
        self, tracked: dict[str, Any]
    ) -> None:
        await _add(tracked, AFTER_CUT)
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5, seconds=5))
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.TERMINAL
        assert outcome.result is OutcomeResult.STOP
        assert outcome.exit_price == Decimal("99.9400000000")
        assert outcome.exit_ts == CUT + MINUTE * 3
        episode = await _episode(tracked)
        assert episode.open_outcome_signal_id is None
        assert episode.armed is False
        assert episode.last_bar_close == outcome.exit_ts

    async def test_funding_that_cannot_be_established_nulls_r_but_keeps_r_ex_funding(
        self, tracked: dict[str, Any]
    ) -> None:
        """No funding history at all: the cadence is unknown, so the net R is
        null with a reason and the funding-free R is kept separately."""
        before = _unresolved_total("funding_schedule_unknown")
        await _add(tracked, AFTER_CUT)
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5, seconds=5))
        outcome = await _outcome(tracked)
        assert outcome.r_multiple is None
        assert outcome.meta["r_net_reason"] == "funding_schedule_unknown"
        assert Decimal(outcome.meta["r_ex_funding"]) < Decimal("-1")
        assert outcome.meta["funding"]["per_unit"] is None
        after = _unresolved_total("funding_schedule_unknown")
        assert after == before + 1

    async def test_funding_with_a_known_cadence_and_no_crossing_is_zero_and_priced(
        self, tracked: dict[str, Any]
    ) -> None:
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            for hour in (0, 8, 16):
                await session.execute(
                    text(
                        "INSERT INTO funding_rates (market_id, funding_time, rate, mark_price) "
                        "VALUES (:m, :t, :r, :p)"
                    ),
                    {
                        "m": tracked["market_id"],
                        "t": CUT.replace(hour=hour) - timedelta(days=1),
                        "r": Decimal("0.0001"),
                        "p": Decimal("100"),
                    },
                )
        await _add(tracked, AFTER_CUT)
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5, seconds=5))
        outcome = await _outcome(tracked)
        assert outcome.meta["funding"]["interval_s"] == str(8 * 3600)
        assert outcome.meta["funding"]["per_unit"] == "0"
        assert outcome.r_multiple is not None
        assert outcome.r_multiple == Decimal(outcome.meta["r_ex_funding"]).quantize(
            outcome.r_multiple
        )

    async def test_the_excursions_are_null_where_ohlc_cannot_say(
        self, tracked: dict[str, Any]
    ) -> None:
        await _add(tracked, AFTER_CUT)
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5, seconds=5))
        outcome = await _outcome(tracked)
        assert outcome.mae is None, "the stop bar is ambiguous: the low may be after the exit"
        assert outcome.mfe == Decimal("0.0398800000")
        excursions = outcome.meta["excursions"]
        assert excursions["ambiguous"] is True
        assert excursions["bounds"]["mae"] == ["0.26012", "0.36012"]
        assert excursions["method"] == "ohlc_complete_bars_v1"


class TestCensorship:
    """MUST-FIX 2: censorship asks ``ingestion_gaps``, it does not just watch a
    clock. The S2 proof recovered 786 gaps in about ten minutes; a worse window
    with a blind 1800 s budget would have censored follow-ups the collector was
    still about to fill, and the bias would correlate with collector
    instability — exactly the trades that matter most."""

    async def test_a_missing_minute_waits_before_it_censors(self, tracked: dict[str, Any]) -> None:
        await _add(tracked, AFTER_CUT, skip={AFTER_CUT[2]["open_time"]})
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5))
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.ACTIVE
        assert outcome.meta["gap_wait"]["minute"] == (CUT + MINUTE * 2).isoformat()

    async def test_a_gap_still_in_recovery_is_waited_out_past_the_budget(
        self, tracked: dict[str, Any]
    ) -> None:
        """An ``open`` gap is the market-worker saying "I am fetching this"."""
        missing = AFTER_CUT[2]["open_time"]
        await _add(tracked, AFTER_CUT, skip={missing})
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            await register_gap(
                session,
                tracked["market_id"],
                start=missing,
                end=missing,
                status="open",
                detected_at=CUT + timedelta(minutes=5),
            )
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5))
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=40))
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.ACTIVE
        assert outcome.meta["gap_wait"]["gap_status"] == "open"

    async def test_a_failed_gap_is_a_cooldown_before_it_is_a_censorship(
        self, tracked: dict[str, Any]
    ) -> None:
        """``failed`` is the collector saying it asked and did not get it — but
        ``_reopen_stale_failed`` puts the row back to ``open`` an hour later with
        the attempts reset, so five transient errors must not cost an outcome
        (Astra, S2 fixes diff review, HIGH c). The budget still applies, and the
        reason keeps the population separate."""
        missing = AFTER_CUT[2]["open_time"]
        await _add(tracked, AFTER_CUT, skip={missing})
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            await register_gap(
                session, tracked["market_id"], start=missing, end=missing, status="failed"
            )
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5))
        assert (await _outcome(tracked)).tracking_state is ShadowTrackingState.ACTIVE
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=40))
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.CENSORED
        assert outcome.censored_reason == f"gap:{missing.isoformat()}:failed"

    async def test_an_unregistered_minute_censors_when_the_budget_expires(
        self, tracked: dict[str, Any]
    ) -> None:
        """Nobody ever registered the hole, so nobody is going to fill it."""
        await _add(tracked, AFTER_CUT, skip={AFTER_CUT[2]["open_time"]})
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5))
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=180))
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.CENSORED
        assert outcome.result is OutcomeResult.OPEN
        assert outcome.censored_reason == (f"gap:{(CUT + MINUTE * 2).isoformat()}:unregistered")
        assert (await _episode(tracked)).open_outcome_signal_id is None

    async def test_a_stalled_open_gap_is_not_waited_out_forever(
        self, tracked: dict[str, Any]
    ) -> None:
        """The other half of the veto: if the collector is not running, its
        ``open`` row never becomes ``failed`` and the tracking — and the
        ``tracking_hold`` behind it — would stay open for good."""
        missing = AFTER_CUT[2]["open_time"]
        await _add(tracked, AFTER_CUT, skip={missing})
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            await register_gap(
                session,
                tracked["market_id"],
                start=missing,
                end=missing,
                status="open",
                detected_at=CUT - timedelta(hours=6),
            )
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5))
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.CENSORED
        assert outcome.censored_reason == f"gap:{missing.isoformat()}:stalled"

    async def test_a_gap_over_another_minute_is_not_this_minute_s_evidence(
        self, tracked: dict[str, Any]
    ) -> None:
        missing = AFTER_CUT[2]["open_time"]
        await _add(tracked, AFTER_CUT, skip={missing})
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            await register_gap(
                session,
                tracked["market_id"],
                start=CUT - timedelta(hours=3),
                end=CUT - timedelta(hours=3),
                status="open",
                detected_at=CUT,
            )
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5))
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=180))
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.CENSORED
        assert outcome.censored_reason == f"gap:{missing.isoformat()}:unregistered"

    async def test_a_blocklisted_market_is_censored_administratively(
        self, tracked: dict[str, Any]
    ) -> None:
        await _add(tracked, AFTER_CUT, skip={AFTER_CUT[2]["open_time"]})
        await sweep_outcomes(
            tracked["factory"],
            CONFIG,
            blocked=frozenset({SYMBOL}),
            now=CUT + timedelta(minutes=5),
        )
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.CENSORED
        assert outcome.censored_reason == f"blocked:{SYMBOL}"


class TestSweepBudget:
    async def test_trackings_past_the_limit_are_counted_not_hidden(
        self, tracked: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``load_open_trackings`` reads at most ``SWEEP_LIMIT`` rows a pass.
        A backlog past it advances nothing, which looks exactly like a quiet
        market — so it has to be a number somebody can see."""
        from hunter_strategy_worker import consumer as consumer_module

        async def nothing(session: Any, **_kwargs: Any) -> list[Any]:
            return await load_open_trackings(session, limit=0)

        monkeypatch.setattr(consumer_module, "load_open_trackings", nothing)
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            assert await count_open_trackings(session) == 1
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5))
        assert shadow_trackings_unswept._value.get() == 1  # pyright: ignore[reportPrivateUsage]


class TestLostConfirmation:
    async def test_a_decision_that_lost_its_attestation_never_enters(
        self, tracked: dict[str, Any]
    ) -> None:
        """Simulates a crash between the commit and the confirmation: the row is
        durable but nothing proves it was durable before the open it chose."""
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            await session.execute(
                text(
                    "UPDATE signal_outcomes SET meta = jsonb_set(meta, "
                    "'{entry_plan,confirmed_at}', 'null'::jsonb)"
                )
            )
        await _add(tracked, AFTER_CUT)
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5))
        outcome = await _outcome(tracked)
        assert outcome.tracking_state is ShadowTrackingState.NO_ENTRY
        assert outcome.no_entry_reason == "late:unconfirmed"
        assert outcome.virtual_entry is None
        assert (await _episode(tracked)).open_outcome_signal_id is None


class TestRearm:
    async def test_a_bar_before_the_end_cannot_rearm_the_slot(
        self, tracked: dict[str, Any]
    ) -> None:
        """Out of order: the tracking ended at 12:03, and a bar that closed at
        12:00 proves nothing about the condition *after* that end."""
        await _add(tracked, AFTER_CUT)
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5, seconds=5))
        assert (await _episode(tracked)).armed is False
        await evaluate_slot(
            tracked["factory"],
            tracked["redis"],
            version=tracked["version"],
            market=tracked["market"],
            bar_close=CUT,
            config=CONFIG,
            clock=clock_at(CUT + timedelta(minutes=5, seconds=10)),
        )
        assert (await _episode(tracked)).armed is False

    async def test_a_false_condition_after_the_end_rearms_once(
        self, tracked: dict[str, Any]
    ) -> None:
        await _add(tracked, AFTER_CUT)
        await sweep_outcomes(tracked["factory"], CONFIG, now=CUT + timedelta(minutes=5, seconds=5))
        for _restart in range(2):  # a restart re-processing the same bar
            evaluation = await evaluate_slot(
                tracked["factory"],
                tracked["redis"],
                version=tracked["version"],
                market=tracked["market"],
                bar_close=CUT + MINUTE * 5,
                config=CONFIG,
                clock=clock_at(CUT + timedelta(minutes=5, seconds=20)),
            )
            assert evaluation.state.value == "not_triggered"
        episode = await _episode(tracked)
        assert episode.armed is True
        assert episode.last_bar_close == CUT + MINUTE * 5
        async with role_session(tracked["factory"], db_role="hunter_worker") as session:
            signals = (await session.execute(text("SELECT count(*) FROM agent_signals"))).scalar()
        assert signals == 1
