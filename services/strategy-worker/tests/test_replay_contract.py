"""The replay engine's contract, without a database — T3.19b.

Everything here is arithmetic or a refusal: which bars a window visits, which
clock a replayed decision reads, how big a pool the budget allows, what the
queue accepts, and the two places a replay cohort is stopped (no outbox row on
the way out, ``cohort_not_live`` at the execution bridge). The integration
proofs live in ``test_replay_engine.py`` and ``test_replay_lookahead.py``.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_core.domain.digests import markets_digest
from hunter_core.domain.enums import ShadowCohort, Timeframe, TradeDirection
from hunter_core.strategies.base import assumed_costs
from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_execution_worker.bridge_repo import ShadowSignal
from hunter_execution_worker.bridge_screen import screen_signal
from hunter_execution_worker.wallet import WalletRef
from hunter_strategy_worker.persist import is_published_cohort
from hunter_strategy_worker.plan import plan_entry
from hunter_strategy_worker.replay.budget import (
    ReplayBudget,
    ReplayRequest,
    live_lane_degraded,
    refuse_direct_run,
    workers_for,
)
from hunter_strategy_worker.replay.environment import (
    REPLAY_DECISION_LAG_S,
    ReplayClock,
    ReplayHotState,
)
from hunter_strategy_worker.replay.ledger import ReplayRun, record_slice
from hunter_strategy_worker.replay.simulate import ReplayWindow, bar_closes

pytestmark = pytest.mark.unit

RUN_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")
COHORT = ShadowCohort.replay(RUN_ID)


class TestWindow:
    """Which bar closes a window visits — the mass the throughput number counts."""

    def test_a_day_of_5m_closes_is_288_bars(self) -> None:
        window = ReplayWindow(datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 8, 2, tzinfo=UTC))
        closes = list(bar_closes(window, Timeframe.M5))
        assert len(closes) == 288
        assert closes[0] == datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
        assert closes[-1] == datetime(2026, 8, 1, 23, 55, tzinfo=UTC)

    def test_a_day_of_15m_closes_is_96_bars(self) -> None:
        window = ReplayWindow(datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 8, 2, tzinfo=UTC))
        assert len(list(bar_closes(window, Timeframe.M15))) == 96

    def test_31_days_of_5m_is_8928_bars(self) -> None:
        window = ReplayWindow(datetime(2026, 8, 8, tzinfo=UTC), datetime(2026, 9, 8, tzinfo=UTC))
        assert window.days == 31.0
        assert len(list(bar_closes(window, Timeframe.M5))) == 31 * 288

    def test_a_start_off_the_grid_begins_at_the_next_close(self) -> None:
        window = ReplayWindow(
            datetime(2026, 8, 1, 0, 1, tzinfo=UTC), datetime(2026, 8, 1, 0, 20, tzinfo=UTC)
        )
        assert list(bar_closes(window, Timeframe.M5)) == [
            datetime(2026, 8, 1, 0, 5, tzinfo=UTC),
            datetime(2026, 8, 1, 0, 10, tzinfo=UTC),
            datetime(2026, 8, 1, 0, 15, tzinfo=UTC),
        ]

    def test_the_end_is_exclusive_so_two_slices_never_share_a_bar(self) -> None:
        cut = datetime(2026, 8, 1, 12, tzinfo=UTC)
        first = set(bar_closes(ReplayWindow(datetime(2026, 8, 1, tzinfo=UTC), cut), Timeframe.M5))
        second = set(bar_closes(ReplayWindow(cut, datetime(2026, 8, 2, tzinfo=UTC)), Timeframe.M5))
        assert not first & second
        assert len(first) + len(second) == 288

    def test_an_empty_window_is_refused_instead_of_producing_nothing(self) -> None:
        moment = datetime(2026, 8, 1, tzinfo=UTC)
        with pytest.raises(ValueError, match="empty replay window"):
            ReplayWindow(moment, moment)


class TestClock:
    """The replay's own clock, and the entry bar it implies."""

    def test_the_clock_is_frozen_at_bar_close_plus_lag(self) -> None:
        bar_close = datetime(2026, 8, 1, 12, 5, tzinfo=UTC)
        clock = ReplayClock(bar_close)
        assert clock() == bar_close + timedelta(seconds=REPLAY_DECISION_LAG_S)
        assert clock() == clock(), "two reads of the same bar must give the same instant"

    def test_the_entry_is_the_next_minute_open_and_never_late(self) -> None:
        bar_close = datetime(2026, 8, 1, 12, 5, tzinfo=UTC)
        costs = assumed_costs(dict(VOLUME_ANOMALY_V1.default_parameters))
        decision_at = ReplayClock(bar_close)()
        plan = plan_entry(
            source_bar_close=bar_close, decision_at=decision_at, costs=costs, now=decision_at
        )
        assert plan.entry_bar_open == datetime(2026, 8, 1, 12, 6, tzinfo=UTC)
        assert plan.delay_s == 60
        assert plan.delay_s <= costs.max_entry_delay_s
        assert plan.late_reason is None

    def test_a_lag_of_a_whole_minute_would_move_the_entry(self) -> None:
        """Why REPLAY_DECISION_LAG_S has to stay under 60 s."""
        bar_close = datetime(2026, 8, 1, 12, 5, tzinfo=UTC)
        costs = assumed_costs(dict(VOLUME_ANOMALY_V1.default_parameters))
        decision_at = ReplayClock(bar_close, lag_s=60)()
        plan = plan_entry(
            source_bar_close=bar_close, decision_at=decision_at, costs=costs, now=decision_at
        )
        assert plan.entry_bar_open == datetime(2026, 8, 1, 12, 7, tzinfo=UTC)
        assert plan.delay_s == 120


