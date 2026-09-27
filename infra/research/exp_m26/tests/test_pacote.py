"""A secundária D_pacote = H − L por par completo, os pares ausentes e o estresse.

Cenários: r1/r2 (chave do par = mint, `features_end_time`, foto de fill; qualquer outro
desalinhamento é par ausente, nunca substituído), r3 must-fix 2 (L ausente que teria +1,00
não vira vantagem de H: L no p90 observado de L), r4/r5 (sem fill ≠ preenchido sem
desfecho; nível de H quando as duas pernas faltam), r3 4b (pares numa rajada: poucos
blocos ⇒ não testável) e a revisão do J (propostas órfãs de R1 contam como ausentes:
100 completos + 26 órfãs = 20,6 % > 20 %).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from infra.research.exp_m26.constantes import RULE_SET_H, RULE_SET_L
from infra.research.exp_m26.modelo import Oportunidade
from infra.research.exp_m26.pacote import Par, parear, secundaria
from infra.research.exp_m26.tests.fabrica import T0, aposta, oportunidade


def _perna(braco: str, mint: str, y: float | None, b: int = 0, **kw: object) -> Oportunidade:
    at = T0 + timedelta(hours=6 * b, minutes=1)
    return replace(oportunidade(mint, at=at, y=y, **kw), rule_set_id=braco)  # type: ignore[arg-type]


def _par(mint: str, yh: float | None, yl: float | None, b: int = 0) -> Par:
    return parear(mint, _perna(RULE_SET_L, mint, yl, b), _perna(RULE_SET_H, mint, yh, b))


def test_par_completo_e_diferenca() -> None:
    p = _par("m", 0.3, 0.1)
    assert (p.estado, p.y_h, p.y_l) == ("completo", pytest.approx(0.3), pytest.approx(0.1))


def test_desalinhamentos_sao_pares_ausentes() -> None:
    pl = _perna(RULE_SET_L, "m", 0.1)
    h = _perna(RULE_SET_H, "m", 0.2)
    assert parear("m", pl, None).estado == "ausente"
    assert parear("m", None, h).detalhe == "sem_registro_L"
    outro_minuto = replace(h, features_end_time=h.features_end_time - timedelta(minutes=1))
    assert parear("m", pl, outro_minuto).detalhe == "minuto_diferente"
    assert h.aposta is not None
    outra_foto = replace(h, aposta=replace(h.aposta, fill_source="curve_ws"))
    assert parear("m", pl, outra_foto).detalhe == "foto_de_fill"
    sem_fill = replace(h, aposta=None, proposal_status="unfilled", proposal_refusal="cap")
    assert parear("m", pl, sem_fill).detalhe.startswith("H:F")
    sem_proposta = replace(pl, proposal_id=None, no_proposal_reason="insert_failed", aposta=None)
    assert parear("m", sem_proposta, h).detalhe.startswith("L:I")
    nao_fiel = replace(pl, fidelity="write_failed")
    assert parear("m", nao_fiel, h).detalhe == "L:fidelity:write_failed"


def test_exclusao_substantiva_sai_do_denominador() -> None:
    pl = _perna(
        RULE_SET_L,
        "m",
        None,
        proposal_refusals=("symbol_clone",),
        proposal_id=None,
        no_proposal_reason="refused",
        aposta_=None,
    )
    assert parear("m", pl, None).estado == "E"


def test_estados_estressaveis() -> None:
    assert _par("m", None, 0.1).estado == "H_C"
    assert _par("m", 0.1, None).estado == "L_C"
    assert _par("m", None, None).estado == "ambos_C"


def _painel(n: int, blocos: int, dh: float = 0.05) -> list[Par]:
    return [_par(f"m{i}", dh + 0.001 * (i % 7), 0.001 * (i % 5), b=i % blocos) for i in range(n)]


def test_secundaria_valores_e_precondicoes() -> None:
    pares = _painel(120, 12)
    s = secundaria(pares, reps=500, seed=1)
    ds = [float(p.y_h or 0.0) - float(p.y_l or 0.0) for p in pares]
    assert s["d"] == pytest.approx(sum(ds) / len(ds))
    assert (s["completos"], s["comuns"], s["blocos"]) == (120, 120, 12)
    assert s["testavel"] is True
    assert s["ic_mint"].lo > 0 and s["ic_blocos"].lo > 0
    assert s["p"] == pytest.approx(1 / 501)


def test_orfas_de_r1_contam_como_ausentes() -> None:
    pares = _painel(100, 12) + [parear(f"o{i}", None, None) for i in range(26)]
    s = secundaria(pares, reps=200, seed=1)
    assert s["comuns"] == 126
    assert s["taxa_ausentes"] == pytest.approx(26 / 126)
    assert s["testavel"] is False
    assert s["motivo_nao_testavel"].startswith("instrumento")


def test_rajada_em_poucos_blocos_nao_e_testavel() -> None:
    s = secundaria(_painel(150, 3), reps=200, seed=1)
    assert s["blocos"] == 3
    assert s["testavel"] is False
    assert s["motivo_nao_testavel"].startswith("amostra")


def test_p_centrado_sob_a_nula_sem_efeito() -> None:
    pares = [_par(f"m{i}", 0.01 * ((i % 5) - 2), 0.0, b=i % 12) for i in range(120)]
    s = secundaria(pares, reps=500, seed=2)
    assert abs(s["d"]) < 1e-12
    assert s["p"] > 0.5


def test_estresse_tres_casos_de_par_incompleto() -> None:
    """L ausente que teria +1,00 não vira vantagem: L entra no p90 dos L completos; H
    ausente entra em perda integral; ambos ausentes: diferença no p10 das completas e
    nível de H em perda integral."""
    base = _painel(120, 12)
    extras = [_par("hc", None, 0.2), _par("lc", 0.1, None), _par("ac", None, None)]
    s = secundaria(base + extras, reps=300, seed=3)
    import numpy as np

    yl = np.array([p.y_l for p in base])
    d = np.array([p.y_h - p.y_l for p in base])  # type: ignore[operator]
    esperados = [-1.0 - 0.2, 0.1 - float(np.quantile(yl, 0.9)), float(np.quantile(d, 0.1))]
    assert s["estresse"]["d"] == pytest.approx((d.sum() + sum(esperados)) / 123)
    yh = np.array([p.y_h for p in base])
    assert s["estresse"]["nivel_h"] == pytest.approx((yh.sum() - 1.0 + 0.1 - 1.0) / 123)
    assert s["estresse"]["ic_mint"].finito
    assert s["completos"] == 120 and s["comuns"] == 123


def test_sem_fill_nao_recebe_custo_de_posicao() -> None:
    pl = _perna(RULE_SET_L, "sf", 0.1)
    h = replace(_perna(RULE_SET_H, "sf", 0.1), aposta=None, proposal_status="expired")
    s = secundaria(_painel(120, 12) + [parear("sf", pl, h)], reps=200, seed=4)
    assert s["estresse"]["n"] == 120
    assert s["comuns"] == 121


def test_aposta_aberta_na_leitura_e_c_nao_f() -> None:
    p = parear(
        "m", _perna(RULE_SET_L, "m", 0.1), _perna(RULE_SET_H, "m", 0.1, aposta_=aposta(None))
    )
    assert p.estado == "H_C"
