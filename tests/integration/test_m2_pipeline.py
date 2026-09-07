"""M2 end to end: synthetic candles -> features -> baselines -> anomaly ->
stage -> regime -> score -> ``radar:scores`` / ``opportunities`` / the real API.

The gap this file closes is written down in ``docs/reports/M2.md`` §7 and in
condition 4 of its VEREDITO: the M2 plan (``docs/plans/M2.md``, T2.8) promised an
integration test that walks one market from a labelled synthetic candle series
to a row on the Radar, and the milestone closed without it.

**What is real here and what is not.** The candles are a seeded random walk
(``services/scanner-worker/tests/test_bootstrap.py::synthetic_minutes``), shaped
in the last hour by closed-form arithmetic — a labelled fixture, never recorded
market data, and the only thing in this file that is synthetic. Postgres and
Redis are real containers, migrated by Alembic; the baselines are written by the
scanner's own bootstrap; the vector, the detectors, the stage classifier, the
regime engine and the scorer are the shipped engines; the rows are written by
``hunter_scanner_worker.persist.flush_batch``; and the last assertion is a real
``GET /api/v1/radar`` against the real FastAPI app over ``httpx.ASGITransport``.

**Where the regime lands, said out loud.** Seven synthetic days are not thirty,
and ``volatility_reference`` needs thirty days of hourly samples before it will
express an opinion. So this test does **not** manufacture a regime: it runs the
real ``RegimeEngine`` and asserts that it publishes ``UNKNOWN`` with the
structured reason ``volatility_warmup``, and that the scorer therefore reports
``market_regime`` as unavailable with ``regime_unknown`` instead of scoring it
as zero. That is the same verdict production shows today
(``docs/reports/M2.md``, item 4) and it is asserted, not tolerated.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import UUID

import pytest
from sqlalchemy import insert, select

from hunter_core.db.models.analysis import Anomaly, MarketRegimeRow, Opportunity
from hunter_core.db.models.market_data import Candle, OpenInterestHistory
from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.domain.enums import (
    AnomalyStatus,
    AnomalyType,
    MarketRegime,
    OpportunityStage,
    OpportunityStatus,
    Timeframe,
    TradeDirection,
)
from hunter_core.redis import keys
from hunter_indicators.baselines import SqlBaselineStore
from hunter_indicators.features import Quality
from hunter_indicators.opportunity import envelope_bytes
from hunter_scanner_worker.backfill import BackfillRequester
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.bootstrap import BootstrapSettings, window_for
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.coverage import read_coverage
from hunter_scanner_worker.deriv import DerivHistory
from hunter_scanner_worker.persist import WriteBatch, flush_batch
from hunter_scanner_worker.publish import publish_radar
from hunter_scanner_worker.regime import RegimeEngine
from hunter_scanner_worker.registry import MarketRef, MarketRegistry
from hunter_scanner_worker.runners import run_regime_once
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .m2_builders import (
    build_policy,
    live_revision,
    publish_coverage,
    run_bootstrap,
    seed_market,
    shape_tail,
    synthetic_minutes,
    to_candle,
    trade_rows,
    write_hot_state,
)

if TYPE_CHECKING:
    import httpx
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_scanner_worker.evaluate import Evaluation

pytestmark = pytest.mark.integration

EXCHANGE = "binance"
SYMBOL = "M2PIPEUSDT"

BOOTSTRAP_NOW = datetime(2026, 9, 20, 0, 30, tzinfo=UTC)
"""Inside the partitions ``0001`` provisions (2026-09..2026-12), like
``test_bootstrap.py``'s own ``NOW``."""

WINDOW_DAYS = 7
BUFFER_MINUTES = 400
"""Same trade-off ``test_bootstrap.py`` documents: 400 keeps a 10 080-cut replay
around a minute of CPU, at the price of the three features that need more than
400 minutes of warm-up having no bootstrap bucket at all."""

