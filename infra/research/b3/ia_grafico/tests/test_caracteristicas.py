"""O simulador de características do procedimento roda o caminho decisório inteiro (escala mínima)."""

from __future__ import annotations

from infra.research.b3.ia_grafico.caracteristicas import ROTULOS, Cenario, operar, painel_sintetico
from infra.research.b3.ia_grafico.estatistica import Painel, contraste
from infra.research.b3.ia_grafico.resposta import Lado


def test_painel_sintetico_tem_pregoes_inteiros_mascaras_variaveis_none_e_invalidas() -> None:
    s = painel_sintetico(Cenario(efeito_bp=5.0, meses=3, pregoes_por_mes=4, frac_invalida=0.1), 1)
    p = Painel.de_celulas(s.avaliacao.celulas)
    assert len(p.dias) == 12
    assert 0 < (~p.elegivel).sum() < p.elegivel.size  # alguma inelegibilidade
    assert p.n_operacoes < p.elegivel.sum()  # há "none"
    assert s.n_invalidas == sum(c.lado_ia is None for c in s.avaliacao.celulas) > 0
    assert len(s.avaliacao.completo_bp) == len(s.dias_completo)


def test_braco_completo_e_distinto_e_a_media_movel_tem_lado() -> None:
    s = painel_sintetico(Cenario(efeito_bp=5.0, meses=2, pregoes_por_mes=5), 3)
    ladosmm = {c.lado_mm for c in s.avaliacao.celulas}
    assert len(ladosmm) == 2  # compra e venda: a regra concorre de verdade
    direcional: list[float] = []
    for c in s.avaliacao.celulas:
        valor = c.compra_bp if c.lado_ia is Lado.COMPRA else c.venda_bp
        if c.lado_ia in (Lado.COMPRA, Lado.VENDA) and valor is not None:
            direcional.append(valor)
    assert sorted(direcional) != sorted(x for x in s.avaliacao.completo_bp if x != 0.0)


def test_censura_sintetica_aparece_na_contagem() -> None:
    s = painel_sintetico(Cenario(efeito_bp=0.0, meses=2, pregoes_por_mes=5, frac_censura=0.2), 4)
    assert Painel.de_celulas(s.avaliacao.celulas).n_censuradas > 0
    assert s.avaliacao.n_censuradas_completo > 0


def test_efeito_grande_aparece_no_contraste() -> None:
    s = painel_sintetico(Cenario(efeito_bp=15.0, meses=6, pregoes_por_mes=10), 2)
    assert contraste(Painel.de_celulas(s.avaliacao.celulas)) > 5


def test_operar_passa_pela_futilidade_e_conta_paradas_separadas() -> None:
    contagem = operar(Cenario(efeito_bp=0.0, meses=2, pregoes_por_mes=3), repeticoes=3, reps=19)
    assert sum(contagem.values()) == 3
    assert set(contagem) <= set(ROTULOS)
