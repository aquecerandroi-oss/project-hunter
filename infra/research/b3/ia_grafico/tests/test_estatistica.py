"""Contraste, bootstrap por mês e permutação por pregão — em painéis sintéticos com resposta conhecida."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

from infra.research.b3.ia_grafico.estatistica import (
    Celula,
    Painel,
    contraste,
    d_media_movel,
    ic_bootstrap_meses,
    metades,
    nivel,
    p_permutacao,
)
from infra.research.b3.ia_grafico.resposta import Lado


def _c(
    dia: date, slot: int, lado: Lado | None, b: float | None, s: float | None, **kw: object
) -> Celula:
    base: dict[str, object] = {
        "dia": dia,
        "slot": slot,
        "lado_ia": lado,
        "compra_bp": b,
        "venda_bp": s,
        "compra_pior_bp": -30.0,
        "venda_pior_bp": -30.0,
        "compra_melhor_bp": 28.0,
        "venda_melhor_bp": 28.0,
        "lado_mm": Lado.NENHUM,
    }
    base.update(kw)
    return Celula(**base)  # type: ignore[arg-type]


D1, D2 = date(2026, 1, 5), date(2026, 1, 6)


def test_contraste_a_mao_com_pi_por_horario() -> None:
    p = Painel.de_celulas([_c(D1, 0, Lado.COMPRA, 10.0, -10.0), _c(D2, 0, Lado.VENDA, -6.0, 6.0)])
    # π0 = 0,5; d1 = (1 − 0,5)(10 − (−10)) = 10; d2 = (0 − 0,5)(−6 − 6) = 6 → D = 8
    assert contraste(p) == pytest.approx(8.0)
    # nível da IA: compra +10, venda +6 → 8
    assert nivel(p) == pytest.approx(8.0)


def test_politica_de_relogio_nao_ganha_nada() -> None:
    """Compra de manhã, vende à tarde, com deriva por horário: D = 0 exato (π por horário)."""
    celulas: list[Celula] = []
    for k in range(20):
        dia = date(2026, 1, 1) + timedelta(days=k)
        celulas += [_c(dia, 0, Lado.COMPRA, 5.0 + k, -5.0 - k), _c(dia, 6, Lado.VENDA, -3.0, 3.0)]
    p = Painel.de_celulas(celulas)
    assert contraste(p) == 0.0
    assert nivel(p) > 0  # o nível é positivo, mas não é leitura do gráfico


def test_none_e_invalida_ficam_fora_e_censura_usa_o_pior_caso_do_lado_da_ia() -> None:
    p = Painel.de_celulas(
        [
            _c(D1, 0, Lado.COMPRA, None, 12.0),  # compra censurada → pior −30; venda observada
            _c(D2, 0, Lado.VENDA, 4.0, None),  # venda censurada → pior −30
            _c(D1, 1, Lado.NENHUM, 50.0, -50.0),
            _c(D2, 1, None, 50.0, -50.0),
        ]
    )
    assert p.n_operacoes == 2 and p.n_censuradas == 2
    # π0 = 0,5; d1 = 0,5·(−30 − 12) = −21; d2 = −0,5·(4 − (−30)) = −17 → D = −19
    assert contraste(p) == pytest.approx(-19.0)


def test_lado_oposto_censurado_recebe_o_melhor_caso() -> None:
    p = Painel.de_celulas([_c(D1, 0, Lado.COMPRA, 10.0, None), _c(D2, 0, Lado.VENDA, 1.0, -1.0)])
    # venda censurada no dia 1 (lado oposto ao da IA) → melhor caso +28
    # d1 = 0,5·(10 − 28) = −9; d2 = −0,5·(1 − (−1)) = −1 → D = −5
    assert contraste(p) == pytest.approx(-5.0)


def _painel_aleatorio(rng: np.random.Generator, oraculo: bool, meses: int = 12) -> Painel:
    celulas: list[Celula] = []
    for k in range(meses * 20):
        dia = date(2025, 1, 1) + timedelta(days=k * 365 // (meses * 20))
        for slot in range(12):
            mov = float(rng.normal(0, 30))
            b, s = mov - 1.5, -mov - 1.5
            if oraculo:
                lado = Lado.COMPRA if (b > s) == (rng.random() < 0.6) else Lado.VENDA
            else:
                lado = Lado.COMPRA if rng.random() < 0.55 else Lado.VENDA
            mm = Lado.COMPRA if rng.random() < 0.5 else Lado.VENDA
            celulas.append(_c(dia, slot, lado, b, s, lado_mm=mm))
    return Painel.de_celulas(celulas)


def test_ia_que_acerta_60_por_cento_e_detectada_e_a_de_moeda_nao() -> None:
    rng = np.random.default_rng(1)
    bom = _painel_aleatorio(rng, oraculo=True)
    lo, hi = ic_bootstrap_meses(bom, reps=400, semente=3)
    assert contraste(bom) > 3 and lo > 0 and hi > lo
    assert p_permutacao(bom, reps=400, semente=3) < 0.01
    assert d_media_movel(bom) > 0
    m1, m2 = metades(bom)
    assert m1 > 0 and m2 > 0

    moeda = _painel_aleatorio(np.random.default_rng(2), oraculo=False)
    assert p_permutacao(moeda, reps=400, semente=3) > 0.05
    lo, hi = ic_bootstrap_meses(moeda, reps=400, semente=3)
    assert lo < 0 < hi


def test_bootstrap_e_permutacao_reproduziveis_pela_semente() -> None:
    p = _painel_aleatorio(np.random.default_rng(5), oraculo=True, meses=6)
    assert ic_bootstrap_meses(p, reps=200, semente=9) == ic_bootstrap_meses(p, reps=200, semente=9)
    assert p_permutacao(p, reps=200, semente=9) == p_permutacao(p, reps=200, semente=9)


def test_painel_vazio_da_nan_nunca_zero() -> None:
    p = Painel.de_celulas([_c(D1, 0, Lado.NENHUM, 1.0, -1.0)])
    assert math.isnan(contraste(p)) and math.isnan(nivel(p))


def test_permutacao_so_troca_pregoes_com_a_mesma_mascara_e_nunca_da_nan() -> None:
    """Sonda da Astra R2: dias com horários diferentes não são trocáveis; sem troca admissível, p = 1."""
    p = Painel.de_celulas([_c(D1, 0, Lado.COMPRA, 10.0, -10.0), _c(D2, 1, Lado.VENDA, -10.0, 10.0)])
    assert contraste(p) == 0.0
    assert p_permutacao(p, reps=99, semente=42) == 1.0


def test_imputacao_otimista_para_o_caminho_do_refuta() -> None:
    p = Painel.de_celulas([_c(D1, 0, Lado.COMPRA, None, 12.0), _c(D2, 0, Lado.VENDA, 4.0, None)])
    # otimista: lado da IA censurado → melhor (+28). d1 = 0,5·(28 − 12) = 8; d2 = −0,5·(4 − 28) = 12
    assert contraste(p, otimista=True) == pytest.approx(10.0)
    assert contraste(p) == pytest.approx(-19.0)


def test_censura_conta_o_lado_oposto_tambem() -> None:
    """Astra R3: D usa B e S; o gêmeo ausente também é censura relevante."""
    p = Painel.de_celulas([_c(D1, 0, Lado.COMPRA, 10.0, None), _c(D2, 0, Lado.VENDA, 1.0, -1.0)])
    assert p.n_censuradas == 1
    assert p.chaves_censuradas() == {(D1, 0)}