CUT = datetime(2026, 9, 20, 1, 5, tzinfo=UTC)
"""The live evaluation cut. **After** the bootstrap window's end (00:00) and
after the revisions' ``available_at`` (00:30), because ``BaselineCut`` admits a
revision only when ``available_at <= as_of`` **and** ``window_end <
observation_ts``. One minute of hysteresis happens at ``CUT - 1min``."""

FIRST_CUT = CUT - timedelta(minutes=1)
HOT_STATE_MINUTES = 1500

HOUR_VOLUME_MULTIPLIER = Decimal(4)
SPIKE_VOLUME_MULTIPLIER = Decimal(40)
HOUR_DRIFT = Decimal("0.003")
TAPE_SECONDS = 420
TRADES_PER_SECOND = 2
BUYS_PER_FOUR = 3

OI_BEFORE = Decimal(900)
OI_AFTER = Decimal(1000)
"""``deriv_hash`` publishes ``open_interest = 1000``; the history steps up an
hour before the cut, so ``open_interest_change_1h = 100/900 = 0.1111...``, over
the ``+2%`` the EARLY confirmation asks for."""


class Bootstrapped(NamedTuple):
    """What the module-scoped, once-only preparation leaves in the database."""

    market_id: UUID
    buckets: int
    features: tuple[str, ...]
    hot_candles: tuple[Any, ...]


def _series() -> list[dict[str, Any]]:
    """One seeded walk covering the bootstrap window, its warm-up and the cut."""
    window = window_for(BOOTSTRAP_NOW, days=WINDOW_DAYS)
    first = window.start - timedelta(minutes=BUFFER_MINUTES)
    minutes = int((CUT - first).total_seconds() // 60)
    rows = synthetic_minutes(first, minutes)
    return shape_tail(
        rows,
        cut=CUT,
        hour_multiplier=HOUR_VOLUME_MULTIPLIER,
        spike_multiplier=SPIKE_VOLUME_MULTIPLIER,
        drift=HOUR_DRIFT,
    )


def _persisted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Everything strictly before the window's end — what the archive holds."""
    end = window_for(BOOTSTRAP_NOW, days=WINDOW_DAYS).end
    return [row for row in rows if row["open_time"] < end]


def _hot_candles(rows: list[dict[str, Any]]) -> list[Any]:
    """The 1500-minute ring the market-worker keeps, oldest first."""
    closed = [row for row in rows if row["open_time"] < CUT]
    return [to_candle(row, exchange=EXCHANGE, symbol=SYMBOL) for row in closed[-HOT_STATE_MINUTES:]]


async def _prepare(db_url: str, redis_url: str) -> Bootstrapped:
    """The expensive half, run once: candles, the bootstrap, OI history and the
    one ``LIVE`` revision a candle bootstrap cannot produce."""
    from pydantic import SecretStr

    from hunter_core.settings import Settings

    engine = create_engine(Settings(database_url=SecretStr(db_url), redis_url=SecretStr(redis_url)))
    redis = None
    try:
        factory = create_session_factory(engine)
        market_id = await seed_market(factory, EXCHANGE, SYMBOL)
        rows = _series()
        await _insert_candles(factory, market_id, _persisted(rows))
        await _insert_open_interest(factory, market_id)

        from hunter_core.redis import create_redis

        redis = create_redis(Settings(redis_url=SecretStr(redis_url)))
        settings = BootstrapSettings(
            window_days=WINDOW_DAYS, buffer_minutes=BUFFER_MINUTES, duty=1.0
        )
        ref = MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=SYMBOL)
        outcome = await run_bootstrap(
            factory,
            redis,
            BackfillRequester("m2-pipeline-test"),
            ref,
            window=window_for(BOOTSTRAP_NOW, days=WINDOW_DAYS),
            settings=settings,
            now=BOOTSTRAP_NOW,
        )
        await _write_tape_baseline(factory, market_id)
        return Bootstrapped(
            market_id=market_id,
            buckets=len(outcome.revisions),
            features=tuple(sorted({revision.key.feature for revision in outcome.revisions})),
            hot_candles=tuple(_hot_candles(rows)),
        )
    finally:
        if redis is not None:
            await redis.aclose()
        await engine.dispose()


