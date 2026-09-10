"""Quanto custa uma avaliação, antes e depois do pacote da barra — T3.74g.

**O que a VPS mediu (notes-T3.74f/T3.74g).** Com `STRATEGY_SHARDS=4` a barra
de 15 min ainda levava 37-43 s por shard, com **um** processo Python preso em
97-100 % de um núcleo e o Postgres em 20-25 % dos doze dele. Dividir por mais
processos não resolve o que é caro por avaliação: ~50 mercados x ~10 versões
vivas ≈ 500 avaliações por barra, ≈ 80 ms de CPU cada.

**O que este arquivo mede, e por que sem banco.** A fatia de CPU pura da
avaliação — montar o contexto e rodar `explain` — sobre a forma real do roster
(8 variantes de `mean_reversion_v1`, a irmã de 1 h e `momentum_v1`) e do shard
(50 mercados). É o trecho onde o perfil da T3.74g achou 59 % do custo total:
o pydantic revalidando cada `NormalizedCandle` a cada construção de
`StrategyContext`, uma vez por versão, sobre a mesma janela. O banco entra na
prova de equivalência com Postgres real (`test_context_cache_engine.py`); aqui
ele só adicionaria ruído a um número que é de CPU.

**O que é asserção e o que é observação.** Asserção: as 500 avaliações do
caminho novo são idênticas às do antigo (estado, motivo, detalhe e decisão), e
o caminho novo não é mais lento. Os milissegundos por avaliação são *registrados*
no log estruturado e copiados para `.claude/state/notes-T3.74g.md` à mão —
tempo de máquina de dev não é contrato, e uma asserção de magnitude aqui viraria
um teste intermitente na primeira máquina mais lenta.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import NormalizedCandle
from hunter_core.logging import get_logger
from hunter_core.strategies.base import build_context
from hunter_core.strategies.mean_reversion_h1_v1 import MEAN_REVERSION_H1_V1
from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1
from hunter_strategy_worker.bar_context import BarBundle
from hunter_strategy_worker.context_budget import required_context_minutes

pytestmark = pytest.mark.unit

logger = get_logger(__name__)

CUT = datetime(2026, 9, 10, 21, 0, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
MARKETS = 50
"""Um shard com `STRATEGY_SHARDS=4` sobre ~200 perpétuos."""
SERIES_MINUTES = 6000
"""O teto de `SHADOW_CONTEXT_MAX_MINUTES` — a janela mais longa que uma versão
viva pede hoje (a irmã de 1 h, 97 barras de ATR = 5820 min)."""
FLOOR = 1560
CEILING = 6000

VARIANTS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("v1", {}),
    ("v2", {"zscore_bars": 30}),
    ("v3", {"zscore_depth_min": Decimal("1.5")}),
    ("v6", {"trend_sma_bars": 50}),
    ("v7", {"atr_bars": 120}),
    ("v8", {"zscore_bars": 40, "atr_bars": 120}),
    ("v10", {"trend_sma_bars": 50, "zscore_depth_min": Decimal("2")}),
    ("v14", {"atr_period": 20}),
)
"""Oito variantes de **uma** família, como o roster vivo (v1, v2, v3, v6, v7,
v8, v10, v14): mesmo código, parâmetros congelados diferentes. Os valores aqui
são plausíveis, não os da VPS — o que o benchmark precisa reproduzir é a
*forma* (várias janelas distintas na mesma família), e nenhum número deste
arquivo chega perto de uma versão viva."""


def _candles(symbol: str, seed: int) -> list[NormalizedCandle]:
    rows: list[NormalizedCandle] = []
    price = Decimal("100")
    for index in range(SERIES_MINUTES):
        open_time = CUT - MINUTE * (SERIES_MINUTES - index)
        close = price + Decimal(((index * 7 + seed) % 23) - 11) / Decimal(100)
        rows.append(
            NormalizedCandle(
                exchange="binance",
                symbol=symbol,
                timeframe=Timeframe.M1,
                open_time=open_time,
                close_time=open_time + MINUTE,
                open=price,
                high=max(price, close) + Decimal("0.15"),
                low=min(price, close) - Decimal("0.15"),
                close=close,
                volume=Decimal("10") + Decimal(index % 9),
                is_final=True,
                received_at=open_time + MINUTE,
            )
        )
        price = close
    return rows


def _roster() -> list[tuple[str, Any, dict[str, Any], int]]:
    """``(rótulo, estratégia, parâmetros, context_minutes)`` das dez versões."""
    out: list[tuple[str, Any, dict[str, Any], int]] = []
    for label, override in VARIANTS:
        params = dict(MEAN_REVERSION_V1.default_parameters) | override
        out.append((f"mean_reversion_v1:{label}", MEAN_REVERSION_V1, params, 0))
    out.append(
        (
            "mean_reversion_h1_v1:v1",
            MEAN_REVERSION_H1_V1,
            dict(MEAN_REVERSION_H1_V1.default_parameters),
            0,
        )
    )
    out.append(("momentum_v1:v3", MOMENTUM_V1, dict(MOMENTUM_V1.default_parameters), 0))
    return [
        (
            label,
            strategy,
            params,
            min(max(required_context_minutes(strategy, params), FLOOR), CEILING),
        )
        for label, strategy, params, _ in out
    ]


def _before(markets: list[list[NormalizedCandle]], roster: list[Any]) -> list[Any]:
    """Uma leitura, uma montagem e uma validação de contexto por versão."""
    out: list[Any] = []
    for candles in markets:
        for _label, strategy, params, minutes in roster:
            start = CUT - timedelta(minutes=minutes)
            window = [c for c in candles if c.open_time >= start]
            context = build_context(
                window, exchange="binance", symbol=candles[0].symbol, source_bar_close=CUT
            )
            out.append(strategy.explain(context, params))
    return out


def _after(markets: list[list[NormalizedCandle]], roster: list[Any]) -> list[Any]:
    """Uma montagem por (mercado, barra); cada versão recebe a sua fatia."""
    ceiling = max(minutes for _l, _s, _p, minutes in roster)
    out: list[Any] = []
    for candles in markets:
        start = CUT - timedelta(minutes=ceiling)
        window = [c for c in candles if c.open_time >= start]
        base = build_context(
            window, exchange="binance", symbol=candles[0].symbol, source_bar_close=CUT
        )
        bundle = BarBundle(
            market_id=None,  # type: ignore[arg-type]  # ``covers`` não é exercido aqui
            bar_close=CUT,
            ceiling_minutes=ceiling,
            durable=window,
            merged=window,
            base=base,
            deriv=None,  # type: ignore[arg-type]
        )
        for _label, strategy, params, minutes in roster:
            out.append(strategy.explain(bundle.view(minutes).context, params))
    return out


class TestTheCostOfOneEvaluation:
    def test_the_bundle_decides_the_same_and_costs_less(self) -> None:
        roster = _roster()
        assert len(roster) == 10
        markets = [_candles(f"BENCH{i}USDT", i) for i in range(MARKETS)]
        evaluations = MARKETS * len(roster)

        started = time.perf_counter()
        before = _before(markets, roster)
        before_s = time.perf_counter() - started

        started = time.perf_counter()
        after = _after(markets, roster)
        after_s = time.perf_counter() - started

        for old, new in zip(before, after, strict=True):
            assert new.state == old.state
            assert new.reason == old.reason
            assert new.detail == old.detail
            assert new.decision == old.decision
        assert after_s < before_s

        logger.info(
            "t374g_evaluation_cost_benchmark",
            markets=MARKETS,
            versions=len(roster),
            evaluations=evaluations,
            before_boundary_s=round(before_s, 2),
            after_boundary_s=round(after_s, 2),
            before_ms_per_evaluation=round(before_s / evaluations * 1000, 2),
            after_ms_per_evaluation=round(after_s / evaluations * 1000, 2),
            speedup=round(before_s / after_s, 2),
        )