class TestHotState:
    """The empty answers, and the refusal to invent a fourth one."""

    async def test_the_three_live_reads_answer_nothing(self) -> None:
        state = ReplayHotState()
        assert await state.xrevrange("market.universe.changed", count=50) == []
        assert await state.lrange("mkt:binance:BTCUSDT:1m", 0, 19) == []
        assert await state.hgetall("mkt:binance:BTCUSDT:deriv") == {}

    def test_any_other_redis_command_is_absent_rather_than_empty(self) -> None:
        assert not hasattr(ReplayHotState(), "get")
        assert not hasattr(ReplayHotState(), "set")


class TestOutbox:
    """A replay writes three rows, not four (``persist.is_published_cohort``)."""

    def test_a_replay_cohort_is_never_published(self) -> None:
        assert is_published_cohort(COHORT) is False

    def test_prospective_and_replication_still_publish(self) -> None:
        assert is_published_cohort(ShadowCohort.PROSPECTIVE) is True
        assert is_published_cohort(ShadowCohort.replication(uuid.uuid4(), 7)) is True


def _paper_signal(cohort: str) -> ShadowSignal:
    """A signal that passes every gate before the cohort one — worst case.

    ``purpose = paper`` on both the column and the envelope, so the refusal
    under test is the *cohort* and nothing else. A ``research_only`` signal is
    refused earlier and would prove a different barrier.
    """
    return ShadowSignal(
        signal_id=uuid.uuid4(),
        strategy_version_id=uuid.uuid4(),
        perp_market_id=uuid.uuid4(),
        exchange_id=uuid.uuid4(),
        base_asset_id=uuid.uuid4(),
        quote_asset_id=uuid.uuid4(),
        direction=TradeDirection.LONG,
        entry_ref=Decimal("100"),
        stop=Decimal("99"),
        target=Decimal("102"),
        assumed_costs=AssumedCosts(
            spread_bps=Decimal("2"),
            slippage_bps=Decimal("5"),
            fee_bps=Decimal("4"),
            max_entry_delay_s=120,
        ),
        source_bar_close=datetime(2026, 8, 1, 12, tzinfo=UTC),
        emitted_at=datetime(2026, 8, 1, 12, 0, 2, tzinfo=UTC),
        purpose="paper",
        envelope_purpose="paper",
        cohort=cohort,
        version_active=True,
    )