async def _insert_candles(
    factory: async_sessionmaker[AsyncSession], market_id: UUID, rows: list[dict[str, Any]]
) -> None:
    payload = [
        {"market_id": market_id, "timeframe": Timeframe.M1, "is_final": True, **row} for row in rows
    ]
    async with role_session(factory, db_role="hunter_worker") as session:
        for chunk in range(0, len(payload), 2000):
            await session.execute(insert(Candle).values(payload[chunk : chunk + 2000]))


async def _insert_open_interest(factory: async_sessionmaker[AsyncSession], market_id: UUID) -> None:
    """The five-minute OI grid the market-worker samples, stepping up one hour
    before the cut so ``open_interest_change_1h`` is a number and not
    ``warmup``."""
    step_at = CUT - timedelta(hours=1)
    payload = [
        {
            "market_id": market_id,
            "ts": CUT - timedelta(minutes=5 * index),
            "open_interest": OI_AFTER
            if CUT - timedelta(minutes=5 * index) > step_at
            else OI_BEFORE,
            "open_interest_value": None,
        }
        for index in range(1, 110)
    ]
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(insert(OpenInterestHistory).values(payload))


async def _write_tape_baseline(factory: async_sessionmaker[AsyncSession], market_id: UUID) -> None:
    revision = live_revision(
        market_id=market_id,
        feature="trade_velocity_1m",
        hour_of_day=CUT.hour,
        median=Decimal("0.5"),
        mad=Decimal("0.1"),
        window_end=window_for(BOOTSTRAP_NOW, days=WINDOW_DAYS).end,
        available_at=BOOTSTRAP_NOW,
    )
    async with role_session(factory, db_role="hunter_worker") as session:
        await SqlBaselineStore(await session.connection()).append([revision])


@pytest.fixture(scope="module")
def bootstrapped(pipeline_db_url: str, pipeline_redis_url: str) -> Bootstrapped:
    """Runs once per module: 10 080 replay cuts are not a per-test cost.

    Synchronous on purpose, with its own engine inside ``asyncio.run`` — the
    pattern ``packages/core/tests/integration/test_schema_seed_and_partitions.py``
    already uses, so no async resource is ever shared across event loops.
    """
    return asyncio.run(_prepare(pipeline_db_url, pipeline_redis_url))


async def _scanner(
    session_factory: async_sessionmaker[AsyncSession], market_id: UUID, *, with_regime: bool
) -> Scanner:
    """The shipped Scanner, with the baselines read from the real Postgres.

    The policy comes from ``infra/scripts/seed_reference.py``'s
    ``OPPORTUNITY_WEIGHTS_V2`` through ``services/scanner-worker/tests/
    policies.py`` — the same vector ``load_policy`` reads in production. The
    migrations alone do not insert that row (seeding is a separate step, and
    this suite's database is migrated only), so ``load_policy`` would refuse
    here; hand-writing a weight dict instead would let the test pass against
    thresholds nobody published, which is the failure ``policies.py`` exists to
    prevent.
    """
    policy = build_policy()
    ref = MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=SYMBOL)
    scanner = Scanner(
        config=ScannerConfig(exchange=EXCHANGE),
        policy=policy,
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
        deriv=DerivHistory(),
    )
    scanner.registry.apply([ref])
    scanner.state.ensure(ref)
    cache = BaselineCache(gate=policy.gate)
    async with role_session(session_factory, db_role="hunter_worker") as session:
        await cache.refresh(await session.connection(), [ref], now=CUT)
    scanner.cache = cache
    await scanner.deriv.refresh(session_factory, [ref], now=CUT)
    if with_regime:
        scanner.regime = RegimeEngine(thresholds=policy.regime)
    return scanner


async def _advance(
    scanner: Scanner,
    redis: redis_asyncio.Redis,
    *,
    now: datetime,
    batch: WriteBatch | None = None,
) -> tuple[Evaluation, WriteBatch]:
    market = scanner.state.markets[SYMBOL]
    market.touch("tick", input_ts=now)
    scanner.coverage = await read_coverage(redis, EXCHANGE, now=now)
    target = batch if batch is not None else WriteBatch()
    evaluation = await scanner.advance(redis, market, target, now=now)
    assert evaluation is not None
    return evaluation, target


