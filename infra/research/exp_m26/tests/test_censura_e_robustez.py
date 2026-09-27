"""Estresse de censura da primária e as condições de robustez (planalto, tercis, identidade).

Contraexemplos sintéticos da Astra, com as contas que ela publicou:

- r2 4.2: 100 true, 85 observados a +0,06, 15 censurados, controle 0 — imputar p10 (−0,10)
  dá +0,036, mas a drenagem sem foto (perda integral) inverte o sinal;
- r3 (b): 200 true, 180 observados a +0,10, 20 censurados — −0,50 dá D = +0,04, perda
  integral dá −0,01, inversão em −0,9 (D = 0) e −0,6 (D = MRE);
- identidade (J): o slope separa exatamente os mesmos mints que a linha, e um único true
  sem slope infla o D_linha integral — só a população comum mostra a redundância.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from infra.research.exp_m26.censura import diagnostico, grade, inversao, unidades_primarias
from infra.research.exp_m26.classes import Registro, registrar
from infra.research.exp_m26.estimador import estimar
from infra.research.exp_m26.robustez import identidade, planalto, tercis
from infra.research.exp_m26.tests.fabrica import T0, aposta, oportunidade


def _estrato(
    b: int, n_true_obs: int, y_true: float, n_true_cens: int, n_false: int
) -> list[Registro]:
    at = T0 + timedelta(hours=6 * b, minutes=1)
    regs: list[Registro] = []
    for i in range(n_true_obs):
        regs.append(registrar(oportunidade(f"t{b}-{i}", at=at, y=y_true)))
    for i in range(n_true_cens):
        regs.append(registrar(oportunidade(f"c{b}-{i}", at=at, y=None)))
    for i in range(n_false):
        regs.append(registrar(oportunidade(f"f{b}-{i}", at=at, classe="false", y=0.0)))
    return regs


def _r3() -> list[Registro]:
    return [r for b in range(10) for r in _estrato(b, 18, 0.10, 2, 40)]


def test_r3_estresse_de_perda_integral_inverte_o_que_o_nominal_preserva() -> None:
    regs = _r3()
    base = estimar(unidades_primarias(regs, estresse=False)[0])
    assert base.d == pytest.approx(0.10)
    assert diagnostico(regs, -0.50).d == pytest.approx(0.04)
    estressado = estimar(unidades_primarias(regs, estresse=True)[0])
    assert estressado.d == pytest.approx(-0.01)
    assert estressado.media_true == pytest.approx(-0.01)
    assert inversao(regs, 0.0) == pytest.approx(-0.9)
    assert inversao(regs, 0.03) == pytest.approx(-0.6)


def test_r2_imputar_quantil_observado_nao_protege_da_cauda() -> None:
    regs = _estrato(0, 85, 0.06, 15, 100)
    assert estimar(unidades_primarias(regs, estresse=True)[0]).d == pytest.approx(
        (85 * 0.06 - 15) / 100
    )
    assert diagnostico(regs, -0.10).d == pytest.approx(0.036)


def test_perda_integral_e_o_sol_spent_sem_somar_a_taxa_de_novo() -> None:
    """`sol_spent` já contém a taxa de compra (paper_fill): −sol_spent/size_sol."""
    o = oportunidade("x", aposta_=aposta(None, sol_spent=Decimal("0.0712")))
    r = registrar(o)
    assert r.motivo == "C"
    assert r.perda == pytest.approx(-0.0712 / 0.07)


def test_sem_censurado_true_nao_ha_ponto_de_inversao() -> None:
    regs = [r for b in range(3) for r in _estrato(b, 5, 0.1, 0, 5)]
    assert inversao(regs, 0.0) is None


def test_false_censurado_so_mexe_no_peso_e_estrato_sem_false_observado_sai() -> None:
    at_a = T0 + timedelta(minutes=1)
    at_b = T0 + timedelta(hours=6, minutes=1)
    regs = [
        registrar(oportunidade("ta", at=at_a, y=0.2)),
        registrar(oportunidade("fa", at=at_a, classe="false", y=0.0)),
        registrar(oportunidade("fa2", at=at_a, classe="false", y=None)),
        registrar(oportunidade("tb", at=at_b, y=0.9)),
        registrar(oportunidade("fb", at=at_b, classe="false", y=None)),
    ]
    e = estimar(unidades_primarias(regs, estresse=True)[0])
    assert e.estratos == 1
    assert e.d == pytest.approx(0.2)
    assert e.n_false == 2


def test_grade_2d_nunca_inventa_quantil_de_grupo_vazio() -> None:
    regs = _r3()
    pontos = grade(regs)
    assert len(pontos) == 25
    xs_true = sorted({p["true_ausente"] for p in pontos})
    assert xs_true[0] == -1.0
    assert 0.10 in xs_true
    so_true = [r for r in regs if r.classe == "true"]
    assert grade(so_true) == []


# ------------------------------------------------------------------- robustez


def _dist(mint: str, b: int, dist: str, y: float) -> Registro:
    at = T0 + timedelta(hours=6 * b, minutes=1)
    return registrar(oportunidade(mint, at=at, distance_to_support_pct=Decimal(dist), y=y))


def test_planalto_exige_sinal_nos_tres_tetos() -> None:
    regs: list[Registro] = []
    for b in range(4):
        regs += [_dist(f"a{b}{i}", b, "0.05", 0.2) for i in range(5)]
        regs += [_dist(f"c{b}{i}", b, "0.40", -0.9) for i in range(5)]
        regs += [_dist(f"z{b}{i}", b, "0.90", 0.0) for i in range(10)]
    res = planalto(regs)
    assert res["0.10"] > 0 and res["0.25"] > 0
    assert res["0.50"] < 0
    assert not res["ok"]


def _terco(regs: list[Registro], progresso: str, n: int, y_true: float, tag: str) -> None:
    for b in range(2):
        at = T0 + timedelta(hours=6 * b, minutes=1)
        p = Decimal(progresso)
        regs += [
            registrar(oportunidade(f"{tag}t{b}{i}", at=at, y=y_true, curve_progress_pct=p))
            for i in range(n)
        ]
        regs += [
            registrar(
                oportunidade(f"{tag}f{b}{i}", at=at, classe="false", y=0.0, curve_progress_pct=p)
            )
            for i in range(n)
        ]


def test_tercis_por_posto_avaliavel_com_20_por_grupo_nos_estratos() -> None:
    regs: list[Registro] = []
    _terco(regs, "0.10", 10, 0.1, "a")
    _terco(regs, "0.50", 10, -0.1, "b")
    _terco(regs, "0.80", 10, 0.1, "c")
    res = tercis(regs)
    assert [t["n"] for t in res["tercis"]] == [40, 40, 40]
    assert [t["avaliavel"] for t in res["tercis"]] == [True, True, True]
    assert [t["d"] > 0 for t in res["tercis"]] == [True, False, True]
    assert res["ok"] is True


def test_tercis_menos_de_dois_avaliaveis_nao_satisfaz() -> None:
    regs: list[Registro] = []
    _terco(regs, "0.10", 5, 0.1, "a")
    _terco(regs, "0.50", 5, 0.1, "b")
    _terco(regs, "0.80", 5, 0.1, "c")
    res = tercis(regs)
    assert not any(t["avaliavel"] for t in res["tercis"])
    assert res["ok"] is False


def test_tercis_sinal_so_entre_tercis_e_progresso() -> None:
    regs: list[Registro] = []
    _terco(regs, "0.10", 10, -0.1, "a")
    _terco(regs, "0.50", 10, -0.1, "b")
    _terco(regs, "0.80", 10, 0.3, "c")
    assert tercis(regs)["ok"] is False


def test_tercis_empates_desfeitos_pelo_mint_sem_olhar_desfecho() -> None:
    """r2 4.4: progresso todo igual — os postos são desfeitos pelo mint, os tercis têm o
    mesmo tamanho e trocar os desfechos não muda quem cai em cada tercil."""
    regs: list[Registro] = []
    _terco(regs, "0.30", 15, 0.1, "a")
    res = tercis(regs)
    assert [t["n"] for t in res["tercis"]] == [20, 20, 20]
    invertido = [
        registrar(replace(r.o, aposta=aposta(-0.5 if r.classe == "true" else 0.5))) for r in regs
    ]
    composicao = [(t["n"], t["n_true"], t["n_false"]) for t in res["tercis"]]
    assert [(t["n"], t["n_true"], t["n_false"]) for t in tercis(invertido)["tercis"]] == (
        composicao
    )


def test_identidade_no_suporte_comum_das_duas_divisoes() -> None:
    """Astra, revisão do J (must-fix 1): bloco A, slope separa exatamente os grupos (true
    0,04); bloco B, todos com slope > 0 (true 0,20). B só tem os dois grupos na divisão da
    linha: fora do suporte comum. Esperado D_linha = D_slope = 0,04 ⇒ identidade dispara."""
    regs: list[Registro] = []
    for b, y, slope_false in ((0, 0.04, "-0.1"), (1, 0.20, "0.1")):
        at = T0 + timedelta(hours=6 * b, minutes=1)
        regs += [
            registrar(oportunidade(f"t{b}{i}", at=at, y=y, mcap_slope_15m=Decimal("0.3")))
            for i in range(10)
        ]
        regs += [
            registrar(
                oportunidade(
                    f"f{b}{i}", at=at, classe="false", y=0.0, mcap_slope_15m=Decimal(slope_false)
                )
            )
            for i in range(10)
        ]
    res = identidade(regs)
    assert res["d_linha_comparavel"] == pytest.approx(0.04)
    assert res["d_slope"] == pytest.approx(0.04)
    assert res["ok"] is False


def test_identidade_na_populacao_comum() -> None:
    regs: list[Registro] = []
    for b in range(10):
        at = T0 + timedelta(hours=6 * b, minutes=1)
        regs += [
            registrar(oportunidade(f"t{b}{i}", at=at, y=0.04, mcap_slope_15m=Decimal("0.3")))
            for i in range(10)
        ]
        regs.append(registrar(oportunidade(f"x{b}", at=at, y=0.40, mcap_slope_15m=None)))
        regs += [
            registrar(
                oportunidade(
                    f"f{b}{i}", at=at, classe="false", y=0.0, mcap_slope_15m=Decimal("-0.1")
                )
            )
            for i in range(30)
        ]
    assert estimar(unidades_primarias(regs, estresse=False)[0]).d == pytest.approx(0.8 / 11)
    res = identidade(regs)
    assert res["ausentes"] == pytest.approx(10 / 410)
    assert res["d_linha_comparavel"] == pytest.approx(0.04)
    assert res["d_slope"] == pytest.approx(0.04)
    assert res["ok"] is False


def test_identidade_slope_ausente_demais_nao_satisfaz() -> None:
    regs = _r3()
    sem = [registrar(oportunidade(f"s{i}", y=0.1, mcap_slope_15m=None)) for i in range(200)]
    res = identidade(regs + sem)
    assert res["ausentes"] > 0.20
    assert res["ok"] is False
