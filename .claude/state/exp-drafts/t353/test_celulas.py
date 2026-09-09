"""Testes do motor de celulas da T3.53, com series sinteticas e valor esperado.

Tres coisas precisam ser verdade antes de qualquer numero da nota valer:

1. **Holm** e o Holm do livro (o passo desce, para no primeiro que falha).
2. O bootstrap vetorizado devolve o **mesmo estimador** do laco ingenuo de
   ``t342-blocos/blocos.py``, que ja foi usado nas T3.42/T3.47 - a conferencia
   passa pela identidade ``media(celula) - media(tudo) = (1-w) * delta``.
3. Em serie sintetica com efeito conhecido, o delta bate no numero exato e o
   intervalo nao inventa incerteza onde nao ha.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "t342-blocos"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import blocos  # noqa: E402  (oraculo reutilizado, nao modificado)
import celulas  # noqa: E402


def test_holm_desce_o_passo_conforme_sobrevive():
    # m = 4; limiares na ordem crescente de p: 0,0125 / 0,0167 / 0,025 / 0,05
    # 0,001 <= 0,0125 ok; 0,013 <= 0,0167 ok; 0,020 <= 0,025 ok; 0,90 > 0,05 nao.
    ps = [0.001, 0.020, 0.013, 0.90]
    assert celulas.holm(ps) == [True, True, True, False]


def test_holm_para_no_primeiro_que_falha():
    # 0,001 <= 0,0125 ok; 0,020 > 0,0167 -> para: 0,03 nem chega a ser testado.
    ps = [0.001, 0.020, 0.030, 0.90]
    assert celulas.holm(ps) == [True, False, False, False]


def test_holm_nao_salva_ninguem_quando_o_menor_ja_falha():
    assert celulas.holm([0.03, 0.04]) == [False, False]


def test_holm_com_um_teste_e_o_teste_cru():
    assert celulas.holm([0.049]) == [True]
    assert celulas.holm([0.051]) == [False]


def test_pf_e_media_em_valores_conhecidos():
    r = np.array([2.0, -1.0, 1.0, -1.0])
    assert celulas.pf(r) == pytest.approx(3.0 / 2.0)
    assert celulas.media(r) == pytest.approx(0.25)
    assert np.isnan(celulas.media(np.array([])))
    assert celulas.pf(np.array([1.0, 2.0])) == float("inf")


def _serie_com_efeito(dias: int = 10, por_dia: int = 10, efeito: float = 1.0):
    """Metade de cada dia dentro da celula com ``efeito``, metade fora com 0."""
    d, r, dentro = [], [], []
    for dia in range(dias):
        for k in range(por_dia):
            d.append(dia)
            na_celula = k < por_dia // 2
            dentro.append(na_celula)
            r.append(efeito if na_celula else 0.0)
    return (
        np.array(d, dtype=int),
        np.array(r, dtype=float),
        np.array(dentro, dtype=bool),
    )


def test_efeito_exato_sem_ruido():
    d, r, dentro = _serie_com_efeito(efeito=1.0)
    delta, ic, p, validas = celulas.bootstrap_celula(d, 10, r, dentro, reamostragens=2000)
    assert delta == pytest.approx(1.0)
    assert ic == pytest.approx((1.0, 1.0))  # sem ruido, nao ha incerteza a inventar
    assert p == pytest.approx(2.0 / 2001.0)
    assert validas == 2000


def test_sem_efeito_o_intervalo_cobre_zero():
    rng = np.random.default_rng(7)
    d = np.repeat(np.arange(20), 12)
    r = rng.normal(0.0, 1.0, size=d.size)
    dentro = np.tile(np.array([True] * 6 + [False] * 6), 20)
    delta, ic, p, _ = celulas.bootstrap_celula(d, 20, r, dentro, reamostragens=3000)
    assert ic[0] < 0.0 < ic[1]
    assert p > 0.05


def test_mesmo_estimador_do_laco_ingenuo_de_blocos():
    """``blocos`` mede celula-contra-tudo; aqui, celula-contra-resto.

    A ponte e a identidade ``celula - tudo = (1-w) * (celula - resto)``.
    """
    rng = np.random.default_rng(11)
    n_dias, por_dia = 15, 8
    linhas, d, r, dentro = [], [], [], []
    for dia in range(n_dias):
        for k in range(por_dia):
            na_celula = k % 3 == 0
            valor = float(rng.normal(0.3 if na_celula else -0.1, 0.5))
            linhas.append(
                blocos.Decisao(dia=f"2026-08-{dia + 1:02d}", atr_pct=1.0 if na_celula else 0.0, r_net=valor)
            )
            d.append(dia)
            r.append(valor)
            dentro.append(na_celula)
    d = np.array(d, dtype=int)
    r = np.array(r, dtype=float)
    dentro = np.array(dentro, dtype=bool)

    ref = blocos.contraste_por_piso(linhas, 0.5, reamostragens=500)
    delta, _, _, _ = celulas.bootstrap_celula(d, n_dias, r, dentro, reamostragens=500)

    w = dentro.mean()
    assert ref.delta == pytest.approx((1.0 - w) * delta, rel=1e-9)
    assert ref.n_variante == int(dentro.sum())
    assert ref.exp_variante == pytest.approx(r[dentro].mean())


def test_dimensoes_hora_e_uma_particao_so():
    """Hora BRT e hora UTC nao podem virar duas dimensoes: e a mesma particao."""
    linhas = [
        {
            "symbol": "BTCUSDT",
            "hora_br": "21",
            "hora_utc": "0",
            "dow_br": "1",
            "regime": "SIDEWAYS",
            "trend": "flat",
            "vol": "normal",
            "custo_id": "0.05",
        },
        {
            "symbol": "BTCUSDT",
            "hora_br": "22",
            "hora_utc": "1",
            "dow_br": "1",
            "regime": "SIDEWAYS",
            "trend": "flat",
            "vol": "normal",
            "custo_id": "0.15",
        },
    ]
    dims = celulas.dimensoes(linhas)
    nomes = [d for d, _, _ in dims]
    assert nomes.count("hora") == 2  # duas horas distintas, uma dimensao
    rotulos = {rot for dim, rot, _ in dims if dim == "hora"}
    assert rotulos == {"21h BRT (00h UTC)", "22h BRT (01h UTC)"}
    faixas = {rot for dim, rot, _ in dims if dim == "pedagio"}
    assert faixas == {"pedagio < 0,10 R", "pedagio 0,10-0,20 R", "pedagio > 0,20 R"}


def test_celula_pequena_nao_e_julgavel():
    linhas = []
    for dia in range(3):
        for k in range(20):
            linhas.append(
                {
                    "symbol": "BTCUSDT" if k == 0 else "ETHUSDT",
                    "hora_br": str(k % 4),
                    "hora_utc": str((k % 4 + 3) % 24),
                    "dow_br": "1",
                    "regime": "SIDEWAYS",
                    "trend": "flat",
                    "vol": "normal",
                    "custo_id": "0.05",
                    "dia_br": f"2026-08-0{dia + 1}",
                    "r_net": "0.1",
                    "r_gross": "0.2",
                    "motivo": "target",
                }
            )
    resultado = celulas.analisar(linhas, "teste v1", "replay", reamostragens=200)
    assert all(not c.julgavel for c in resultado)  # so 3 dias: nada e julgavel
    btc = next(c for c in resultado if c.rotulo == "BTCUSDT")
    assert btc.n == 3 and btc.dias == 3


def test_deduplicar_funde_mascaras_identicas_e_complementares():
    m1 = np.array([True, True, False, False])
    igual = np.array([True, True, False, False])
    comp = np.array([False, False, True, True])
    outra = np.array([True, False, True, False])
    dims = [
        ("regime", "SIDEWAYS", m1),
        ("trend_x_vol", "flat/normal", igual),
        ("pedagio", "pedagio > 0,20 R", comp),
        ("mercado", "BTCUSDT", outra),
    ]
    saida, fusoes = celulas.deduplicar(dims)
    assert len(saida) == 2
    assert saida[0][1] == "SIDEWAYS = flat/normal (vs pedagio > 0,20 R)"
    assert saida[1][1] == "BTCUSDT"
    assert len(fusoes) == 2