async def _load_hot_state(
    redis: redis_asyncio.Redis, bootstrapped: Bootstrapped, *, covered_until: datetime
) -> None:
    await write_hot_state(
        redis,
        exchange=EXCHANGE,
        symbol=SYMBOL,
        candles=[c for c in bootstrapped.hot_candles if c.close_time <= covered_until],
        trades=trade_rows(
            until=covered_until,
            seconds=TAPE_SECONDS,
            per_second=TRADES_PER_SECOND,
            buys_per_four=BUYS_PER_FOUR,
        ),
        as_of=covered_until,
    )
    await publish_coverage(
        redis,
        exchange=EXCHANGE,
        symbol=SYMBOL,
        session_since=CUT - timedelta(days=1),
        covered_until=covered_until,
    )


async def _two_passes(
    scanner: Scanner, redis: redis_asyncio.Redis, bootstrapped: Bootstrapped
) -> tuple[Evaluation, Evaluation, WriteBatch]:
    """The hysteresis: two distinct observations, one minute apart.

    A published stage changes only after two distinct ``observation_ts`` agree
    on the candidate and the side (``stage/classifier.py``), so a single cut can
    never show EARLY however perfect its evidence is.
    """
    await _load_hot_state(redis, bootstrapped, covered_until=FIRST_CUT)
    first, batch = await _advance(scanner, redis, now=FIRST_CUT)
    await _load_hot_state(redis, bootstrapped, covered_until=CUT)
    second, batch = await _advance(scanner, redis, now=CUT, batch=batch)
    return first, second, batch


# --------------------------------------------------------------------------
# 1. baselines
# --------------------------------------------------------------------------


