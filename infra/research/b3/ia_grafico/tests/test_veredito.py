"""O veredito na ordem pré-registrada (desenho §6) e a parada por futilidade."""

from __future__ import annotations

from dataclasses import replace

from infra.research.b3.ia_grafico.veredito import Resumo, futilidade, julgar, relatorio

BOM = Resumo(
    n_chamadas=2000,
    n_invalidas=20,
    n_instantes=2000,
    n_operacoes=1200,
    n_censuradas=0,
    n_sem_preco_entrada=5,
    n_meses=24,
    d=5.0,
    ic=(1.0, 9.0),
    p=0.002,
    nivel_direcional=4.0,
    nivel_completo=1.5,
    metades=(4.0, 6.0),
    patamar=(3.0, 4.0),
    d_mm=2.0,
    holdout_operacoes=600,
    holdout_meses=4,
    holdout_nivel_completo=1.0,
    holdout_d=3.0,
    ic_otimista=(1.0, 9.0),
    holdout_n_chamadas=1100,
    holdout_n_invalidas=5,
    holdout_n_censuradas=0,
    holdout_n_sem_preco_entrada=3,
)


def test_confirma_quando_todas_as_clausulas_passam() -> None:
    v = julgar(BOM)
    assert v.rotulo == "CONFIRMA" and all(ok for _, ok, _ in v.clausulas)


def test_limite_de_dado_vem_antes_de_tudo() -> None:
    for campo, valor, motivo in [
        ("n_operacoes", 599, "operações"),
        ("n_invalidas", 101, "inválidas"),
        ("n_censuradas", 61, "censura"),
        ("n_sem_preco_entrada", 61, "sem preço"),
        ("n_meses", 11, "meses"),
    ]:
        v = julgar(replace(BOM, **{campo: valor}))
        assert v.rotulo == "NÃO CONFIRMA" and motivo in v.motivo, campo


def test_refuta_o_tamanho_quando_o_limite_superior_fica_abaixo_do_mre() -> None:
    v = julgar(replace(BOM, d=0.5, ic=(-1.5, 2.9), p=0.3))
    assert v.rotulo == "REFUTA"


def test_holdout_curto_ou_negativo_impede_confirma_sem_refutar() -> None:
    assert julgar(replace(BOM, holdout_operacoes=149)).rotulo == "NÃO CONFIRMA"
    assert julgar(replace(BOM, holdout_meses=2)).rotulo == "NÃO CONFIRMA"
    assert julgar(replace(BOM, holdout_nivel_completo=-0.1)).rotulo == "NÃO CONFIRMA"
    assert julgar(replace(BOM, holdout_d=None)).rotulo == "NÃO CONFIRMA"


def test_cada_clausula_sozinha_derruba_o_confirma() -> None:
    for mudanca in [
        {"d": 2.9},
        {"ic": (-0.1, 9.0)},
        {"p": 0.05},
        {"nivel_direcional": 0.0},
        {"nivel_completo": -0.01},
        {"metades": (4.0, -0.1)},
        {"patamar": (-1.0, 4.0)},
        {"d_mm": 0.0},
    ]:
        assert julgar(replace(BOM, **mudanca)).rotulo == "NÃO CONFIRMA", mudanca


def test_nan_nunca_passa_numa_clausula() -> None:
    assert julgar(replace(BOM, d=float("nan"))).rotulo == "NÃO CONFIRMA"


def test_futilidade() -> None:
    assert futilidade(nivel_completo=-0.2, n_operacoes=300) == "parar sem rótulo"
    assert futilidade(nivel_completo=0.0, n_operacoes=300) == "parar sem rótulo"
    assert futilidade(nivel_completo=float("nan"), n_operacoes=0) == "parar: instrumento"
    assert futilidade(nivel_completo=0.4, n_operacoes=300) == "seguir"


def test_relatorio_mostra_rotulo_clausulas_e_suposicoes() -> None:
    texto = relatorio(BOM, diagnosticos={"espelho_consistencia": 0.71})
    assert "CONFIRMA" in texto and "MRE" in texto and "espelho_consistencia" in texto
    assert "aproximação OHLC" in texto and "R$ 0,256" in texto


def test_censura_nao_resolvida_bloqueia_o_confirma_em_p_e_em_h() -> None:
    """Astra R2: stop + tick não limita a perda num gap; a imputação é só sensibilidade."""
    assert julgar(replace(BOM, n_censuradas=1)).rotulo == "NÃO CONFIRMA"
    assert julgar(replace(BOM, holdout_n_censuradas=1)).rotulo == "NÃO CONFIRMA"


def test_censura_no_primario_impede_tambem_o_refuta() -> None:
    """Astra R3: nem a imputação otimista é limite (o oposto pode perder mais que stop + tick)."""
    v = julgar(replace(BOM, d=0.5, ic=(-1.5, 2.0), p=0.3, n_censuradas=1))
    assert v.rotulo == "NÃO CONFIRMA" and "instrumento" in v.motivo
    # censura só no holdout não invalida um REFUTA decidido no primário inteiramente observado
    v = julgar(replace(BOM, d=0.5, ic=(-1.5, 2.0), p=0.3, holdout_n_censuradas=3))
    assert v.rotulo == "REFUTA"


def test_holdout_tem_os_proprios_portoes_de_instrumento() -> None:
    assert julgar(replace(BOM, holdout_n_sem_preco_entrada=31)).rotulo == "NÃO CONFIRMA"
    assert julgar(replace(BOM, holdout_n_invalidas=56)).rotulo == "NÃO CONFIRMA"
