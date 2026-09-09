"""Duas versões na mesma passada leem janelas diferentes — T3.54b, contra o banco.

O teste de `test_context_budget.py` prova a aritmética; este prova que ela chega
ao Postgres. Um mercado, um corte, duas versões: a de 5 m (``volume_anomaly_v1``,
1560 min pelo piso) e a irmã de 1 h (``mean_reversion_h1_v1``, 5880 min pelo
próprio contrato congelado). O ``start`` que cada uma manda para
``repo.load_candles`` é medido, e as velas que cada contexto recebe são contadas:
com 2 000 minutos persistidos, a primeira enxerga 1 560 e a segunda enxerga os
2 000 — o botão único acabou.

A terceira asserção é a que fecha o §4 do brief: ``provenance.context_minutes``
carrega o número, então um contexto curto aparece no envelope como motivo e não
como mistério (foi o que custou à T3.54 uma versão inteira).

O último teste do arquivo entra pela porta do worker em vez da do construtor de
contexto: ``decide.evaluate_slot``, a mesma função que o consumidor chama quando
uma vela fecha e a que o replay chama barra a barra. É lá que a fiação existe ou
não existe — as duas versões avaliadas na mesma passada pedem janelas diferentes
ao banco, e a de 1 h ainda responde ``atr_warmup`` porque o *mercado* é curto,
que é justamente a distinção que a T3.54 não conseguia fazer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.strategies.canonical import params_hash
from hunter_core.strategies.mean_reversion_h1_v1 import MEAN_REVERSION_H1_V1
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker.catalogue import ActiveVersion
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.context import build_market_context
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.repo import load_candles, load_market

from .builders import (
    EXCHANGE,
    MINUTE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    seed_market,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.market import NormalizedCandle
    from hunter_core.strategies.base import Strategy
    from hunter_strategy_worker.repo import MarketRow

pytestmark = pytest.mark.integration

CUT = datetime(2026, 9, 5, 14, 0, tzinfo=UTC)
PERSISTED = 2000
"""Mais do que o piso de 1560 e menos do que os 5880 da irmã: é a única faixa em
que as duas leituras se distinguem pelo que *recebem*, e não só pelo que pedem."""

CONFIG = ShadowConfig(hot_state_tail=5)


def version_of(
    strategy: Strategy, key: str, *, version_id: uuid.UUID | None = None
) -> ActiveVersion:
    """A versão viva desta estratégia, com os parâmetros congelados dela.

    ``version_id`` é a linha real de ``strategy_versions`` quando o teste chega a
    escrever no banco (o slot de episódio tem chave estrangeira para ela); os
    testes que só constroem contexto não precisam de linha nenhuma.
    """
    params = dict(strategy.default_parameters)
    return ActiveVersion(
        id=version_id or uuid.uuid4(),
        strategy_key=key,
        version="v1",
        params=params,
        params_hash=params_hash(params),
        strategy=strategy,
        code_ref=None,
        purpose="research_only",
    )


def rows(cut: datetime, minutes: int) -> list[dict[str, Any]]:
    return [
        {
            "open_time": cut - MINUTE * (minutes - index),
            "open": Decimal("100"),
            "high": Decimal("100.2"),
            "low": Decimal("99.8"),
            "close": Decimal("100"),
            "volume": Decimal("10"),
        }
        for index in range(minutes)
    ]


@pytest.fixture
async def market(db_session_factory: Any) -> MarketRow:
    """Um mercado com 2 000 minutos persistidos, do jeito que o banco de teste é
    de sessão: as velas são apagadas e reescritas, como em ``test_shadow_decisions``."""
    async with db_session_factory() as owner, owner.begin():
        # DDL como dono: ``hunter_worker`` não tem CREATE em public, por desenho.
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM candles"))
        _exchange_id, market_id = await seed_market(session)
        await insert_candles(session, market_id, rows(CUT, PERSISTED))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await load_market(session, EXCHANGE, SYMBOL)
    assert row is not None
    return row


async def test_two_versions_of_the_same_bar_read_different_windows(
    db_session_factory: Any, redis_client: Any, market: MarketRow
) -> None:
    """O item 2 do brief, contra o banco: mesma barra, mesmas configurações,
    janelas diferentes — e cada uma delas é a da versão."""
    asked: dict[str, datetime] = {}

    def reader(label: str) -> Any:
        async def read(
            session: AsyncSession, *, market: MarketRow, start: datetime, end: datetime
        ) -> list[NormalizedCandle]:
            asked[label] = start
            return await load_candles(session, market=market, start=start, end=end)

        return read

    five_minute = version_of(VOLUME_ANOMALY_V1, "volume_anomaly")
    hourly = version_of(MEAN_REVERSION_H1_V1, "mean_reversion_h1")
    contexts: dict[str, Any] = {}
    for label, version in (("5m", five_minute), ("1h", hourly)):
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            contexts[label] = await build_market_context(
                session,
                redis_client,
                market=market,
                source_bar_close=CUT,
                config=CONFIG,
                candles_reader=reader(label),
                context_minutes=version.context_minutes(CONFIG),
            )

    assert asked["5m"] == CUT - timedelta(minutes=1560)
    assert asked["1h"] == CUT - timedelta(minutes=5880)

    ctx_5m, prov_5m = contexts["5m"]
    ctx_1h, prov_1h = contexts["1h"]
    assert (prov_5m.context_minutes, prov_1h.context_minutes) == (1560, 5880)
    assert len(ctx_5m.candles_1m) == 1560
    assert len(ctx_1h.candles_1m) == PERSISTED
    assert prov_5m.bars_in_context == 1560
    assert prov_1h.bars_in_context == PERSISTED


async def test_the_wider_window_still_ends_at_the_cut(
    db_session_factory: Any, redis_client: Any, market: MarketRow
) -> None:
    """A janela maior cresce só para trás: a última vela das duas é a mesma, e
    nenhuma delas fecha depois do corte. É a garantia de não-antecipação do §2
    do PIPELINE dita sobre a mudança desta tarefa."""
    windows: dict[str, Any] = {}
    for label, version in (
        ("5m", version_of(VOLUME_ANOMALY_V1, "volume_anomaly")),
        ("1h", version_of(MEAN_REVERSION_H1_V1, "mean_reversion_h1")),
    ):
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            context, _provenance = await build_market_context(
                session,
                redis_client,
                market=market,
                source_bar_close=CUT,
                config=CONFIG,
                context_minutes=version.context_minutes(CONFIG),
            )
        windows[label] = context

    narrow, wide = windows["5m"].candles_1m, windows["1h"].candles_1m

    assert narrow[-1].open_time == wide[-1].open_time == CUT - MINUTE
    assert all(candle.close_time <= CUT for candle in wide)
    assert wide[-len(narrow) :] == narrow


async def test_without_a_version_the_window_is_the_old_shared_floor(
    db_session_factory: Any, redis_client: Any, market: MarketRow
) -> None:
    """Compatibilidade: quem não passa ``context_minutes`` lê exatamente o que
    lia antes da T3.54b — ``SHADOW_CONTEXT_MINUTES``, o piso."""
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        context, provenance = await build_market_context(
            session,
            redis_client,
            market=market,
            source_bar_close=CUT,
            config=CONFIG,
        )

    assert provenance.context_minutes == CONFIG.context_minutes == 1560
    assert len(context.candles_1m) == 1560


@pytest.fixture
async def activated(db_session_factory: Any) -> dict[str, ActiveVersion]:
    """As duas versões com linha real em ``strategy_versions``.

    ``evaluate_slot`` tranca um slot de episódio, e `shadow_episodes` tem chave
    estrangeira para a versão: um id inventado passaria pelo contexto e morreria
    no primeiro `INSERT`. As tabelas de sombra são limpas antes porque o banco de
    teste é de sessão e um slot deixado aberto por outro cenário decidiria o que
    este teste vê.
    """
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        _five_strategy, five_id = await activate_version(session, key="volume_anomaly")
        _hourly_strategy, hourly_id = await activate_version(session, key="mean_reversion_h1")
    return {
        "5m": version_of(VOLUME_ANOMALY_V1, "volume_anomaly", version_id=five_id),
        "1h": version_of(MEAN_REVERSION_H1_V1, "mean_reversion_h1", version_id=hourly_id),
    }


async def test_the_worker_gives_each_version_its_own_window_in_the_same_pass(
    db_session_factory: Any,
    redis_client: Any,
    market: MarketRow,
    activated: dict[str, ActiveVersion],
) -> None:
    """O item 5 do brief pela porta por onde o worker realmente passa.

    Os testes acima provam o construtor de contexto; este prova a **fiação**:
    ``decide.evaluate_slot`` — a mesma função que o consumidor chama quando uma
    vela fecha e a que o replay chama barra a barra — pede a janela da *versão*,
    não a do processo. Mesma passada, mesma barra, mesma ``ShadowConfig``, e as
    duas leituras de `load_candles` começam em instantes diferentes.

    O desfecho de cada uma é a segunda metade do argumento: a de 1 h recebe os
    5 880 min a que tem direito e ainda assim responde ``atr_warmup``, porque o
    mercado só tem 2 000 minutos persistidos. Antes da T3.54b as duas causas —
    janela curta e mercado curto — eram indistinguíveis sem ler o ambiente do
    deployment, e foi essa confusão que custou à T3.54 duas versões inteiras.
    """
    asked: dict[str, datetime] = {}

    def reader(label: str) -> Any:
        async def read(
            session: AsyncSession, *, market: MarketRow, start: datetime, end: datetime
        ) -> list[NormalizedCandle]:
            asked[label] = start
            return await load_candles(session, market=market, start=start, end=end)

        return read

    outcome: dict[str, tuple[str, str]] = {}
    for label, version in activated.items():
        evaluation = await evaluate_slot(
            db_session_factory,
            redis_client,
            version=version,
            market=market,
            bar_close=CUT,
            config=CONFIG,
            clock=lambda: CUT + timedelta(seconds=2),
            candles_reader=reader(label),
        )
        outcome[label] = (evaluation.state.value, evaluation.reason or "")

    assert asked["5m"] == CUT - timedelta(minutes=1560)
    assert asked["1h"] == CUT - timedelta(minutes=5880)
    # O botão único teria mandado as duas para o mesmo instante.
    assert asked["1h"] != CUT - timedelta(minutes=CONFIG.context_minutes)
    assert outcome["5m"] == ("not_triggered", "volume_below_threshold")
    assert outcome["1h"] == ("unavailable", "atr_warmup")
