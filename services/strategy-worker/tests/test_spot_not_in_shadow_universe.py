"""T3.73 — a linha `spot` de um símbolo não entra no universo de decisão do Lab.

`markets` tem até duas linhas por símbolo desde a T3.0b/T3.0c (`spot` e
`perpetual`), e o consumidor do Shadow Lab avaliava **a vela que chegasse**:
`handle_candle` resolvia `load_market(..., candle.market_type)` e seguia. Como o
`market-worker` publica `market.candles.closed` para os dois produtos (T3.0d,
PIPELINE §1d item 6), as versões passaram a decidir também sobre a linha spot —
com o modelo de custo do perpétuo. Medido na VPS em 2026-09-10: **340 sinais**
spot entre 08 e 09/09 e **133 desfechos terminais, todos com `r_multiple`
NULL** por `funding_schedule_unknown` — `funding_rates` não tem (nem pode ter)
uma linha para um mercado à vista, então `resolve_funding` nunca estabelece
cadência. E 179 trios (versão, símbolo, barra) foram decididos nas duas linhas,
o que duplica qualquer contagem de aposta única.

A decisão é a que os documentos já implicam (PIPELINE §1d itens 1 e 7: o spot
existe como **preço de execução da carteira**, e "todo o resto do pipeline …
continua raciocinando só sobre o perpétuo"; a ponte de execução mapeia o sinal
perpétuo para o par spot em `bridge_universe.spot_pair_for`, então a carteira
não precisa — e nunca precisou — de um sinal nascido na linha spot).

Run: ``uv run pytest services/strategy-worker/tests/test_spot_not_in_shadow_universe.py -q``
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, text

from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.agents_shadow import ShadowEpisode, ShadowOutbox
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import NormalizedCandle, to_wire
from hunter_core.observability import registry
from hunter_core.strategies.base import EvaluationState
from hunter_core.strategies.envelope import PURPOSE_RESEARCH_ONLY
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker import consumer as consumer_mod
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth, handle_candle
from hunter_strategy_worker.repo import load_market
from hunter_strategy_worker.roster import ActiveVersion
from hunter_strategy_worker.versions import VersionCache

from . import builders

BAR_CLOSE = datetime(2026, 9, 8, 12, 5, tzinfo=UTC)
"""Um fechamento de 5m — o timeframe do ``volume_anomaly_v1``."""


def _payload(
    *, market_type: MarketType, close_time: datetime = BAR_CLOSE, is_final: bool = True
) -> dict[str, Any]:
    return to_wire(
        NormalizedCandle(
            exchange=builders.EXCHANGE,
            symbol=builders.SYMBOL,
            market_type=market_type,
            timeframe=Timeframe.M1,
            open_time=close_time - timedelta(minutes=1),
            close_time=close_time,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            volume=Decimal("10"),
            is_final=is_final,
        )
    )


def _version(version: str = "v1") -> ActiveVersion:
    return ActiveVersion(
        id=uuid.uuid4(),
        strategy_key="volume_anomaly",
        version=version,
        params={"volume_mult": "4"},
        params_hash="0" * 64,
        strategy=VOLUME_ANOMALY_V1,
        code_ref=None,
        purpose=PURPOSE_RESEARCH_ONLY,
    )


class _Versions:
    def __init__(self, versions: list[ActiveVersion]) -> None:
        self._versions = versions

    async def get(self, _factory: Any) -> list[ActiveVersion]:
        return list(self._versions)


class _Evaluation:
    state = EvaluationState.NOT_TRIGGERED


def _skipped(market_type: str) -> float:
    value = registry.get_sample_value(
        "hunter_shadow_bars_skipped_total", {"reason": f"market_type:{market_type}"}
    )
    return 0.0 if value is None else value


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """``handle_candle`` sem banco: o que está sob teste é a porta, não o banco."""
    seen: dict[str, list[Any]] = {"markets": [], "evaluated": []}

    @asynccontextmanager
    async def _session(*_args: Any, **_kwargs: Any) -> AsyncGenerator[object]:
        yield object()

    async def _load_market(_session: Any, *args: Any, **_kwargs: Any) -> Any:
        seen["markets"].append(args)
        return object()

    async def _evaluate(*_args: Any, version: ActiveVersion, **_kwargs: Any) -> Any:
        seen["evaluated"].append(version.version)
        return _Evaluation()

    monkeypatch.setattr(consumer_mod, "role_session", _session)
    monkeypatch.setattr(consumer_mod, "load_market", _load_market)
    monkeypatch.setattr(consumer_mod, "evaluate_slot", _evaluate)

    def _due(versions: list[ActiveVersion], _bar: datetime) -> list[ActiveVersion]:
        return versions

    monkeypatch.setattr(consumer_mod, "versions_for_bar", _due)
    return seen


async def _run(payload: dict[str, Any], health: ConsumerHealth) -> None:
    await handle_candle(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        payload=payload,
        versions=_Versions([_version()]),  # type: ignore[arg-type]
        config=ShadowConfig(),
        health=health,
        # BAR_CLOSE is a fixed past date; without this the real clock (T3.74c's
        # bar-level backlog valve, ShadowConfig.late_delay_backlog_max_s) would
        # see every bar here as far too late and skip it before the door this
        # suite tests is even reached.
        clock=lambda: BAR_CLOSE + timedelta(seconds=2),
    )


@pytest.mark.unit
async def test_a_spot_bar_is_never_evaluated(wired: dict[str, list[Any]]) -> None:
    health = ConsumerHealth()
    await _run(_payload(market_type=MarketType.SPOT), health)
    assert wired["evaluated"] == []
    assert health.evaluated_bars == 0


@pytest.mark.unit
async def test_a_spot_bar_does_not_even_resolve_its_market_row(
    wired: dict[str, list[Any]],
) -> None:
    """A recusa é anterior ao banco: nem a linha de ``markets`` é lida.

    Importa para o custo — a mediana do atraso decisão-menos-barra estava em
    108 s na VPS em 09/09 — e para a intenção: o mercado não está no universo,
    não é "um mercado do universo cuja avaliação falhou"."""
    health = ConsumerHealth()
    await _run(_payload(market_type=MarketType.SPOT), health)
    assert wired["markets"] == []


@pytest.mark.unit
async def test_the_refusal_is_counted_never_silent(wired: dict[str, list[Any]]) -> None:
    before = _skipped("spot")
    await _run(_payload(market_type=MarketType.SPOT), ConsumerHealth())
    assert _skipped("spot") == before + 1


@pytest.mark.unit
async def test_the_perpetual_bar_of_the_same_symbol_still_decides(
    wired: dict[str, list[Any]],
) -> None:
    """O controle: a mesma vela, do outro produto, continua avaliada."""
    before = _skipped("perpetual")
    health = ConsumerHealth()
    await _run(_payload(market_type=MarketType.PERPETUAL), health)
    assert wired["evaluated"] == ["v1"]
    assert health.evaluated_bars == 1
    assert _skipped("perpetual") == before


@pytest.mark.unit
async def test_a_payload_without_market_type_is_the_perpetual(
    wired: dict[str, list[Any]],
) -> None:
    """Compatibilidade declarada na T3.0c item 3: um payload antigo, sem o
    discriminador, significa perpétuo — e continua decidindo."""
    payload = _payload(market_type=MarketType.PERPETUAL)
    payload.pop("market_type", None)
    await _run(payload, ConsumerHealth())
    assert wired["evaluated"] == ["v1"]


class _NoUniverseChange:
    """A sonda de elegibilidade lê ``market.universe.changed``; um stream vazio
    significa "o conjunto monitorado não mudou desde a barra"."""

    async def xrevrange(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    async def lrange(self, *_args: Any, **_kwargs: Any) -> list[bytes]:
        return []

    async def hgetall(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {}


async def _counts(factory: Any) -> dict[str, int]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return {
            "signals": await session.scalar(select(func.count()).select_from(AgentSignal)) or 0,
            "outcomes": await session.scalar(select(func.count()).select_from(SignalOutcome)) or 0,
            "episodes": await session.scalar(select(func.count()).select_from(ShadowEpisode)) or 0,
            "outbox": await session.scalar(select(func.count()).select_from(ShadowOutbox)) or 0,
        }


@pytest.mark.integration
async def test_a_spot_candle_writes_no_shadow_row(db_session_factory: Any) -> None:
    """Contra Postgres de verdade: a mesma série que faz a versão disparar,
    inserida na linha **spot**, não produz sinal, desfecho, episódio nem outbox;
    a mesma série na linha perpétua produz exatamente um de cada."""
    cut = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    async with db_session_factory() as owner, owner.begin():
        await builders.ensure_partitions(owner, cut)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        await session.execute(text("DELETE FROM candles"))
        exchange_id, perpetual_id = await builders.seed_market(session)
        spot_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type, status, "
                "is_monitored, monitor_rank, volume_24h_usd, last_seen_at) "
                "VALUES (:id, :exchange_id, :symbol, 'spot', 'active', true, 1, "
                "1000000, now()) ON CONFLICT (exchange_id, symbol, market_type) DO NOTHING"
            ),
            {"id": spot_id, "exchange_id": exchange_id, "symbol": builders.SYMBOL},
        )
        await builders.activate_version(session)
        await builders.isolate_catalogue(session)
        bars = builders.series(cut)
        await builders.insert_candles(session, perpetual_id, bars)
        await builders.insert_candles(session, spot_id, bars)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        spot = await load_market(session, builders.EXCHANGE, builders.SYMBOL, MarketType.SPOT)
        versions = await load_active_versions(session)
    assert spot is not None and spot.id == spot_id
    assert len(versions) == 1

    config = ShadowConfig(eligibility_max_lag_s=300, context_minutes=1560)
    cache = VersionCache(60.0)
    health = ConsumerHealth()

    async def _deliver(market_type: MarketType) -> None:
        await handle_candle(
            db_session_factory,
            _NoUniverseChange(),  # type: ignore[arg-type]
            payload=_payload(market_type=market_type, close_time=cut),
            versions=cache,
            config=config,
            health=health,
            clock=lambda: cut,
        )

    await _deliver(MarketType.SPOT)
    assert await _counts(db_session_factory) == {
        "signals": 0,
        "outcomes": 0,
        "episodes": 0,
        "outbox": 0,
    }

    await _deliver(MarketType.PERPETUAL)
    assert await _counts(db_session_factory) == {
        "signals": 1,
        "outcomes": 1,
        "episodes": 1,
        "outbox": 1,
    }
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        market_ids = list((await session.execute(select(AgentSignal.market_id))).scalars().all())
    assert market_ids == [perpetual_id]
