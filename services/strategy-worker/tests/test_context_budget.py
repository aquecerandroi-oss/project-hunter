"""O contexto deixa de ser um número do processo e passa a ser da versão — T3.54b.

Três coisas são provadas aqui, e a segunda é a que importa:

1. **os números**, um por versão viva, escritos à mão a partir dos parâmetros
   congelados (``atr_bars`` × grade do ATR, ``trend_sma_bars + 1`` × grade da
   tendência mais o deslocamento do alinhamento, ``zscore_bars``/``rvol_window``
   × grade da decisão) — as sete de 15 m/5 m cabem no piso de 1560 que a faixa
   viva já usa, e a irmã de 1 h pede 5880;
2. **que a tabela declarada não é um chute**: um espião sobre ``aggregate`` roda
   a estratégia *de verdade* sobre uma série sintética e compara cada janela que
   o código pediu com a que a tabela declara. Uma variante que mexa num parâmetro
   de janela sem mexer na declaração morre aqui, em CI, e não em produção
   emudecida como as duas ``v9`` da T3.54;
3. **que ampliar a janela não move decisão nenhuma** — a prova de
   não-antecipação desta tarefa: o contexto só cresce para *trás* do corte, então
   dar 4× mais história à mesma barra tem de devolver byte a byte a mesma
   avaliação, e a vela em formação continua sem existir.

Sem Docker: tudo aqui é aritmética sobre parâmetros congelados e séries
construídas em memória.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from hunter_core.domain.enums import MarketStatus, ShadowCohort, Timeframe
from hunter_core.domain.market import NormalizedCandle, align_open_time, timeframe_seconds
from hunter_core.strategies.aggregate import aggregate as real_aggregate
from hunter_core.strategies.base import build_context
from hunter_core.strategies.canonical import canonical_json, params_hash
from hunter_core.strategies.registry import DEFAULT_REGISTRY
from hunter_strategy_worker.catalogue import ActiveVersion
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.context_budget import (
    WINDOWS,
    ContextBudgetUnknown,
    claim_reach_minutes,
    context_minutes_for,
    declared_windows,
    over_ceiling,
    required_context_minutes,
)
from hunter_strategy_worker.replay.plan import RunPlan
from hunter_strategy_worker.replay.simulate import ReplayWindow
from hunter_strategy_worker.repo import MarketRow

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_core.strategies.base import Strategy

pytestmark = pytest.mark.unit

EXCHANGE = "binance"
SYMBOL = "BTCUSDT"
MINUTE = timedelta(minutes=1)

CUT_M15 = datetime(2026, 9, 5, 14, 15, tzinfo=UTC)
"""14:15 UTC porque ``session_orb_v1`` só chega às janelas dele dentro de uma
sessão: abertura de 13:00 (US), 5 barras depois — acima de ``range_bars = 4`` e
dentro de ``session_window_bars = 20``. Também é o pior caso do alinhamento de
1 h para as versões de 15 m (45 min dentro da hora)."""

CUT_H1 = datetime(2026, 9, 5, 14, 0, tzinfo=UTC)

EXPECTED: dict[tuple[str, str], int] = {
    # 15m: max(97 barras de ATR × 15 = 1455) + 15 de folga
    ("breakout_v1", "v1"): 1470,
    ("mean_reversion_v1", "v1"): 1470,
    ("momentum_v1", "v1"): 1470,
    ("session_orb_v1", "v1"): 1470,
    ("sweep_reclaim_v1", "v1"): 1470,
    ("trendline_bounce_v1", "v1"): 1470,
    ("trendline_breakout_v1", "v1"): 1470,
    # 5m: o ATR é de 15m e o corte de 5m cai no meio da barra de 15m,
    # 97 × 15 + (15 − 5) = 1465, + 15 de folga
    ("volume_anomaly_v1", "v1"): 1480,
    # 1h: 97 barras de 1 h = 5820, + 60 de folga (notes-T3.54 §6.5)
    ("mean_reversion_h1_v1", "v1"): 5880,
}


def series(cut: datetime, minutes: int) -> list[NormalizedCandle]:
    """``minutes`` velas de 1 min terminando no corte, com preço que oscila.

    Dado de teste, e desenhado para não degenerar: um z-score sobre uma série
    constante tem desvio zero e ``mean_reversion`` responde ``zscore_degenerate``
    **antes** de pedir a janela de tendência — o espião não veria a terceira
    janela. A onda tem período 37 (primo com 5, 15 e 60) para que nenhuma grade
    veja sempre a mesma fatia dela.

    O preço é função do **minuto absoluto**, nunca do índice: uma série mais
    longa tem de ser a mesma série com mais passado à frente dela, ou o teste de
    "janela maior não move decisão" estaria comparando dois mercados diferentes
    (e foi exatamente o que ele acusou na primeira execução).
    """
    candles: list[NormalizedCandle] = []
    for index in range(minutes):
        open_time = cut - minutes * MINUTE + index * MINUTE
        phase = int(open_time.timestamp()) // 60
        base = Decimal(100) + Decimal(phase % 37)
        candles.append(
            NormalizedCandle(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                timeframe=Timeframe.M1,
                open_time=open_time,
                close_time=open_time + MINUTE,
                open=base,
                high=base + Decimal(2),
                low=base - Decimal(1),
                close=base + Decimal(1),
                volume=Decimal(10 + phase % 7),
                is_final=True,
            )
        )
    return candles


def cut_for(strategy: Strategy) -> datetime:
    return CUT_H1 if strategy.timeframe is Timeframe.H1 else CUT_M15


def defaults(strategy: Strategy) -> dict[str, Any]:
    return dict(strategy.default_parameters)


# --------------------------------------------------------------- 1. os números


def test_every_registered_strategy_declares_its_windows() -> None:
    """Uma estratégia nova sem declaração falha **aqui**, nunca em produção.

    É o fecho da regra de "falhar fechado": o catálogo recusa uma versão que este
    build não sabe dimensionar (``context_budget_unknown``) e a ativação também,
    então esquecer a declaração emudeceria a versão. Este teste faz o
    esquecimento custar um CI vermelho em vez de um experimento vazio.
    """
    registered = {(s.key, s.version) for s in DEFAULT_REGISTRY.all()}

    assert registered <= set(WINDOWS)
    assert registered == set(EXPECTED)


@pytest.mark.parametrize("strategy", DEFAULT_REGISTRY.all(), ids=lambda s: s.key)
def test_the_frozen_requirement_of_every_live_version(strategy: Strategy) -> None:
    assert (
        required_context_minutes(strategy, defaults(strategy))
        == EXPECTED[(strategy.key, strategy.version)]
    )


def test_the_fifteen_minute_versions_all_fit_the_floor_that_is_deployed() -> None:
    """A promessa de compatibilidade: nenhuma população viva se move.

    Todas as versões de 15 m/5 m pedem menos que os 1560 que o worker já
    carregava, então o ``min``/``max`` devolve exatamente 1560 para elas e a
    janela que a faixa viva lê hoje é a mesma de ontem. Eram sete até a T3.57;
    ``trendline_bounce_v1`` entra como a oitava e pede os mesmos 1470 da mãe.
    """
    config = ShadowConfig()
    fifteen = [s for s in DEFAULT_REGISTRY.all() if s.timeframe is not Timeframe.H1]

    assert len(fifteen) == 8
    for strategy in fifteen:
        assert required_context_minutes(strategy, defaults(strategy)) <= 1560
        assert context_minutes_for(strategy, defaults(strategy), config) == 1560


def test_the_h1_sibling_now_gets_what_it_needs() -> None:
    """O número que a T3.54 não pôde ligar: 5880 ≥ 5820 (notes-T3.54 §6.5)."""
    from hunter_core.strategies.mean_reversion_h1_v1 import MEAN_REVERSION_H1_V1

    params = defaults(MEAN_REVERSION_H1_V1)
    config = ShadowConfig()

    assert required_context_minutes(MEAN_REVERSION_H1_V1, params) == 5880
    assert required_context_minutes(MEAN_REVERSION_H1_V1, params) >= 5820
    assert context_minutes_for(MEAN_REVERSION_H1_V1, params, config) == 5880
    assert config.context_minutes == 1560
    assert config.context_max_minutes == 6000


def test_the_two_variants_t354_killed_would_run_today() -> None:
    """As ``v9`` aposentadas (``atr_timeframe = 1h``, ``atr_bars = 97``).

    5760 barras, 100 % ``atr_warmup``, porque 1560 < o alcance delas. O número
    inclui os 45 min do alinhamento de 1 h sob um corte de 15 m, que é o pior
    caso e é o que tem de ser carregado.
    """
    from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1

    v9 = {**defaults(MEAN_REVERSION_V1), "atr_timeframe": "1h"}

    assert required_context_minutes(MEAN_REVERSION_V1, v9) == 97 * 60 + 45 + 60 == 5925
    assert context_minutes_for(MEAN_REVERSION_V1, v9, ShadowConfig()) == 5925


def test_the_v10_that_did_run_keeps_reading_exactly_what_it_read() -> None:
    """``atr_bars = 24`` em 1 h pede 1545 < 1560: a coorte da T3.54 não se move."""
    from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1

    v10 = {**defaults(MEAN_REVERSION_V1), "atr_timeframe": "1h", "atr_bars": 24}

    assert required_context_minutes(MEAN_REVERSION_V1, v10) == 24 * 60 + 45 + 60 == 1545
    assert context_minutes_for(MEAN_REVERSION_V1, v10, ShadowConfig()) == 1560


def test_parameters_as_the_database_stores_them() -> None:
    """A linha congelada guarda ``params_format = 1``: números como strings.

    O worker lê ``default_parameters`` do JSONB, não do código, então a função
    tem de dar a mesma resposta para ``"97"`` e para ``97``.
    """
    from hunter_core.strategies.momentum_v1 import MOMENTUM_V1

    stored = {name: str(value) for name, value in MOMENTUM_V1.default_parameters.items()}

    assert required_context_minutes(MOMENTUM_V1, stored) == 1470


# --------------------------------------------------------------- 2. teto e recusas


def test_a_version_over_the_ceiling_is_refused_with_both_numbers() -> None:
    from hunter_core.strategies.mean_reversion_h1_v1 import MEAN_REVERSION_H1_V1

    message = over_ceiling(MEAN_REVERSION_H1_V1, defaults(MEAN_REVERSION_H1_V1), ceiling=2000)

    assert message is not None
    assert "5880" in message
    assert "2000" in message
    assert "'atr'" in message
    assert over_ceiling(MEAN_REVERSION_H1_V1, defaults(MEAN_REVERSION_H1_V1), ceiling=6000) is None


def test_the_ceiling_clamps_instead_of_muting() -> None:
    """Um teto abaixado *depois* da ativação encurta a janela e é registrado —
    nunca emudece a versão em silêncio (o motivo vai no envelope)."""
    from hunter_core.strategies.mean_reversion_h1_v1 import MEAN_REVERSION_H1_V1

    tight = ShadowConfig(context_max_minutes=3000)

    assert context_minutes_for(MEAN_REVERSION_H1_V1, defaults(MEAN_REVERSION_H1_V1), tight) == 3000


def test_an_undeclared_strategy_is_a_refusal_and_not_a_guess() -> None:
    class Impostor:
        key = "not_registered_v1"
        version = "v1"
        timeframe = Timeframe.M15
        default_parameters: dict[str, Any] = {}

    with pytest.raises(ContextBudgetUnknown, match="no declared context window"):
        required_context_minutes(Impostor(), {})  # type: ignore[arg-type]


def test_a_missing_parameter_is_a_refusal_and_not_a_zero() -> None:
    from hunter_core.strategies.momentum_v1 import MOMENTUM_V1

    without_atr = {k: v for k, v in defaults(MOMENTUM_V1).items() if k != "atr_bars"}

    with pytest.raises(ContextBudgetUnknown, match="atr_bars"):
        required_context_minutes(MOMENTUM_V1, without_atr)


# --------------------------------------------------------------- 3. o espião


@pytest.mark.parametrize("strategy", DEFAULT_REGISTRY.all(), ids=lambda s: s.key)
def test_the_declaration_covers_every_window_the_code_asks_for(
    strategy: Strategy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prova de que a tabela é transcrição e não chute.

    O espião embrulha o ``aggregate`` **no módulo da estratégia** (é lá que o
    nome está ligado) e mede o alcance real de cada chamada:
    ``corte − (fim − barras × grade)``. Cada chamada tem de caber em alguma
    janela declarada, e o total tem de caber no orçamento — que é exatamente a
    pergunta "esta versão decide ou nasce muda?".
    """
    params = defaults(strategy)
    budget = required_context_minutes(strategy, params)
    cut = cut_for(strategy)
    module = sys.modules[type(strategy).__module__]
    observed: list[int] = []

    def spy(
        candles: Sequence[NormalizedCandle],
        timeframe: Timeframe,
        source_bar_close: datetime,
        bars_needed: int,
    ) -> Any:
        span = timedelta(seconds=timeframe_seconds(timeframe) * bars_needed)
        observed.append(int((cut - (source_bar_close - span)).total_seconds() // 60))
        return real_aggregate(candles, timeframe, source_bar_close, bars_needed)

    monkeypatch.setattr(module, "aggregate", spy)
    context = build_context(
        series(cut, budget), exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=cut
    )
    evaluation = strategy.explain(context, params)

    assert evaluation.state.value != "unavailable", (evaluation.reason, evaluation.detail)
    assert len(observed) == len(declared_windows(strategy))
    declared = sorted(
        claim_reach_minutes(claim, strategy, params) for claim in declared_windows(strategy)
    )
    # Par a par, do menor para o maior: cada janela que o código pediu cabe na
    # janela declarada correspondente. "≤" e não "==" porque a declaração carrega
    # o **pior** alinhamento (uma barra de 1 h sob um corte de 15 m pode começar
    # 45 min antes) e este corte não é obrigado a realizá-lo — o teste seguinte
    # mostra um que realiza.
    for reach, budgeted in zip(sorted(observed), declared, strict=True):
        assert reach <= budgeted, (strategy.key, sorted(observed), declared)
    assert max(observed) <= budget
    assert max(observed) > 0


def test_the_alignment_offset_is_paid_by_a_cut_that_realises_it() -> None:
    """O termo de alinhamento não é decorativo: 14:10 é fechamento de 5 m e cai
    **dentro** da barra de 15 m, então o ATR de ``volume_anomaly_v1`` recua os
    1465 min declarados — dez a mais do que as 97 barras sozinhas."""
    from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1

    params = defaults(VOLUME_ANOMALY_V1)
    cut = datetime(2026, 9, 5, 14, 10, tzinfo=UTC)
    atr_end = align_open_time(cut, Timeframe.M15)
    reach = int(
        (cut - (atr_end - timedelta(minutes=15 * int(params["atr_bars"])))).total_seconds() // 60
    )

    atr = next(c for c in declared_windows(VOLUME_ANOMALY_V1) if c.name == "atr")

    assert reach == 1465 == claim_reach_minutes(atr, VOLUME_ANOMALY_V1, params)


# --------------------------------------------------------------- 4. não-antecipação


def test_a_wider_window_never_moves_a_decision() -> None:
    """A propriedade que torna esta mudança segura.

    A janela por versão só cresce para **trás** do corte, então dar 4× mais
    história à mesma barra não pode mudar nada: o mesmo estado, o mesmo motivo e
    o mesmo envelope canônico. Se crescesse para a frente, este teste falharia —
    é o oposto exato do vazamento.
    """
    from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1

    params = defaults(MEAN_REVERSION_V1)
    budget = required_context_minutes(MEAN_REVERSION_V1, params)

    def decide(minutes: int) -> tuple[str, str, bytes | None]:
        context = build_context(
            series(CUT_M15, minutes),
            exchange=EXCHANGE,
            symbol=SYMBOL,
            source_bar_close=CUT_M15,
        )
        evaluation = MEAN_REVERSION_V1.explain(context, params)
        envelope = (
            None
            if evaluation.decision is None
            else canonical_json(evaluation.decision.supporting_features.to_jsonable())
        )
        return evaluation.state.value, evaluation.reason, envelope

    tight = decide(budget)

    assert tight == decide(budget * 4)
    assert tight[0] != "unavailable"


def test_the_minute_still_forming_never_enters_the_window() -> None:
    """A vela em formação dentro da janela não muda a decisão (S1, reafirmado
    aqui porque a janela mudou de dono)."""
    from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1

    params = defaults(MEAN_REVERSION_V1)
    clean = series(CUT_M15, required_context_minutes(MEAN_REVERSION_V1, params))
    forming = clean[-1].model_copy(
        update={
            "open_time": CUT_M15,
            "close_time": CUT_M15 + MINUTE,
            "high": Decimal(10_000),
            "close": Decimal(9_999),
            "is_final": False,
        }
    )

    def decide(candles: list[NormalizedCandle]) -> tuple[str, str]:
        context = build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT_M15)
        evaluation = MEAN_REVERSION_V1.explain(context, params)
        return evaluation.state.value, evaluation.reason

    assert decide([*clean, forming]) == decide(clean)


# --------------------------------------------------------------- 5. o plano da coorte


def version_of(strategy: Strategy) -> ActiveVersion:
    """Uma :class:`ActiveVersion` de teste com os parâmetros congelados reais."""
    params = defaults(strategy)
    return ActiveVersion(
        id=uuid.uuid4(),
        strategy_key=strategy.key.removesuffix("_v1"),
        version="v1",
        params=params,
        params_hash=params_hash(params),
        strategy=strategy,
        code_ref=None,
        purpose="research_only",
    )


def plan_for(strategy: Strategy) -> RunPlan:
    return RunPlan(
        version=version_of(strategy),
        markets=(
            MarketRow(
                id=uuid.uuid4(),
                symbol=SYMBOL,
                exchange=EXCHANGE,
                is_monitored=True,
                status=MarketStatus.ACTIVE,
            ),
        ),
        window=ReplayWindow(datetime(2026, 8, 8, tzinfo=UTC), datetime(2026, 8, 9, tzinfo=UTC)),
        cohort=ShadowCohort.replay(uuid.uuid4()),
        lag_s=2,
    )


def test_the_cohort_plan_carries_the_window_of_its_own_version() -> None:
    """ "O mesmo experimento" passa a ser por versão (``replay/plan.py``)."""
    from hunter_core.strategies.mean_reversion_h1_v1 import MEAN_REVERSION_H1_V1
    from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1

    mother = plan_for(MEAN_REVERSION_V1)
    sister = plan_for(MEAN_REVERSION_H1_V1)

    assert mother.context_minutes == 1560
    assert sister.context_minutes == 5880
    assert mother.context_minutes != sister.context_minutes


def test_two_versions_of_the_same_pass_get_different_windows() -> None:
    """O item 2 do brief, na unidade em que ele é aritmética.

    A mesma :class:`ShadowConfig` — o mesmo processo, a mesma passada — devolve
    janelas diferentes para versões diferentes. É o fim do botão único.
    """
    from hunter_core.strategies.mean_reversion_h1_v1 import MEAN_REVERSION_H1_V1
    from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1

    config = ShadowConfig()
    windows = {
        version.strategy_key: version.context_minutes(config)
        for version in (version_of(VOLUME_ANOMALY_V1), version_of(MEAN_REVERSION_H1_V1))
    }

    assert windows == {"volume_anomaly": 1560, "mean_reversion_h1": 5880}


def test_the_alignment_offset_is_the_worst_case_and_not_an_average() -> None:
    """Por que a janela de tendência custa 45 min a mais do que as barras dizem.

    Um fechamento de 15 m às 14:45 alinha a hora em 14:00, então a janela de
    ``trend_sma_bars + 1`` horas começa 45 min antes do que começaria num corte
    de hora cheia — e o orçamento é por versão, não por barra: tem de caber o
    pior corte, não o médio.
    """
    from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1

    params = defaults(MEAN_REVERSION_V1)
    trend = next(c for c in declared_windows(MEAN_REVERSION_V1) if c.name == "trend")
    worst = datetime(2026, 9, 5, 14, 45, tzinfo=UTC)

    reach = claim_reach_minutes(trend, MEAN_REVERSION_V1, params)
    start = align_open_time(worst, Timeframe.H1) - timedelta(
        hours=int(params["trend_sma_bars"]) + 1
    )

    assert reach == 1305
    assert int((worst - start).total_seconds() // 60) == reach
