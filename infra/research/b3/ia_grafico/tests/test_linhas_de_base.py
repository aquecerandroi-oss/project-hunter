"""Geometria do braço direcional, regra de média móvel e conversão da resposta em ordem."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from infra.research.b3.ia_grafico.barras import Barra
from infra.research.b3.ia_grafico.linhas_de_base import (
    atr,
    distancia_direcional,
    lado_media_movel,
    ordem_da_resposta,
)
from infra.research.b3.ia_grafico.resposta import Lado, validar
from infra.research.b3.ia_grafico.tests.fabrica import brt

D = date(2026, 3, 10)
CINCO = timedelta(minutes=5)


def _b(i: int, h: int, lo: int, c: int) -> Barra:
    return Barra(
        inicio=brt(D, 10, 0) + i * CINCO,
        duracao=CINCO,
        abertura=Decimal(c),
        maxima=Decimal(h),
        minima=Decimal(lo),
        fechamento=Decimal(c),
        volume=Decimal(1),
    )


def test_atr_e_distancia_com_valores_a_mao() -> None:
    barras = [_b(0, 100, 100, 100), _b(1, 110, 95, 105), _b(2, 108, 104, 106)]
    # TR1 = max(15, |110−100|, |95−100|) = 15; TR2 = max(4, |108−105|, |104−105|) = 4
    assert atr(barras, n=2) == Decimal("9.5")
    assert distancia_direcional(barras, n=2) == Decimal(20)  # 2 × 9,5 = 19 → teto ao tick (20)
    with pytest.raises(ValueError, match="barras"):
        atr(barras, n=3)


def test_media_movel_de_20_fechamentos() -> None:
    subindo = [_b(i, 1000 + i, 1000 + i, 1000 + i) for i in range(20)]
    assert lado_media_movel(subindo) is Lado.COMPRA
    descendo = [_b(i, 1000 - i, 1000 - i, 1000 - i) for i in range(20)]
    assert lado_media_movel(descendo) is Lado.VENDA
    plano = [_b(i, 1000, 1000, 1000) for i in range(20)]
    assert lado_media_movel(plano) is Lado.NENHUM


def _resposta(**kw: object) -> str:
    base: dict[str, object] = {
        "side": "buy",
        "entry_type": "market",
        "entry_y": None,
        "stop_y": -0.30,
        "target_y": 0.45,
        "confidence": 0.5,
        "levels": [],
        "rationale": "",
    }
    base.update(kw)
    return json.dumps(base)


def test_ordem_da_resposta_arredonda_para_o_lado_conservador() -> None:
    ref = Decimal(100_000)
    o = ordem_da_resposta(validar(_resposta()), ref)
    # 100 000·e^(−0,003) = 99 700,45 → piso 99 700; 100 000·e^(0,0045) = 100 451,01 → teto 100 455
    assert (o.lado, o.tipo, o.stop, o.alvo, o.limite) == (
        Lado.COMPRA,
        "market",
        Decimal(99_700),
        Decimal(100_455),
        None,
    )
    v = ordem_da_resposta(
        validar(
            _resposta(side="sell", entry_type="limit", entry_y=0.20, stop_y=0.50, target_y=-0.10)
        ),
        ref,
    )
    # limite 100 200,2 → teto 100 205; stop 100 501,25 → teto 100 505; alvo 99 900,05 → piso 99 900
    assert (v.limite, v.stop, v.alvo) == (Decimal(100_205), Decimal(100_505), Decimal(99_900))


def test_none_nao_vira_ordem() -> None:
    r = validar(_resposta(side="none", entry_type=None, stop_y=None, target_y=None))
    with pytest.raises(ValueError, match="none"):
        ordem_da_resposta(r, Decimal(100_000))
