"""As regras do rótulo: concordância dos dois IC (r4 must-fix 2), Holm com hipótese não
testável na família fixa (r2 4.1, r5), a equação dos denominadores (r4 must-fix 1: cenários
A e B) e a precedência de instrumento/amostra sobre qualquer rótulo (r1, r3 5)."""

from __future__ import annotations

import math

from infra.research.exp_m26.classes import registrar
from infra.research.exp_m26.estimador import Intervalo
from infra.research.exp_m26.tests.fabrica import oportunidade
from infra.research.exp_m26.veredito import (
    concordancia,
    decidir,
    denominadores,
    falhas_de_instrumento,
    holm,
)
from infra.research.verdict import CONFIRMA, NAO_CONFIRMA, REFUTA


def _iv(lo: float, hi: float) -> Intervalo:
    return Intervalo(lo, hi, 0.0, 10_000)


def test_r4_refuta_exige_os_dois_limites_superiores_abaixo_do_mre() -> None:
    """IC_mint [−0,01; 0,04], IC_blocos [−0,10; 0,02]: o de blocos é mais largo mas acaba
    abaixo do MRE; o de mint ainda comporta 0,04 ⇒ nem CONFIRMA nem REFUTA."""
    assert concordancia(_iv(-0.01, 0.04), _iv(-0.10, 0.02)) == (False, False)
    assert concordancia(_iv(-0.01, 0.02), _iv(-0.10, 0.029)) == (False, True)
    assert concordancia(_iv(0.01, 0.2), _iv(0.001, 0.3)) == (True, False)
    assert concordancia(_iv(0.01, 0.2), _iv(-0.001, 0.3)) == (False, False)


def test_holm_familia_fixa_de_dois_com_nao_testavel() -> None:
    """A secundária não testável entra com p = 1: a primária precisa de p ≤ 0,025."""
    assert holm(0.03, 1.0) == (False, False)
    assert holm(0.02, 1.0) == (True, False)
    assert holm(0.02, 0.04) == (True, True)


def test_decidir_precedencia_e_ic_nao_finito() -> None:
    bom = [(True, "tudo")]
    r = decidir([("instrumento", "parada")], _iv(0.1, 0.2), _iv(0.1, 0.2), bom)
    assert (r["rotulo"], r["categoria"]) == (NAO_CONFIRMA, "instrumento")
    r = decidir([], Intervalo(math.nan, 0.01, 0.0, 10_000), _iv(-0.1, 0.01), bom)
    assert (r["rotulo"], r["categoria"]) == (NAO_CONFIRMA, "ic_nao_finito")
    r = decidir([], _iv(-0.01, 0.01), Intervalo(-0.02, 0.02, 0.05, 9_500), bom)
    assert r["rotulo"] == NAO_CONFIRMA  # 5 % de réplicas inválidas impede até REFUTA
    assert decidir([], _iv(0.1, 0.2), _iv(0.05, 0.3), bom)["rotulo"] == CONFIRMA
    r = decidir([], _iv(0.1, 0.2), _iv(0.05, 0.3), [(False, "planalto")])
    assert (r["rotulo"], r["motivos"]) == (NAO_CONFIRMA, ["planalto"])
    assert decidir([], _iv(-0.01, 0.02), _iv(-0.02, 0.02), bom)["rotulo"] == REFUTA


def _sem_proposta(mint: str, recusa: str, classe: str = "true"):
    return oportunidade(
        mint,
        classe=classe,
        proposal_refusals=(recusa,),
        proposal_id=None,
        no_proposal_reason="refused",
        aposta_=None,
    )


def test_r4_cenario_a_pedigree_desconhecido_passa_do_teto_de_5() -> None:
    regs = [registrar(oportunidade(f"t{i}")) for i in range(110)]
    regs += [registrar(oportunidade(f"f{i}", classe="false", y=0.0)) for i in range(340)]
    regs += [
        registrar(_sem_proposta(f"p{i}", "pedigree_unknown", "true" if i < 40 else "false"))
        for i in range(150)
    ]
    den = denominadores(regs, orfas_c=0)
    assert den["true"]["I"] == 40 and den["false"]["I"] == 110
    assert den["true"]["taxa_I"] > 0.05
    assert any("sem_proposta" in f for f in falhas_de_instrumento(den))


def test_r4_cenario_b_exclusao_nao_dilui_o_teto() -> None:
    regs = [registrar(_sem_proposta(f"e{i}", "creator_serial")) for i in range(800)]
    regs += [
        registrar(
            oportunidade(f"n{i}", aposta_=None, proposal_status="unfilled", proposal_refusal="cap")
        )
        for i in range(60)
    ]
    regs += [registrar(oportunidade(f"a{i}")) for i in range(140)]
    regs += [registrar(oportunidade(f"f{i}", classe="false", y=0.0)) for i in range(300)]
    den = denominadores(regs, orfas_c=0)
    t = den["true"]
    assert (t["N_bruto"], t["E"], t["N_elegivel"], t["F"], t["A"]) == (1000, 800, 200, 60, 140)
    assert t["taxa_falha"] == 0.3
    assert any("falha" in f for f in falhas_de_instrumento(den))


def test_desconhecida_sobre_elegiveis_mais_u_e_orfas() -> None:
    """r2 (F): 50 oportunidades, 8 true e 42 desconhecidas ⇒ U muito acima de 20 %."""
    regs = [registrar(oportunidade(f"t{i}")) for i in range(8)]
    regs += [registrar(oportunidade(f"u{i}", classe="unknown")) for i in range(42)]
    den = denominadores(regs, orfas_c=3)
    assert den["U"] == 45
    assert den["taxa_U"] == 45 / (8 + 0 + 45)
    falhas = falhas_de_instrumento(den)
    assert any("desconhecida" in f for f in falhas)
    assert any("false" in f for f in falhas)  # nenhum false elegível: sem taxa estimável


def test_sem_oportunidades_nao_ha_taxa() -> None:
    den = denominadores([], orfas_c=0)
    assert den["taxa_U"] is None
    assert falhas_de_instrumento(den)
