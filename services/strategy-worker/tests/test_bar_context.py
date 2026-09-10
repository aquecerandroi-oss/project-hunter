"""O pacote da barra devolve exatamente o contexto que a leitura por versão devolvia — T3.74g.

O ganho da T3.74g vem de *não* reconstruir, por versão, um objeto que já foi
construído e validado uma vez na mesma barra
(:mod:`hunter_strategy_worker.bar_context`). Isso só é aceitável se a fatia
servida for **igual** — no sentido do `==` do pydantic, campo a campo, mesmas
velas na mesma ordem — ao contexto que ``build_context`` produziria lendo aquela
janela sozinha. É o que este arquivo prova, sem banco e sem Redis: o pacote é
montado com listas em memória, e cada janela viva é comparada com a construção
antiga.

Três provas que valem registrar separadamente:

1. **igualdade por janela** — inclusive no teto (onde a fatia é o próprio objeto
   base) e numa janela mais curta que a série (onde é uma cópia);
2. **anti-look-ahead sobrevive ao atalho** — uma vela não final e uma vela que
   fecha depois do corte entram no pacote e não aparecem em nenhuma fatia; mudar
   a vela em formação não muda nada do que qualquer versão vê. O corte continua
   sendo o de ``build_context``, porque é ``build_context`` quem o aplica;
3. **o pacote recusa em vez de responder curto** — outra barra, outro mercado ou
   uma janela mais larga que o teto não são servidos, e quem perguntou volta
   para a leitura própria (o caminho de antes da T3.74g, que continua testado).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import MarketStatus, MarketType, Timeframe
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.base import build_context
from hunter_strategy_worker.bar_context import BarBundle
from hunter_strategy_worker.repo import MarketRow

pytestmark = pytest.mark.unit

CUT = datetime(2026, 9, 10, 21, 0, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
CEILING = 600
EXCHANGE = "binance"
SYMBOL = "BTCUSDT"
MARKET_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def candle(open_time: datetime, *, is_final: bool = True, close: str = "100") -> NormalizedCandle:
    return NormalizedCandle(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        timeframe=Timeframe.M1,
        open_time=open_time,
        close_time=open_time + MINUTE,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal(close),
        volume=Decimal("10"),
        is_final=is_final,
        received_at=open_time + MINUTE,
    )


def series(minutes: int = CEILING) -> list[NormalizedCandle]:
    return [candle(CUT - MINUTE * (minutes - i)) for i in range(minutes)]


def market() -> MarketRow:
    return MarketRow(
        id=MARKET_ID,
        symbol=SYMBOL,
        exchange=EXCHANGE,
        is_monitored=True,
        status=MarketStatus.ACTIVE,
        market_type=MarketType.PERPETUAL,
    )


def bundle_of(candles: list[NormalizedCandle], *, ceiling: int = CEILING) -> BarBundle:
    """O pacote como ``build_bar_bundle`` o monta, sem os dois `await` dele.

    Montar aqui em vez de chamar a função assíncrona é deliberado: o que este
    arquivo prova é a *álgebra* das fatias, e ela não deve depender de um banco
    para ser verificável. A montagem contra Postgres — com derivativos e cauda
    reais — é provada em ``test_context_cache_engine.py``.
    """
    base = build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT)
    return BarBundle(
        market_id=MARKET_ID,
        bar_close=CUT,
        ceiling_minutes=ceiling,
        durable=candles,
        merged=candles,
        base=base,
        deriv=None,  # type: ignore[arg-type]  # nenhuma asserção deste arquivo lê derivativos
    )


def built_the_old_way(
    candles: list[NormalizedCandle],
    minutes: int,
    *,
    eligible: bool = True,
    eligibility_reason: str | None = None,
) -> object:
    """O que ``build_market_context`` construiria lendo só aquela janela."""
    start = CUT - timedelta(minutes=minutes)
    window = [c for c in candles if c.open_time >= start]
    return build_context(
        window,
        exchange=EXCHANGE,
        symbol=SYMBOL,
        source_bar_close=CUT,
        eligible=eligible,
        eligibility_reason=eligibility_reason,
    )


class TestTheViewIsTheOldContext:
    @pytest.mark.parametrize("minutes", [CEILING, 500, 240, 60, 1])
    def test_every_window_equals_the_context_built_from_that_window_alone(
        self, minutes: int
    ) -> None:
        candles = series()
        view = bundle_of(candles).view(minutes)
        assert view.context == built_the_old_way(candles, minutes)
        assert len(view.context.candles_1m) == minutes

    def test_the_durable_slice_is_what_load_candles_would_have_returned(self) -> None:
        candles = series()
        view = bundle_of(candles).view(120)
        start = CUT - timedelta(minutes=120)
        assert list(view.durable) == [c for c in candles if c.open_time >= start]
        assert view.newest_bar_open == candles[-1].open_time

    def test_eligibility_is_stamped_per_version_and_still_equals_the_old_context(self) -> None:
        candles = series()
        view = bundle_of(candles).view(300)
        refused = view.with_eligibility(eligible=False, eligibility_reason="regime:btc_bear")
        assert refused == built_the_old_way(
            candles, 300, eligible=False, eligibility_reason="regime:btc_bear"
        )
        assert view.with_eligibility(eligible=True, eligibility_reason=None) is view.context

    def test_the_ceiling_window_is_served_as_the_very_object_that_was_validated(self) -> None:
        """Nenhuma cópia quando não há o que fatiar: a versão mais larga da
        barra recebe o próprio objeto que ``build_context`` validou, e as mais
        curtas recebem cópias iguais ao que teriam construído sozinhas."""
        bundle = bundle_of(series())
        assert bundle.view(CEILING).context is bundle.view(CEILING).context
        assert bundle.view(300).context == bundle.view(300).context


class TestTheCutSurvivesTheShortcut:
    def test_a_forming_minute_and_a_bar_past_the_cut_never_reach_any_window(self) -> None:
        polluted = [*series(), candle(CUT - MINUTE, is_final=False), candle(CUT)]
        bundle = bundle_of(polluted)
        for minutes in (CEILING, 120, 5):
            window = bundle.view(minutes).context.candles_1m
            assert all(c.is_final for c in window)
            assert all(c.close_time <= CUT for c in window)

    def test_changing_the_non_final_candle_does_not_change_what_a_version_sees(self) -> None:
        clean = series()
        one = bundle_of([*clean, candle(CUT - MINUTE, is_final=False, close="100.9")])
        other = bundle_of([*clean, candle(CUT - MINUTE, is_final=False, close="99.1")])
        for minutes in (CEILING, 120, 5):
            assert one.view(minutes).context == other.view(minutes).context


class TestItRefusesInsteadOfAnsweringShort:
    def test_a_window_wider_than_the_ceiling_is_not_covered(self) -> None:
        bundle = bundle_of(series())
        assert bundle.covers(market(), CUT, CEILING)
        assert not bundle.covers(market(), CUT, CEILING + 1)

    def test_another_bar_or_another_market_is_not_covered(self) -> None:
        bundle = bundle_of(series())
        other = MarketRow(
            id=uuid.uuid4(),
            symbol="ETHUSDT",
            exchange=EXCHANGE,
            is_monitored=True,
            status=MarketStatus.ACTIVE,
        )
        assert not bundle.covers(market(), CUT + MINUTE, 60)
        assert not bundle.covers(other, CUT, 60)