class TestBridgeRefusesReplay:
    """T3.15e's third barrier, exercised with a cohort that now really exists."""

    async def test_a_replay_cohort_is_refused_cohort_not_live(self) -> None:
        screened = await screen_signal(
            cast("Any", None),
            wallet=WalletRef(organization_id=uuid.uuid4(), portfolio_id=uuid.uuid4()),
            signal=_paper_signal(COHORT),
            now=datetime(2026, 8, 1, 12, 1, tzinfo=UTC),
        )
        assert screened.refused == "cohort_not_live"
        assert screened.eligible is False

    async def test_the_refusal_happens_before_any_database_access(self) -> None:
        """The session above is ``None``: reaching Postgres would raise.

        That is the assertion, not a shortcut — the bridge must refuse a replay
        by name *before* it looks up a wallet, a spot pair or an agent, which is
        what makes the barrier independent of every query behind it.
        """
        screened = await screen_signal(
            cast("Any", None),
            wallet=WalletRef(organization_id=uuid.uuid4(), portfolio_id=uuid.uuid4()),
            signal=_paper_signal(COHORT),
            now=datetime(2026, 8, 1, 12, 1, tzinfo=UTC),
        )
        assert screened.refused == "cohort_not_live"

    async def test_the_same_signal_under_prospective_reaches_the_next_gate(self) -> None:
        """Contra-proof: without the cohort refusal this signal would go on.

        It fails later (``source_bar_unavailable`` is impossible here, so the
        next gate is the entry window) — the point is only that
        ``cohort_not_live`` is what stopped the replay, not some other rule.
        """
        screened = await screen_signal(
            cast("Any", None),
            wallet=WalletRef(organization_id=uuid.uuid4(), portfolio_id=uuid.uuid4()),
            signal=_paper_signal(ShadowCohort.PROSPECTIVE),
            now=datetime(2026, 8, 1, 18, tzinfo=UTC),
        )
        assert screened.refused == "entry_window_closed"


class TestBudget:
    """``REPLAY_BUDGET``: how much machine the lane may take."""

    def test_the_vps_budget_is_three_of_twelve_vcpu(self) -> None:
        """``floor(12 x 0.33) = 3`` — the floor, never a round up onto the live lane."""
        assert workers_for(ReplayBudget(), cpu_count=12) == 3

    def test_the_share_never_rounds_down_to_zero_workers(self) -> None:
        assert workers_for(ReplayBudget(cpu_share=0.1), cpu_count=2) == 1

    def test_the_ceiling_wins_over_a_bigger_machine(self) -> None:
        assert workers_for(ReplayBudget(max_workers=4), cpu_count=64) == 4

    def test_a_share_of_zero_still_leaves_one_slow_worker(self) -> None:
        assert workers_for(ReplayBudget(cpu_share=0.0), cpu_count=12) == 1


class _FakeRedis:
    """Only ``hgetall``; the gate reads nothing else."""

    def __init__(self, fields: dict[str, str] | None = None, *, fail: bool = False) -> None:
        self._fields = fields
        self._fail = fail

    async def hgetall(self, _key: str) -> dict[str, str]:
        if self._fail:
            raise RuntimeError("redis down")
        return dict(self._fields or {})


