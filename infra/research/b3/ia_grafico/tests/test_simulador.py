"""Simulação OHLC de 1 min com custo B3 e 1 tick por perna — valores calculados à mão.

Convenções: tick 5 pts; custo 1,28 pt por perna (R$ 0,256 ÷ R$ 0,20); entrada a mercado na
abertura da 1.ª barra que começa em t + 1 min; ref = 100 000 pts.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from infra.research.b3.ia_grafico.barras import Barra
from infra.research.b3.ia_grafico.resposta import Lado
from infra.research.b3.ia_grafico.simulador import Contexto, Ordem, Status, simular
from infra.research.b3.ia_grafico.tests.fabrica import barra, brt

D = date(2026, 3, 10)
REF = Decimal(100_000)
CTX = Contexto(t=brt(D, 10, 30), fim_sessao=brt(D, 17, 0), referencia=REF)


def _plano(inicio: datetime, n: int, preco: int = 100_000) -> list[Barra]:
    from infra.research.b3.ia_grafico.tests.fabrica import UM_MIN

    return [barra(inicio + i * UM_MIN, preco, preco, preco, preco) for i in range(n)]


def _troca(barras: list[Barra], i: int, novo: Barra) -> list[Barra]:
    return [*barras[:i], novo, *barras[i + 1 :]]


COMPRA = Ordem(lado=Lado.COMPRA, tipo="market", stop=Decimal(99_700), alvo=Decimal(100_500))


def test_alvo_com_travessia_de_um_tick() -> None:
    barras = _troca(
        _plano(brt(D, 10, 31), 70), 1, barra(brt(D, 10, 32), 100_050, 100_510, 100_000, 100_400)
    )
    r = simular(barras, COMPRA, CTX)
    assert (r.status, r.motivo) == (Status.OK, "alvo")
    assert (r.entrada, r.saida) == (Decimal(100_005), Decimal(100_495))
    assert r.net_pts == Decimal("487.44") and r.net_bp == pytest.approx(48.744)


def test_stop_e_alvo_na_mesma_barra_conta_stop() -> None:
    barras = _troca(
        _plano(brt(D, 10, 31), 70), 0, barra(brt(D, 10, 31), 100_000, 100_600, 99_600, 100_000)
    )
    r = simular(barras, COMPRA, CTX)
    assert (r.motivo, r.saida, r.net_pts) == ("stop", Decimal(99_695), Decimal("-312.56"))


def test_gap_alem_do_stop_sai_na_abertura() -> None:
    barras = _troca(
        _plano(brt(D, 10, 31), 70), 1, barra(brt(D, 10, 32), 99_500, 99_600, 99_400, 99_550)
    )
    r = simular(barras, COMPRA, CTX)
    assert (r.motivo, r.saida, r.net_pts) == ("stop", Decimal(99_495), Decimal("-512.56"))


def test_toque_no_alvo_sem_travessia_nao_basta_e_sai_por_tempo() -> None:
    barras = _troca(
        _plano(brt(D, 10, 31), 70), 1, barra(brt(D, 10, 32), 100_000, 100_500, 100_000, 100_000)
    )
    r = simular(barras, COMPRA, CTX)
    assert (r.motivo, r.fim) == ("tempo", brt(D, 11, 31))
    assert (r.saida, r.net_pts) == (Decimal(99_995), Decimal("-12.56"))


def test_venda_com_distancia_simetrica_do_arnes() -> None:
    ordem = Ordem(lado=Lado.VENDA, tipo="market", distancia=Decimal(300))
    barras = _troca(
        _plano(brt(D, 10, 31), 70), 1, barra(brt(D, 10, 32), 100_000, 100_000, 99_680, 99_700)
    )
    r = simular(barras, ordem, CTX)
    assert (r.entrada, r.stop, r.alvo) == (Decimal(99_995), Decimal(100_295), Decimal(99_695))
    assert (r.motivo, r.saida, r.net_pts) == ("alvo", Decimal(99_700), Decimal("292.44"))


LIMITE = Ordem(
    lado=Lado.COMPRA,
    tipo="limit",
    limite=Decimal(99_800),
    stop=Decimal(99_500),
    alvo=Decimal(100_300),
)


def test_limite_so_com_travessia_e_alvo_nao_vale_na_barra_do_fill() -> None:
    barras = _plano(brt(D, 10, 31), 70)
    barras = _troca(barras, 0, barra(brt(D, 10, 31), 100_000, 100_000, 99_800, 99_900))  # só toca
    barras = _troca(
        barras, 1, barra(brt(D, 10, 32), 99_900, 100_400, 99_790, 99_900)
    )  # fill; alvo ignorado
    barras = _troca(barras, 2, barra(brt(D, 10, 33), 99_900, 100_310, 99_900, 100_000))
    r = simular(barras, LIMITE, CTX)
    assert (r.inicio, r.entrada) == (brt(D, 10, 32), Decimal(99_805))
    assert (r.motivo, r.saida, r.net_pts) == ("alvo", Decimal(100_295), Decimal("487.44"))


def test_limite_stop_na_barra_do_fill_conta_stop() -> None:
    barras = _troca(
        _plano(brt(D, 10, 31), 70), 1, barra(brt(D, 10, 32), 99_900, 100_400, 99_450, 99_900)
    )
    r = simular(barras, LIMITE, CTX)
    assert (r.motivo, r.saida, r.net_pts) == ("stop", Decimal(99_495), Decimal("-312.56"))


def test_limite_sem_fill_em_30_min() -> None:
    r = simular(_plano(brt(D, 10, 31), 70), LIMITE, CTX)
    assert r.status is Status.SEM_FILL and r.net_pts is None


def test_sem_barra_na_tolerancia_de_entrada() -> None:
    r = simular(_plano(brt(D, 10, 37), 70), COMPRA, CTX)
    assert r.status is Status.SEM_PRECO_ENTRADA


def test_minuto_faltando_no_meio_da_posicao_censura_com_pior_caso() -> None:
    barras = [b for b in _plano(brt(D, 10, 31), 70) if b.inicio != brt(D, 10, 50)]
    r = simular(barras, COMPRA, CTX)
    assert r.status is Status.CENSURADO and r.net_pts is None
    assert r.pior_caso_pts == Decimal("-312.56")  # |100 005 − 99 700| + 5 + 2,56


def test_gap_na_entrada_alem_do_stop_sai_na_hora_sem_ganho() -> None:
    barras = _troca(
        _plano(brt(D, 10, 31), 70, 99_600), 0, barra(brt(D, 10, 31), 99_600, 99_600, 99_600, 99_600)
    )
    r = simular(barras, COMPRA, CTX)
    # Astra R2: a saída imediata paga o próprio tick (abertura − 5), além do tick da entrada
    assert (r.motivo, r.entrada, r.saida, r.net_pts) == (
        "gap_na_entrada",
        Decimal(99_605),
        Decimal(99_595),
        Decimal("-12.56"),
    )


def test_saida_por_tempo_limitada_pelo_fim_da_sessao() -> None:
    ctx = Contexto(t=brt(D, 16, 30), fim_sessao=brt(D, 17, 0), referencia=REF)
    r = simular(_plano(brt(D, 16, 31), 90), COMPRA, ctx)
    assert (r.motivo, r.fim) == ("tempo", brt(D, 17, 0))


def test_ordem_recusa_mistura_de_modos() -> None:
    with pytest.raises(ValueError, match="distancia"):
        Ordem(
            lado=Lado.COMPRA,
            tipo="market",
            distancia=Decimal(300),
            stop=Decimal(1),
            alvo=Decimal(2),
        )
    with pytest.raises(ValueError, match="limite"):
        Ordem(lado=Lado.COMPRA, tipo="limit", distancia=Decimal(300))


def test_limite_com_minutos_ausentes_ate_a_expiracao_e_censura_nao_sem_fill() -> None:
    """Sonda da Astra R2: janela 10:31–11:01 sem nenhuma barra até 11:01 pode ter preenchido."""
    r = simular(_plano(brt(D, 11, 1), 40), LIMITE, CTX)
    assert r.status is Status.CENSURADO


def test_limite_sem_fill_so_com_todos_os_minutos_da_janela_vistos() -> None:
    r = simular(_plano(brt(D, 10, 31), 40), LIMITE, CTX)
    assert r.status is Status.SEM_FILL
