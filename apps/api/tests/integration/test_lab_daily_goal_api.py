"""Integration tests: ``GET /api/v1/orgs/{org_id}/lab/daily-goal`` — T3.78.

Three scenarios the brief names explicitly, over a real Postgres:

1. Three active versions decide on the same bet the same day ->
   ``unique_r`` counts it once, ``pooled_r`` counts all three.
2. A market with a thin 1-minute quote volume (200 000 USDT) prices ``1R``
   under ``max_participation_pct`` — the ceiling T3.60 found binding almost
   everywhere.
3. No FX observation exists by the day's end -> every ``real_brl`` field is
   ``None`` with a named reason, never a default rate.

Days are chosen far apart on the calendar (2026-01-15, 2026-01-20,
2020-06-15) so each scenario's population, and each scenario's FX/portfolio
state, cannot leak into another test's — including tests in other files that
insert ``fx_observations`` at real "now" (a global, session-shared table,
same caveat ``test_portfolio_api.py``'s ``TestBrlUnavailable`` already
documents).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.market_data import Candle
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import (
    OutcomeResult,
    ShadowTrackingState,
    Timeframe,
    TradeDirection,
)
from hunter_core.domain.types import uuid7
from hunter_core.portfolio.opening import open_paper_wallet

from . import lab_fixtures as fx
from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

CAPITAL_BRL = Decimal("100000")
ASSUMED_COSTS = {"spread_bps": "10", "slippage_bps": "5", "fee_bps": "10", "max_entry_delay_s": 30}


async def _seed_bet(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    version_id: uuid.UUID,
    market_id: uuid.UUID,
    decision_at: datetime,
    entry_ts: datetime | None,
    exit_ts: datetime,
    r_multiple: Decimal | None,
    virtual_entry: Decimal | None = None,
    virtual_stop: Decimal | None = None,
    assumed_costs: Mapping[str, object] | None = None,
) -> None:
    """One ``agent_signals`` + ``signal_outcomes`` row, minimal but exact
    about the fields ``LabDailyGoalRepository`` reads."""
    signal_id = uuid7()
    async with session_factory() as session:
        session.add(
            AgentSignal(
                id=signal_id,
                strategy_version_id=version_id,
                market_id=market_id,
                params_hash="t378-fixture",
                direction=TradeDirection.LONG,
                confidence=Decimal("0.5"),
                supporting_features={
                    "cohort": "prospective",
                    "observation_ts": decision_at.isoformat(),
                },
                emitted_at=decision_at,
            )
        )
        session.add(
            SignalOutcome(
                signal_id=signal_id,
                virtual_entry=virtual_entry,
                virtual_stop=virtual_stop,
                entry_ts=entry_ts,
                exit_price=Decimal("101"),
                exit_ts=exit_ts,
                result=OutcomeResult.TARGET,
                r_multiple=r_multiple,
                tracking_state=ShadowTrackingState.TERMINAL,
                meta={} if assumed_costs is None else {"assumed_costs": assumed_costs},
            )
        )
        await session.commit()


async def _seed_candle(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    market_id: uuid.UUID,
    open_time: datetime,
    quote_volume: Decimal,
) -> None:
    async with session_factory() as session:
        session.add(
            Candle(
                market_id=market_id,
                timeframe=Timeframe.M1,
                open_time=open_time,
                open=Decimal("100"),
                high=Decimal("100.5"),
                low=Decimal("99.5"),
                close=Decimal("100"),
                volume=Decimal("2000"),
                quote_volume=quote_volume,
                is_final=True,
            )
        )
        await session.commit()


def _daily_goal_url(org_id: uuid.UUID) -> str:
    return f"/api/v1/orgs/{org_id}/lab/daily-goal"


async def test_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get(_daily_goal_url(uuid.uuid4()))
    assert response.status_code == 401


async def test_a_membership_less_org_id_is_a_404(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor = make_actor("t378-no-membership")
    response = await client.get(_daily_goal_url(uuid.uuid4()), headers=actor.headers)
    assert response.status_code == 404


class TestDedupe:
    """Three active versions, one bet, one day.

    2026-09-10 is inside the hardcoded initial partitions
    (``0001_initial_schema``: 2026-09..2026-12) — every date this file uses
    for a row on a partitioned table (``candles``, ``portfolio_equity_snapshots``)
    has to be, or the insert itself fails with a ``CheckViolationError``
    before the endpoint is ever called.
    """

    DAY = date(2026, 9, 10)
    BAR_CLOSE = datetime(2026, 9, 10, 14, 0, tzinfo=UTC)
    EXIT_TS = datetime(2026, 9, 10, 15, 0, tzinfo=UTC)

    async def test_unique_r_counts_once_pooled_counts_three(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await create_org(
            client, make_actor("t378-dedupe"), f"Dedupe {uuid.uuid4().hex[:6]}"
        )
        market_id = await fx.seed_lab_market(session_factory)
        _, v1 = await fx.seed_strategy_version(
            session_factory, activated_at=datetime(2026, 1, 1, tzinfo=UTC), version="v1"
        )
        versions = [v1]
        for k, activated in enumerate(
            (datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC)), start=2
        ):
            _, vid = await fx.seed_strategy_version(
                session_factory, activated_at=activated, version=f"v{k}"
            )
            versions.append(vid)

        for r, version_id in zip((Decimal("1"), Decimal("2"), Decimal("3")), versions, strict=True):
            await _seed_bet(
                session_factory,
                version_id=version_id,
                market_id=market_id,
                decision_at=self.BAR_CLOSE,
                entry_ts=self.BAR_CLOSE,
                exit_ts=self.EXIT_TS,
                r_multiple=r,
            )

        assert actor.org_id is not None
        response = await client.get(
            _daily_goal_url(actor.org_id),
            params={"day": self.DAY.isoformat()},
            headers=actor.headers,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["unique_bets"] == 1
        assert body["pooled_bets"] == 3
        assert body["unique_r"] == "1"  # v1 activated first, wins the dedupe
        assert body["pooled_r"] == "6"
        assert body["dedupe_order"] == "activated_at asc, strategy_version_id asc, signal_id asc"

    async def test_explain_uses_the_version_emitted_index(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Best-effort plan check on the seeded population (a handful of
        rows) — not a substitute for measuring against a T3.62b-size ledger,
        which this suite does not build (see ``notes-T3.78.md`` CONCERN)."""
        async with session_factory() as session:
            plan = (
                await session.execute(
                    text(
                        "EXPLAIN SELECT s.id FROM agent_signals s "
                        "JOIN signal_outcomes o ON o.signal_id = s.id "
                        "WHERE s.strategy_version_id = :vid "
                        "AND s.emitted_at >= :start AND s.emitted_at < :end"
                    ),
                    {
                        "vid": uuid.uuid4(),
                        "start": datetime(2026, 1, 1, tzinfo=UTC),
                        "end": datetime(2026, 1, 2, tzinfo=UTC),
                    },
                )
            ).scalars()
            rows = "\n".join(str(line) for line in plan)
        assert "ix_agent_signals_version_cohort_emitted" in rows, rows