class TestReadinessGate:
    """The replay pauses when the live lane is not healthy."""

    NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)

    def _redis(self, **fields: str) -> Any:
        return _FakeRedis(fields)

    async def test_a_healthy_heartbeat_does_not_pause(self) -> None:
        redis = self._redis(ts="2026-08-01T11:59:55+00:00", outbox_lag_s="0.4")
        assert await live_lane_degraded(redis, ReplayBudget(), now=self.NOW) is None

    async def test_a_missing_heartbeat_pauses(self) -> None:
        assert (
            await live_lane_degraded(cast("Any", _FakeRedis({})), ReplayBudget(), now=self.NOW)
            == "heartbeat_missing"
        )

    async def test_a_stale_heartbeat_pauses_with_its_age(self) -> None:
        redis = self._redis(ts="2026-08-01T11:55:00+00:00", outbox_lag_s="0")
        assert (
            await live_lane_degraded(redis, ReplayBudget(), now=self.NOW) == "heartbeat_stale:300s"
        )

    async def test_an_outbox_lag_past_the_alert_pauses(self) -> None:
        redis = self._redis(ts="2026-08-01T11:59:55+00:00", outbox_lag_s="185.0")
        assert await live_lane_degraded(redis, ReplayBudget(), now=self.NOW) == "outbox_lag:185s"

    async def test_redis_down_pauses_rather_than_assuming_health(self) -> None:
        redis = cast("Any", _FakeRedis(fail=True))
        assert (
            await live_lane_degraded(redis, ReplayBudget(), now=self.NOW) == "heartbeat_unreadable"
        )

    async def test_the_gate_can_be_turned_off_deliberately(self) -> None:
        budget = ReplayBudget(pause_on_degraded=False)
        assert await live_lane_degraded(cast("Any", _FakeRedis({})), budget, now=self.NOW) is None


class _ClosingFakeRedis(_FakeRedis):
    """``_FakeRedis`` plus a spy on ``aclose`` (:func:`refuse_direct_run` owns its client)."""

    def __init__(self, fields: dict[str, str] | None = None) -> None:
        super().__init__(fields)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class TestRefuseDirectRun:
    """The same gate, wired for a one-off ``--version``/``--from``/``--to`` run (T3.74).

    Before this, only :data:`live_lane_degraded` itself was reachable from a test:
    nothing in ``replay/run.py`` ever called it, on either entry point (T3.74
    notes §2).
    """

    async def test_a_healthy_lane_returns_no_reason_and_closes_the_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No ``now=`` on this path (it reads the real heartbeat), so the fixture
        # heartbeat has to be fresh against the wall clock, not a frozen date.
        fresh = (datetime.now(UTC)).isoformat()
        fake = _ClosingFakeRedis({"ts": fresh, "outbox_lag_s": "0"})

        def fake_create_redis(settings: object) -> _ClosingFakeRedis:
            del settings
            return fake

        monkeypatch.setattr("hunter_core.redis.create_redis", fake_create_redis)
        reason = await refuse_direct_run(cast("Any", object()), ReplayBudget())
        assert reason is None
        assert fake.closed is True

    async def test_a_degraded_lane_is_reported_and_the_client_still_closes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _ClosingFakeRedis({})

        def fake_create_redis(settings: object) -> _ClosingFakeRedis:
            del settings
            return fake

        monkeypatch.setattr("hunter_core.redis.create_redis", fake_create_redis)
        reason = await refuse_direct_run(cast("Any", object()), ReplayBudget())
        assert reason == "heartbeat_missing"
        assert fake.closed is True


class TestQueue:
    """What the plantão may enqueue, and what the engine refuses to read."""

    def test_a_request_round_trips(self) -> None:
        request = ReplayRequest.new(
            strategy_version_id=uuid.uuid4(),
            window_from=datetime(2026, 8, 8, tzinfo=UTC),
            window_to=datetime(2026, 9, 8, tzinfo=UTC),
            markets=("BTCUSDT", "ETHUSDT"),
            requested_by="sexta-feira",
            run_id=RUN_ID,
        )
        assert request.cohort == COHORT
        assert ReplayRequest.from_json(request.to_json()) == request

    def test_a_non_replay_cohort_in_the_queue_is_refused(self) -> None:
        request = ReplayRequest.new(
            strategy_version_id=uuid.uuid4(),
            window_from=datetime(2026, 8, 8, tzinfo=UTC),
            window_to=datetime(2026, 9, 8, tzinfo=UTC),
            requested_by="sexta-feira",
            run_id=RUN_ID,
        )
        payload = request.to_json().replace(COHORT, ShadowCohort.PROSPECTIVE)
        with pytest.raises(ValueError, match="is not a replay cohort"):
            ReplayRequest.from_json(payload)