async def test_seven_synthetic_days_bootstrap_the_buckets_the_live_cut_is_judged_against(
    bootstrapped: Bootstrapped, worker_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    assert bootstrapped.buckets > 0
    assert "relative_volume_5m" in bootstrapped.features
    assert "atr_14_pct" in bootstrapped.features
    # A candle bootstrap cannot reproduce the tape or the book, and says so
    # rather than inventing a number (docs/reports/M2.md, item 3).
    for absent in ("trade_velocity_1m", "buy_pressure_5m", "spread_pct"):
        assert absent not in bootstrapped.features

    policy = build_policy()
    cache = BaselineCache(gate=policy.gate)
    ref = MarketRef(market_id=bootstrapped.market_id, exchange=EXCHANGE, symbol=SYMBOL)
    async with role_session(worker_session_factory, db_role="hunter_worker") as session:
        loaded = await cache.refresh(await session.connection(), [ref], now=CUT)
    assert loaded > 0
    # The one baseline the *live* refresh owns, written through the same store.
    assert cache.median_of(bootstrapped.market_id, "trade_velocity_1m", CUT.hour) == Decimal("0.5")


# --------------------------------------------------------------------------
# 2. features + anomaly
# --------------------------------------------------------------------------


async def test_the_injected_spike_fires_volume_spike_at_saturated_severity(
    bootstrapped: Bootstrapped,
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: redis_asyncio.Redis,
) -> None:
    scanner = await _scanner(worker_session_factory, bootstrapped.market_id, with_regime=False)
    _first, second, _batch = await _two_passes(scanner, worker_redis, bootstrapped)

    relative_volume = second.vector.values["relative_volume_5m"]
    assert relative_volume.quality is Quality.OK
    assert relative_volume.value is not None
    # 5 spiked minutes over the median of the 23 previous disjoint 5-minute
    # windows, 12 of which are un-amplified: 40x/1x.
    assert relative_volume.value > Decimal(30)

    active = {state.type: state for state in second.anomaly_states}
    # Exactly two of the ten detectors fire, and both are closed numbers: the
    # injected spike (relative_volume_5m against its bootstrap bucket) and the
    # tape (trade_velocity_1m 2.0/s against the LIVE median 0.5 with MAD 0.1,
    # 15 MADs). Every other detector is either armed and silent or disarmed
    # with a reason -- asserting the *set* is what keeps a third one from
    # appearing unnoticed.
    assert sorted(state.type.value for state in second.anomaly_states) == [
        "TRADE_VELOCITY_SPIKE",
        "VOLUME_SPIKE",
    ]
    for anomaly_type in (AnomalyType.VOLUME_SPIKE, AnomalyType.TRADE_VELOCITY_SPIKE):
        state = active[anomaly_type]
        assert state.status is AnomalyStatus.ACTIVE
        assert state.severity == Decimal("100.00"), "saturated: the deviation is past 6 MADs"


# --------------------------------------------------------------------------
# 3. stage
# --------------------------------------------------------------------------


async def test_the_coverage_proof_releases_the_tape_and_the_stage_publishes_early(
    bootstrapped: Bootstrapped,
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: redis_asyncio.Redis,
) -> None:
    scanner = await _scanner(worker_session_factory, bootstrapped.market_id, with_regime=False)
    _first, second, _batch = await _two_passes(scanner, worker_redis, bootstrapped)

    for key in ("trade_velocity_1m", "buy_pressure_5m"):
        assert second.vector.values[key].quality is Quality.OK, key
    assert second.vector.values["trade_velocity_1m"].value == Decimal(TRADES_PER_SECOND)

    assert second.stage is not None
    decision = second.stage
    assert decision.state_out.stage is OpportunityStage.EARLY
    assert decision.state_out.direction == TradeDirection.LONG.value
    assert all(decision.confirmations.values()), decision.confirmations


async def test_without_the_coverage_proof_the_stage_refuses_to_publish_early(
    bootstrapped: Bootstrapped,
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: redis_asyncio.Redis,
) -> None:
    """The edge case that keeps production's stage column empty today: the tape
    features refuse themselves without ``covered_until``, and an absent
    confirmation removes a confirmation, not the requirement."""
    scanner = await _scanner(worker_session_factory, bootstrapped.market_id, with_regime=False)
    await write_hot_state(
        worker_redis,
        exchange=EXCHANGE,
        symbol=SYMBOL,
        candles=list(bootstrapped.hot_candles),
        trades=trade_rows(
            until=CUT,
            seconds=TAPE_SECONDS,
            per_second=TRADES_PER_SECOND,
            buys_per_four=BUYS_PER_FOUR,
        ),
        as_of=CUT,
    )
    # No coverage hash at all: the collector proved nothing.
    first, _ = await _advance(scanner, worker_redis, now=FIRST_CUT)
    second, _ = await _advance(scanner, worker_redis, now=CUT)

    assert first.vector.values["trade_velocity_1m"].quality is Quality.UNAVAILABLE
    assert second.stage is not None
    assert second.stage.state_out.stage is not OpportunityStage.EARLY


# --------------------------------------------------------------------------
# 4. regime
# --------------------------------------------------------------------------


async def test_seven_days_are_not_thirty_so_the_regime_is_unknown_with_its_reason(
    bootstrapped: Bootstrapped,
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: redis_asyncio.Redis,
) -> None:
    scanner = await _scanner(worker_session_factory, bootstrapped.market_id, with_regime=True)
    assert scanner.regime is not None
    scanner.regime.seed(list(bootstrapped.hot_candles), until=FIRST_CUT)
    await _two_passes(scanner, worker_redis, bootstrapped)
    await run_regime_once(scanner, worker_session_factory, worker_redis, now=CUT)

    decision = scanner.regime.last_decision
    assert decision is not None
    assert decision.state_out.regime is MarketRegime.UNKNOWN
    supporting = decision.supporting_features()
    assert supporting["volatility"] == "unknown"
    reference = supporting["reading"]["volatility_reference"]
    # This is the "seven days are not thirty" claim, proved rather than
    # asserted by adjective: the reference exists, refuses itself, and says
    # which of the two gates it failed.
    assert reference["usable"] is False
    assert reference["reason"] == "volatility_warmup"
    assert reference["window_days"] == 30
    assert reference["distinct_days"] < 30
    # And the trend half is unavailable for its own reason: this synthetic
    # universe has no ``BTCUSDT``, which is the reference market the engine
    # reads. Same pair of reasons production reports today
    # (docs/reports/M2.md, item 4) -- no regime is manufactured here.
    assert supporting["reading"]["reason"] == "trend_input_unavailable"

    async with role_session(worker_session_factory, db_role="hunter_worker") as session:
        stored = (await session.execute(select(MarketRegimeRow))).scalars().all()
    assert [row.regime for row in stored] == [MarketRegime.UNKNOWN]


# --------------------------------------------------------------------------
# 5. score + explanation
# --------------------------------------------------------------------------


async def test_the_score_components_and_the_explanation_state_the_same_numbers(
    bootstrapped: Bootstrapped,
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: redis_asyncio.Redis,
) -> None:
    scanner = await _scanner(worker_session_factory, bootstrapped.market_id, with_regime=False)
    _first, second, _batch = await _two_passes(scanner, worker_redis, bootstrapped)

    assert second.score is not None
    score = second.score
    available = {
        component.name: (
            str(component.weight),
            str(component.normalized),
            str(component.contribution),
            component.used,
            component.expected,
        )
        for component in score.components
        if component.available
    }
    unavailable = {c.name: c.reason for c in score.components if not c.available}

    # Closed numbers, every one of them derivable from the fixture: the volume
    # component sees 3 of its 4 inputs (``relative_volume_1h`` has no bootstrap
    # bucket at a 400-minute warm-up), order flow 1 of 3 (only the tape has a
    # baseline), momentum lands on the median of its own walk, and the two
    # saturated anomalies carry the 0.05 weight whole.
    assert available == {
        "agent_consensus": ("0.00", "0.0000", "0.0000", 0, 0),
        "anomalies": ("0.05", "100.0000", "5.0000", 2, 2),
        "momentum": ("0.20", "0.0000", "0.0000", 3, 3),
        "order_flow": ("0.15", "33.3333", "5.0000", 1, 3),
        "volume": ("0.20", "75.0000", "15.0000", 3, 4),
    }
    # Absence never redistributes weight, it reduces confidence -- and every
    # absence says which kind of absence it is.
    assert unavailable == {
        "derivatives": "no_usable_input",
        "external_intelligence": "feature_not_implemented",
        "liquidity": "no_usable_input",
        "market_regime": "regime_unknown",
    }
    assert score.confidence == Decimal("0.5000")

    early = score.early_movement
    assert (early.e, early.stage, early.stage_direction) == (1, "EARLY", "long")
    assert early.contribution == Decimal("10.0000")
    # ``score = clip(sum(w_i * c_i) + 10e)``: 5 + 0 + 5 + 15 + 0 + 10 = 35.00,
    # with Early-Movement outside the weight budget.
    assert sum(c.contribution for c in score.components) + early.contribution == Decimal("35.0000")
    assert score.score == Decimal("35.00")

    # The binding the panel rests on: every sentence carries the very numbers
    # the decomposition summed (``explanation.py``'s own contract). A sentence
    # built from anything else would let the text and the score disagree.
    sentences: list[dict[str, Any]] = second.explanation["frases"]
    by_code: dict[str, list[dict[str, Any]]] = {}
    for sentence in sentences:
        by_code.setdefault(sentence["codigo"], []).append(sentence)
    assert second.explanation["resumo"] == sentences[0]["texto"]

    head = by_code["score"][0]["valores"]
    assert head["score"] == score.score
    assert head["confianca"] == score.confidence
    assert head["direcao"] == score.direction.value

    bound = {
        sentence["valores"]["componente"]: sentence
        for code in ("componente", "componente_indisponivel")
        for sentence in by_code.get(code, [])
    }
    for component in score.components:
        if component.name not in bound:
            continue
        values = bound[component.name]["valores"]
        if component.available:
            assert values["normalizado"] == component.normalized, component.name
            assert values["contribuicao"] == component.contribution, component.name
            assert values["peso"] == component.weight, component.name
        else:
            assert values["motivo"] == component.reason, component.name

    assert by_code["regime_indisponivel"][0]["valores"]["motivo"] == "regime_unknown"
    assert sorted(by_code["anomalias"][0]["valores"]["tipos"]) == [
        "TRADE_VELOCITY_SPIKE",
        "VOLUME_SPIKE",
    ]
    # The stage sentence and the stage the classifier published are one fact.
    assert by_code["estagio"][0]["valores"]["estagio"] == score.early_movement.stage


# --------------------------------------------------------------------------
# 6. the row: opportunities, radar:scores, and the real API
# --------------------------------------------------------------------------


async def test_the_scored_episode_reaches_opportunities_radar_scores_and_the_api(
    bootstrapped: Bootstrapped,
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: redis_asyncio.Redis,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    scanner = await _scanner(worker_session_factory, bootstrapped.market_id, with_regime=False)
    _first, second, batch = await _two_passes(scanner, worker_redis, bootstrapped)
    assert batch.opportunities, "an anomaly-driven episode must open a row"

    await flush_batch(worker_session_factory, worker_redis, batch, now=CUT)
    ref = MarketRef(market_id=bootstrapped.market_id, exchange=EXCHANGE, symbol=SYMBOL)
    await publish_radar(worker_redis, ref, second)

    async with role_session(worker_session_factory, db_role="hunter_worker") as session:
        stored = (
            (
                await session.execute(
                    select(Opportunity).where(Opportunity.market_id == bootstrapped.market_id)
                )
            )
            .scalars()
            .all()
        )
        anomalies = (
            (
                await session.execute(
                    select(Anomaly).where(Anomaly.market_id == bootstrapped.market_id)
                )
            )
            .scalars()
            .all()
        )
    assert len(stored) == 1
    assert stored[0].status is OpportunityStatus.ANOMALY
    assert stored[0].score == Decimal("35.00")
    # The column docs/reports/M2.md reports as empty in 299 production samples,
    # populated here by the pipeline itself rather than by an INSERT.
    assert stored[0].stage is OpportunityStage.EARLY
    assert sorted(row.type.value for row in anomalies) == [
        "TRADE_VELOCITY_SPIKE",
        "VOLUME_SPIKE",
    ]

    member = keys.market_slug(EXCHANGE, SYMBOL)
    zscore = await worker_redis.zscore(keys.radar_scores(), member)
    assert zscore is not None
    assert Decimal(str(zscore)) == stored[0].score

    response = await pipeline_client.get(
        "/api/v1/radar", params={"q": SYMBOL}, headers=authed_actor
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["symbol"] for item in items] == [SYMBOL]
    assert Decimal(items[0]["score"]) == Decimal("35.00")
    assert items[0]["stage"] == OpportunityStage.EARLY.value
    assert items[0]["status"] == OpportunityStatus.ANOMALY.value
    assert items[0]["opportunity_id"] == str(stored[0].id)


# --------------------------------------------------------------------------
# 7. reproducibility
# --------------------------------------------------------------------------


async def test_two_independent_runs_of_the_same_cut_produce_byte_identical_envelopes(
    bootstrapped: Bootstrapped,
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: redis_asyncio.Redis,
) -> None:
    """Byte equality, not "the same numbers": the joint M2 decision promises the
    stored envelope can be recomputed, and key order is part of that promise."""
    first_run = await _scanner(worker_session_factory, bootstrapped.market_id, with_regime=False)
    _a, first, _ = await _two_passes(first_run, worker_redis, bootstrapped)
    second_run = await _scanner(worker_session_factory, bootstrapped.market_id, with_regime=False)
    _b, second, _ = await _two_passes(second_run, worker_redis, bootstrapped)

    assert envelope_bytes(first.envelope) == envelope_bytes(second.envelope)
    assert envelope_bytes(first.explanation) == envelope_bytes(second.explanation)