class TestParticipationBinds:
    """A market whose 1-minute quote volume (200 000 USDT) makes the
    participation ceiling win over the risk-per-trade budget.

    Dated well after ``TestFxMissing``'s cutoff (2026-09-02T03:00Z) so this
    class's own FX observation can never leak into that scenario — the
    predicate that matters is ``available_at <= window_end`` (a value
    comparison), never which test happened to run first.
    """

    DAY = date(2026, 9, 6)
    ENTRY_TS = datetime(2026, 9, 6, 14, 5, tzinfo=UTC)
    EXIT_TS = datetime(2026, 9, 6, 15, 0, tzinfo=UTC)
    RATE = Decimal("5.00")

    async def test_real_brl_is_priced_under_the_participation_ceiling(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await create_org(
            client, make_actor("t378-participation"), f"Participation {uuid.uuid4().hex[:6]}"
        )
        wallet_as_of = datetime(2026, 9, 5, tzinfo=UTC)
        fx_id = uuid7()
        async with session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO fx_observations (id, pair, rate, source, observed_at, "
                    "available_at, raw) VALUES (:id, 'USDTBRL', :rate, "
                    "'binance.spot.ticker', :ts, :ts, '{}'::jsonb)"
                ),
                {"id": fx_id, "rate": self.RATE, "ts": wallet_as_of},
            )
            await session.commit()
        assert actor.org_id is not None and actor.workspace_id is not None
        async with tenant_session(
            session_factory, actor.org_id, actor.user_id, db_role="hunter_worker"
        ) as session:
            observation = await FxObservationRepository(session).get(fx_id)
            assert observation is not None
            await open_paper_wallet(
                session,
                organization_id=actor.org_id,
                workspace_id=actor.workspace_id,
                fx=observation,
                as_of=wallet_as_of,
                capital_brl=CAPITAL_BRL,
            )

        market_id = await fx.seed_lab_market(session_factory)
        _, version_id = await fx.seed_strategy_version(
            session_factory, activated_at=datetime(2026, 1, 10, tzinfo=UTC)
        )
        await _seed_candle(
            session_factory,
            market_id=market_id,
            open_time=self.ENTRY_TS.replace(second=0, microsecond=0),
            quote_volume=Decimal("200000"),
        )
        await _seed_bet(
            session_factory,
            version_id=version_id,
            market_id=market_id,
            decision_at=self.ENTRY_TS - timedelta(minutes=1),
            entry_ts=self.ENTRY_TS,
            exit_ts=self.EXIT_TS,
            r_multiple=Decimal("1"),
            virtual_entry=Decimal("100"),
            virtual_stop=Decimal("99"),
            assumed_costs=ASSUMED_COSTS,
        )

        response = await client.get(
            _daily_goal_url(actor.org_id),
            params={"day": self.DAY.isoformat()},
            headers=actor.headers,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        # equity = 100_000 BRL / 5.00 = 20_000 USDT
        # loss_fraction = 0.01 (stop) + 0.004 (round-trip cost) = 0.014
        # participation ceiling = 1% * 200_000 = 2_000 < risk budget (3_571.43)
        # value_1r_usdt = 2_000 * 0.014 = 28 -> value_1r_brl = 28 * 5.00 = 140
        assert body["portfolio"]["source"] == "equity_snapshot"
        assert body["value_of_1r"]["real_brl_p50"] == "140"
        assert body["value_of_1r"]["sample_size"] == 1
        assert body["progress"]["real_brl"] == "140"
        assert body["progress"]["required_1r_brl"] == "9000"
        # T3.78b: profit is real in USDT first (before FX), then in BRL by
        # the observed rate -- both present here, fx block names the source.
        assert body["value_of_1r"]["real_usdt_p50"] == "28"
        assert body["progress"]["real_usdt"] == "28"
        assert body["fx"] == {
            "rate": "5",
            "source": "binance.spot.ticker",
            "observed_at": wallet_as_of.isoformat().replace("+00:00", "Z"),
            "available_at": wallet_as_of.isoformat().replace("+00:00", "Z"),
        }
        assert body["fx_reason"] is None
        # The series day matching this scenario carries its own USDT figure.
        series_point = next(p for p in body["series_30d"] if p["day"] == self.DAY.isoformat())
        assert series_point["unique_usdt"] == "28"


class TestFxMissing:
    """The earliest day inside the seeded partition range, with no
    ``fx_observations`` row (nor any portfolio) available by its end ->
    every real-money field is ``None`` with a reason, never a guessed rate.

    2026-09-01: no test in this file (or, by convention, elsewhere in the
    suite — every other fixture uses ``utcnow()`` or a date at/after
    ``TestParticipationBinds``'s 2026-09-05) ever names an ``available_at``
    at or before this day's end (2026-09-02T03:00Z).
    """

    DAY = date(2026, 9, 1)
    ENTRY_TS = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    EXIT_TS = datetime(2026, 9, 1, 11, 0, tzinfo=UTC)

    async def test_real_brl_is_null_with_a_reason(
        self,
        client: httpx.AsyncClient,
        make_actor: Callable[[str], Actor],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        actor = await create_org(client, make_actor("t378-no-fx"), f"NoFx {uuid.uuid4().hex[:6]}")
        assert actor.org_id is not None
        market_id = await fx.seed_lab_market(session_factory)
        _, version_id = await fx.seed_strategy_version(
            session_factory, activated_at=datetime(2020, 6, 1, tzinfo=UTC)
        )
        await _seed_candle(
            session_factory,
            market_id=market_id,
            open_time=self.ENTRY_TS.replace(second=0, microsecond=0),
            quote_volume=Decimal("200000"),
        )
        await _seed_bet(
            session_factory,
            version_id=version_id,
            market_id=market_id,
            decision_at=self.ENTRY_TS - timedelta(minutes=1),
            entry_ts=self.ENTRY_TS,
            exit_ts=self.EXIT_TS,
            r_multiple=Decimal("1"),
            virtual_entry=Decimal("100"),
            virtual_stop=Decimal("99"),
            assumed_costs=ASSUMED_COSTS,
        )

        response = await client.get(
            _daily_goal_url(actor.org_id),
            params={"day": self.DAY.isoformat()},
            headers=actor.headers,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["unique_r"] == "1"  # the bet itself is real
        assert body["fx"] is None
        assert body["fx_reason"] == "no_fx_observation"
        assert body["portfolio"]["source"] == "no_portfolio"
        assert body["value_of_1r"]["real_brl_p50"] is None
        assert body["value_of_1r"]["real_brl_p10"] is None
        assert body["value_of_1r"]["real_brl_p90"] is None
        assert body["value_of_1r"]["reason"] is not None
        assert body["progress"]["real_brl"] is None
        assert body["progress"]["distance_to_goal_real_brl"] is None
        assert body["progress"]["required_unique_r"] is None
        # T3.78b: no equity known here either (no_portfolio), so USDT pricing
        # never even ran -- real_usdt_* is None for the same reason as
        # real_brl_*, not a separate FX-only gap (that branch is covered
        # without a database in test_lab_daily_goal_service.py, concern 5).
        assert body["value_of_1r"]["real_usdt_p50"] is None
        assert body["progress"]["real_usdt"] is None
        series_point = next(p for p in body["series_30d"] if p["day"] == self.DAY.isoformat())
        assert series_point["unique_usdt"] is None