class TestLedger:
    """The receipt of a run, in the shape the pending ``replay_runs`` row wants."""

    def _run(self, *, bars: int = 26_784, seconds: float = 300.0) -> ReplayRun:
        return ReplayRun(
            run_id=RUN_ID,
            cohort=COHORT,
            strategy_version_id=uuid.uuid4(),
            version_label="volume_anomaly v1",
            window_from=datetime(2026, 8, 8, tzinfo=UTC),
            window_to=datetime(2026, 9, 8, tzinfo=UTC),
            markets=("binance:BTCUSDT", "binance:ETHUSDT", "binance:SOLUSDT"),
            started_at=datetime(2026, 9, 8, 10, tzinfo=UTC),
            finished_at=datetime(2026, 9, 8, 10, 5, tzinfo=UTC),
            bars_evaluated=bars,
            signals=41,
            outcomes_resolved=39,
            outcomes_open=2,
            seconds=seconds,
            decision_lag_s=REPLAY_DECISION_LAG_S,
            workers=4,
            evaluations_by_state={"not_triggered": 26_700, "triggered": 41, "unavailable": 43},
        )

    def test_bars_per_second_is_bars_over_seconds(self) -> None:
        assert self._run().bars_per_second == pytest.approx(89.28)

    def test_a_run_that_took_no_time_reports_zero_instead_of_dividing(self) -> None:
        assert self._run(seconds=0.0).bars_per_second == 0.0

    def test_the_row_carries_every_column_the_table_will_need(self) -> None:
        row = self._run().to_jsonable()
        assert set(row) >= {
            "run_id",
            "cohort",
            "strategy_version_id",
            "window_from",
            "window_to",
            "markets",
            "started_at",
            "finished_at",
            "bars_evaluated",
            "signals",
            "outcomes_resolved",
            "seconds",
        }
        assert row["market_count"] == 3
        assert row["window_from"] == "2026-08-08T00:00:00+00:00"
        assert row["decision_lag_s"] == REPLAY_DECISION_LAG_S
        assert row["markets_digest"] == markets_digest(list(self._run().markets))

    def test_the_digest_follows_the_markets_instead_of_being_a_field(self) -> None:
        """``markets_digest`` is a property, not a constructor argument — the
        fourth column of the slice key since ``0018`` (DATABASE.md §30).

        A field could be handed a digest that does not describe ``markets``, and
        that is precisely the failure mode: two different market slices sharing
        a digest collide again under ``ON CONFLICT DO NOTHING``, which is how
        T3.62 wrote 32 slices and kept 8 receipts. Derived, it cannot disagree
        — and the dispatch order the tuple happens to carry cannot fabricate a
        second slice of work that already has a receipt.
        """
        run = self._run()
        reordered = replace(run, markets=tuple(reversed(run.markets)))
        assert run.markets_digest == reordered.markets_digest
        assert run.markets_digest != markets_digest(list(run.markets)[:2])

    async def test_a_database_still_at_0012_keeps_the_other_two_branches(self) -> None:
        """``replay_runs`` missing degrades; it never poisons the transaction.

        A statement against a relation that does not exist aborts the *whole*
        transaction, which would take the ``system_events`` half of the receipt
        down with it — a replay of thirty minutes reporting nothing at all
        because a deploy ran the image before the migration. So ``record_slice``
        asks ``to_regclass`` first (the shape DATABASE.md §17.2 gives the
        scanner's baseline-lock probe), logs an ``error`` naming the revision,
        and returns ``None`` without issuing an ``INSERT``.
        """
        session = _SessionWithoutTheTable()
        assert await record_slice(cast(Any, session), self._run()) is None
        assert len(session.statements) == 1, "the probe ran; the INSERT never did"
        assert "to_regclass" in session.statements[0]


class _SessionWithoutTheTable:
    """A session on a database still at ``0012``: ``to_regclass`` answers NULL."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def scalar(self, statement: Any, params: Any = None) -> Any:
        self.statements.append(str(statement))
        return None
