"""`completed_at`/`migrated_at` COMO CONHECIDOS EM L, lidos do histórico só de acréscimo
(`meme_token_state_history`, `0067`) — histórico SINTÉTICO escrito à mão.

Fecha o must-fix 2 da revisão do J (Astra, rodada 2): um fato registrado depois de L,
mesmo apontando para antes de L (o `LEAST` do indexador), nunca muda o valor em L.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from infra.research.exp_m26.estado_token import (
    EstadoToken,
    ExportSemProvaDeVisibilidade,
    Mudanca,
    ProvaDeVisibilidade,
    de_registro,
    em,
    provar_visibilidade,
)

L = datetime(2026, 10, 20, 2, tzinfo=UTC)
M = timedelta(minutes=1)


def _mud(
    i: int, coluna: str, antes: datetime | None, depois: datetime | None, quando: datetime
) -> Mudanca:
    return Mudanca(id=i, coluna=coluna, antes=antes, depois=depois, registrado_em=quando)


def _estado(*hist: Mudanca, completed: datetime | None = None, migrated: datetime | None = None,
            existe: bool = True) -> EstadoToken:  # fmt: skip
    return EstadoToken("m", existe, completed, migrated, tuple(hist))


def test_o_valor_em_l_e_a_ultima_mudanca_registrada_ate_l() -> None:
    a, b = L - 50 * M, L - 90 * M
    e = _estado(
        _mud(1, "completed_at", None, a, L - 40 * M),
        _mud(2, "completed_at", a, b, L - 5 * M),
        _mud(3, "migrated_at", None, L - 3 * M, L - 2 * M),
        completed=b,
        migrated=L - 3 * M,
    )
    v = em(e, L)
    assert (v.completed_at, v.migrated_at, v.via) == (b, L - 3 * M, "history")


def test_correcao_tardia_por_least_depois_de_l_nao_muda_o_valor_em_l() -> None:
    """O contraexemplo da Astra: em L+10 min chega uma conclusão anterior às vendas."""
    cedo, tardio = L - 30 * M, L - 120 * M
    e = _estado(
        _mud(1, "completed_at", None, cedo, L - 20 * M),
        _mud(2, "completed_at", cedo, tardio, L + 10 * M),
        completed=tardio,
    )
    assert em(e, L).completed_at == cedo
    assert em(e, L + 10 * M).completed_at == tardio


def test_o_mesmo_instante_desempata_pelo_id() -> None:
    e = _estado(
        _mud(8, "completed_at", L - 9 * M, L - 10 * M, L - 2 * M),
        _mud(7, "completed_at", None, L - 9 * M, L - 2 * M),
        completed=L - 10 * M,
    )
    assert (em(e, L).completed_at, em(e, L).via) == (L - 10 * M, "history")


def test_a_ordem_e_a_do_commit_dentro_do_mint_nao_a_do_relogio() -> None:
    """Astra (J rodada 4): com o relógio do servidor recuando entre duas mudanças, ordenar
    pelo carimbo elegeria a mudança velha como a última e acusaria divergência num
    histórico íntegro. Dentro de um mint o `id` é a ordem de commit (lock de linha)."""
    e = _estado(
        _mud(1, "completed_at", None, L - 30 * M, L - 10 * M),
        _mud(2, "completed_at", L - 30 * M, L - 40 * M, L - 20 * M),  # relógio recuou
        completed=L - 40 * M,
    )
    v = em(e, L)
    assert (v.completed_at, v.via) == (L - 40 * M, "history")


def test_a_visibilidade_em_l_e_provada_pelo_export_ou_ele_e_recusado() -> None:
    """Toda mudança carimbada até L tem de estar visível no export: nenhuma transação
    escritora aberta desde antes de L em voo quando o export começa; nenhuma escritora de
    início desconhecido; nenhuma transação preparada; relógio sem recuo; e o papel do
    export enxerga, de fato, a atividade de todos (Astra, rodadas 2 e 3)."""
    ok = ProvaDeVisibilidade(ve_toda_atividade=True)
    provar_visibilidade(ok, leitura=L)
    provar_visibilidade(replace(ok, escritoras_abertas_desde=L + M), leitura=L)
    provar_visibilidade(replace(ok, relogio_recuou_s=Decimal("0.9")), leitura=L)
    for campos, motivo in (
        ({"escritoras_abertas_desde": L}, "em voo"),
        ({"escritoras_sem_inicio": 1}, "sem início"),
        ({"preparadas": 1}, "preparada"),
        ({"relogio_recuou_s": Decimal("1.5")}, "relógio"),
        ({"ve_toda_atividade": False}, "atividade"),
    ):
        with pytest.raises(ExportSemProvaDeVisibilidade, match=motivo):
            provar_visibilidade(replace(ok, **campos), leitura=L)  # type: ignore[arg-type]


def test_linha_corrente_diferente_do_ultimo_registro_denuncia_gatilho_contornado() -> None:
    """A última mudança do histórico tem de ser a linha corrente do export (os dois saem da
    mesma transação); se não for, alguém escreveu sem o gatilho — estado desconhecido."""
    e = _estado(_mud(1, "completed_at", None, L - 50 * M, L - 40 * M), completed=L - 90 * M)
    assert em(e, L).via == "historico_diverge"
    sem_linha = EstadoToken(
        "m", False, None, None, (_mud(1, "migrated_at", None, L - M, L - 9 * M),)
    )
    assert em(sem_linha, L).via == "historico_diverge"


def test_nascido_depois_de_l_ou_primeira_mudanca_depois_de_l_e_nulo_em_l() -> None:
    e = _estado(_mud(1, "completed_at", None, L - 60 * M, L + M), completed=L - 60 * M)
    v = em(e, L)
    assert (v.completed_at, v.via) == (None, "history")


def test_valor_anterior_ao_historico_vem_do_antes_e_e_dito() -> None:
    antigo, recuado = L - 3 * timedelta(days=1), L - 4 * timedelta(days=1)
    e = _estado(_mud(1, "completed_at", antigo, recuado, L + M), completed=recuado)
    v = em(e, L)
    assert (v.completed_at, v.via) == (antigo, "current_row_pre_history")


def test_sem_historico_a_linha_atual_so_vale_se_anterior_a_l_e_e_dito() -> None:
    v = em(_estado(completed=L - M), L)
    assert (v.completed_at, v.via) == (L - M, "current_row_pre_history")
    v = em(_estado(completed=L + M), L)
    assert (v.completed_at, v.via) == (None, "current_row_pre_history")
    v = em(_estado(), L)
    assert (v.completed_at, v.migrated_at, v.via) == (None, None, "history")


def test_token_ausente_e_dito() -> None:
    v = em(_estado(existe=False), L)
    assert (v.completed_at, v.migrated_at, v.via) == (None, None, "token_ausente")


def test_de_registro_le_a_linha_do_export() -> None:
    r = json.loads(
        json.dumps(
            {
                "tipo": "estado_token",
                "mint": "Mint1pump",
                "token_existe": True,
                "completed_at_atual": "2026-10-20T00:30:00+00:00",
                "migrated_at_atual": None,
                "historico": [
                    {
                        "id": 12,
                        "coluna": "completed_at",
                        "antes": None,
                        "depois": "2026-10-20T00:30:00+00:00",
                        "registrado_em": "2026-10-20T00:31:02.123456+00:00",
                    }
                ],
            }
        ),
        parse_float=Decimal,
    )
    e = de_registro(r)
    assert e.mint == "Mint1pump" and e.existe
    assert e.historico == (
        Mudanca(
            12,
            "completed_at",
            None,
            datetime(2026, 10, 20, 0, 30, tzinfo=UTC),
            datetime(2026, 10, 20, 0, 31, 2, 123456, tzinfo=UTC),
        ),
    )
    with pytest.raises(ValueError, match="coluna"):
        de_registro({**r, "historico": [{**r["historico"][0], "coluna": "name"}]})
    with pytest.raises(ValueError, match="fuso"):
        de_registro({**r, "completed_at_atual": "2026-10-20T00:30:00"})
