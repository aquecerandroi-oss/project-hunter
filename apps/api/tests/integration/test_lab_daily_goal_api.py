"""Daily-goal HTTP, historical eligibility and per-bet sizing on Postgres."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_core.db.models.market_data import Candle
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import StrategyVersionStatus, Timeframe
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
    virtual_entry: Decimal | None = Decimal("100"),
    virtual_stop: Decimal | None = Decimal("99"),
    assumed_costs: Mapping[str, object] | None = ASSUMED_COSTS,
) -> None:
    signal, outcome = fx.build_shadow_signal(
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        r_multiple=r_multiple,
    )
    signal.supporting_features = {
        "cohort": "prospective",
        "observation_ts": decision_at.isoformat(),
    }
    outcome.virtual_entry, outcome.virtual_stop = virtual_entry, virtual_stop
    outcome.meta = {} if assumed_costs is None else {"assumed_costs": assumed_costs}
    async with session_factory() as session:
        session.add_all([signal, outcome])
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


async def _read(client: httpx.AsyncClient, actor: Actor, day: date) -> dict[str, Any]:
    assert actor.org_id is not None
    response = await client.get(
        _daily_goal_url(actor.org_id), params={"day": day.isoformat()}, headers=actor.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


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
        versions: list[uuid.UUID] = []
        for k in range(1, 4):
            _, vid = await fx.seed_strategy_version(
                session_factory, activated_at=datetime(2026, 1, k, tzinfo=UTC), version=f"v{k}"
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
        body = await _read(client, actor, self.DAY)
        assert body["unique_bets"] == 1
        assert body["pooled_bets"] == 3
        assert body["unique_r"] == "1"  # v1 activated first, wins the dedupe
        assert body["pooled_r"] == "6"
        assert body["dedupe_order"] == "activated_at asc, strategy_version_id asc, signal_id asc"

    async def test_explain_uses_the_version_emitted_index(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            plan = (
                await session.execute(
                    text(
                        "EXPLAIN SELECT s.id FROM agent_signals s "
                        "JOIN signal_outcomes o ON o.signal_id = s.id "
                        "WHERE s.strategy_version_id = '00000000-0000-0000-0000-000000000000' "
                        "AND s.emitted_at >= '2026-01-01' AND s.emitted_at < '2026-01-02'"
                    )
                )
            ).scalars()
            rows = "\n".join(str(line) for line in plan)
        assert "ix_agent_signals_version_cohort_emitted" in rows, rows


class TestParticipationBinds:
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
            open_time=self.ENTRY_TS - timedelta(minutes=1),
            quote_volume=Decimal("200000"),
        )
        await _seed_candle(
            session_factory,
            market_id=market_id,
            open_time=self.ENTRY_TS,
            quote_volume=Decimal("1000000"),
        )
        await _seed_bet(
            session_factory,
            version_id=version_id,
            market_id=market_id,
            decision_at=self.ENTRY_TS - timedelta(minutes=1),
            entry_ts=self.ENTRY_TS,
            exit_ts=self.EXIT_TS,
            r_multiple=Decimal("1"),
        )
        body = await _read(client, actor, self.DAY)
        assert body["portfolio"]["source"] == "equity_snapshot"
        assert body["value_of_1r"]["real_brl_p50"] == "140"
        assert body["value_of_1r"]["sample_size"] == 1
        assert body["progress"]["real_brl"] == "140"
        assert body["progress"]["required_1r_brl"] == "9000"
        assert body["value_of_1r"]["real_usdt_p50"] == "28"
        assert body["progress"]["real_usdt"] == "28"
        assert body["fx"] == {
            "rate": "5",
            "source": "binance.spot.ticker",
            "observed_at": wallet_as_of.isoformat().replace("+00:00", "Z"),
            "available_at": wallet_as_of.isoformat().replace("+00:00", "Z"),
        }
        assert body["fx_reason"] is None
        series_point = next(p for p in body["series_30d"] if p["day"] == self.DAY.isoformat())
        assert series_point["unique_usdt"] == "28"
        later = self.ENTRY_TS + timedelta(minutes=2)
        await _seed_candle(
            session_factory,
            market_id=market_id,
            open_time=later - timedelta(minutes=1),
            quote_volume=Decimal("1000000"),
        )
        await _seed_bet(
            session_factory,
            version_id=version_id,
            market_id=market_id,
            decision_at=later,
            entry_ts=later,
            exit_ts=self.EXIT_TS,
            r_multiple=Decimal("-1"),
        )
        progress = (await _read(client, actor, self.DAY))["progress"]
        assert progress["real_usdt"] == "0"
        assert progress["real_usdt_summed"] == "-22"
        assert progress["real_brl_summed"] == "-110"


async def test_retired_version_counts_on_its_active_day_only(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    actor = await create_org(client, make_actor("a378c-history"), f"History {uuid.uuid4().hex[:6]}")
    market_id = await fx.seed_lab_market(session_factory)
    _, version_id = await fx.seed_strategy_version(
        session_factory,
        activated_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
        deprecated_at=datetime(2026, 9, 9, 2, tzinfo=UTC),
        status=StrategyVersionStatus.DEPRECATED,
    )
    for day in (8, 9):
        ts = datetime(2026, 9, day, 15, tzinfo=UTC)
        await _seed_bet(
            session_factory,
            version_id=version_id,
            market_id=market_id,
            decision_at=ts,
            entry_ts=ts,
            exit_ts=ts,
            r_multiple=Decimal("-7"),
        )
    assert actor.org_id is not None
    for day, expected in ((8, "-7"), (9, "0")):
        body = await _read(client, actor, date(2026, 9, day))
        assert body["unique_r"] == expected
        assert body["series_30d"][-1]["unique_r"] == expected
        if day == 9:
            assert body["series_30d"][-2]["unique_r"] == "-7"


class TestFxMissing:
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
        await _seed_bet(
            session_factory,
            version_id=version_id,
            market_id=market_id,
            decision_at=self.ENTRY_TS - timedelta(minutes=1),
            entry_ts=self.ENTRY_TS,
            exit_ts=self.EXIT_TS,
            r_multiple=Decimal("1"),
        )
        body = await _read(client, actor, self.DAY)
        assert body["unique_r"] == "1"  # the bet itself is real
        assert body["fx"] is None
        assert body["fx_reason"] == "no_fx_observation"
        assert body["portfolio"]["source"] == "no_portfolio"
        for field in ("real_brl_p50", "real_brl_p10", "real_brl_p90", "real_usdt_p50"):
            assert body["value_of_1r"][field] is None
        assert body["value_of_1r"]["reason"] is not None
        for field in ("real_brl", "distance_to_goal_real_brl", "required_unique_r", "real_usdt"):
            assert body["progress"][field] is None
        series_point = next(p for p in body["series_30d"] if p["day"] == self.DAY.isoformat())
        assert series_point["unique_usdt"] is None
