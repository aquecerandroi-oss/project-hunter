"""Classes de `linha_ok`, o motivo único E → I → F → C → A e a guarda anti-antecipação.

Cenários das rodadas 1–5 da Astra (`.claude/state/dialogue-EXP-M26.md`) presos aqui:
`flat` coberto é `false` (r3a), `out_of_range` é `false` contado à parte (r3a), falha de
coleta nunca vira `false` (r2 4.3), pedigree desconhecido é instrumento e não exclusão
(r4 must-fix 1), venda sem praça pelo estado da foto, qualquer que seja o gatilho (r2 5d),
e o relógio único do tique (r3 must-fix 1).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from infra.research.exp_m26.classes import classe_linha, motivo
from infra.research.exp_m26.modelo import na_leitura
from infra.research.exp_m26.tests.fabrica import T0, aposta, oportunidade
from infra.research.guards import LookAheadError


@pytest.mark.parametrize(
    ("kw", "esperado"),
    [
        ({}, ("true", "tracada")),
        ({"distance_to_support_pct": Decimal("0")}, ("true", "tracada")),
        ({"distance_to_support_pct": Decimal("0.25")}, ("true", "tracada")),
        ({"distance_to_support_pct": Decimal("0.2501")}, ("false", "tracada")),
        ({"distance_to_support_pct": Decimal("-0.01")}, ("false", "tracada")),
        ({"higher_lows": False}, ("false", "tracada")),
        ({"coverage_status": "covered_from_birth"}, ("true", "tracada")),
        ({"coverage_status": "gap"}, ("desconhecida", "cobertura:gap")),
        ({"coverage_status": "unread"}, ("desconhecida", "cobertura:unread")),
        ({"line_reason": "flat"}, ("false", "flat")),
        ({"line_reason": "out_of_range"}, ("false", "out_of_range")),
        ({"line_reason": "no_snapshot"}, ("desconhecida", "linha:no_snapshot")),
        ({"line_reason": "too_few_points"}, ("desconhecida", "linha:too_few_points")),
        ({"distance_to_support_pct": None}, ("desconhecida", "linha:ausente")),
        ({"features_computed_at": None}, ("desconhecida", "computed_at_ausente")),
    ],
)
def test_as_tres_classes_congeladas(kw: dict[str, object], esperado: tuple[str, str]) -> None:
    assert classe_linha(oportunidade(**kw)) == esperado  # type: ignore[arg-type]


def test_flat_com_lacuna_e_desconhecida_nunca_false() -> None:
    """r2 4.3: falha de coleta fica fora dos dois grupos, mesmo com `flat`."""
    o = oportunidade(classe="flat", coverage_status="gap")
    assert classe_linha(o) == ("desconhecida", "cobertura:gap")


def test_teto_de_distancia_para_o_planalto() -> None:
    o = oportunidade(distance_to_support_pct=Decimal("0.40"))
    assert classe_linha(o)[0] == "false"
    assert classe_linha(o, teto=Decimal("0.50"))[0] == "true"
    assert classe_linha(oportunidade(), teto=Decimal("0.05"))[0] == "false"


# ------------------------------------------------------------------ antecipação


def test_feature_dobrada_depois_do_tique_e_defeito_do_export() -> None:
    """Relógio único (r3): a feature que conta é a lida no tique; `computed_at` depois
    de `evaluated_at` quer dizer que o registro não é o do tique."""
    o = oportunidade()
    tarde = replace(o, features_computed_at=o.evaluated_at + timedelta(seconds=1))
    with pytest.raises(LookAheadError):
        classe_linha(tarde)
    futuro = replace(o, features_end_time=o.evaluated_at + timedelta(minutes=1))
    with pytest.raises(LookAheadError):
        classe_linha(futuro)


def test_a_classe_nao_muda_quando_o_desfecho_ou_o_depois_muda() -> None:
    """A classe lê só os insumos do tique: trocar a aposta, o PnL, a proposta ou o
    estado do token depois do tique não a move."""
    o = oportunidade(distance_to_support_pct=Decimal("0.12"))
    outra = replace(
        o,
        aposta=aposta(-0.9, token_migrated_at=T0),
        proposal_status="expired",
        prior_other_bet=True,
    )
    assert classe_linha(o) == classe_linha(outra) == ("true", "tracada")


def test_resultado_depois_da_leitura_nao_existe_na_leitura() -> None:
    """Guarda do desfecho: saída depois do instante da leitura = aberta; fill depois
    da leitura = sem fill."""
    leitura = T0 + timedelta(hours=1)
    fechada_depois = aposta(0.3, entry_at=leitura - timedelta(minutes=10))
    fechada_depois = replace(fechada_depois, exit_at=leitura + timedelta(seconds=1))
    vista = na_leitura(fechada_depois, leitura)
    assert vista is not None
    assert vista.status == "open"
    assert vista.pnl_sol is None
    assert vista.exit_reason is None
    assert na_leitura(aposta(0.3, entry_at=leitura + timedelta(seconds=1)), leitura) is None
    antes = aposta(0.3, entry_at=leitura - timedelta(minutes=10))
    assert na_leitura(antes, leitura) == antes


# ------------------------------------------------------------------ motivo único


def test_ordem_fidelity_e_u_i_f_c_a() -> None:
    assert motivo(oportunidade()) == ("A", "avaliavel")
    assert motivo(oportunidade(fidelity="eligible_before_lane")) == (
        "I",
        "fidelity:eligible_before_lane",
    )
    serial = oportunidade(
        proposal_refusals=("creator_serial", "pedigree_unknown"),
        proposal_id=None,
        no_proposal_reason="refused",
        aposta_=None,
    )
    assert motivo(serial) == ("E", "exclusao:creator_serial")
    assert motivo(replace(serial, line_reason="too_few_points"))[0] == "E"
    assert motivo(oportunidade(classe="unknown")) == ("U", "linha:too_few_points")


def test_pedigree_desconhecido_e_instrumento_nao_exclusao() -> None:
    """r4 must-fix 1: `pedigree_unknown` sem recusa substantiva é sem_proposta."""
    for nome in ("pedigree_unknown", "creator_unknown", "symbol_unknown", "no_snapshot_for_quote"):
        o = oportunidade(
            proposal_refusals=(nome,), proposal_id=None, no_proposal_reason="refused", aposta_=None
        )
        assert motivo(o) == ("I", f"sem_proposta:refused:{nome}")
    falhou = oportunidade(proposal_id=None, no_proposal_reason="insert_failed", aposta_=None)
    assert motivo(falhou) == ("I", "sem_proposta:insert_failed:")


def test_sem_fill_e_c_separados() -> None:
    sem_fill = oportunidade(aposta_=None, proposal_status="unfilled", proposal_refusal="x")
    assert motivo(sem_fill) == ("F", "sem_fill:unfilled:x")
    inativo = oportunidade(
        aposta_=None, proposal_status="unfilled", proposal_refusal="rule_set_inactive"
    )
    assert motivo(inativo)[0] == "F"
    assert motivo(oportunidade(y=None)) == ("C", "aberta_na_leitura")
    indet = oportunidade(aposta_=aposta(-1.0, outcome_quality="indeterminate"))
    assert motivo(indet) == ("C", "indeterminate")


def test_venda_sem_praca_pelo_estado_da_foto_qualquer_gatilho() -> None:
    """r2 5d: alvo em T, a curva completa antes da foto seguinte; a venda sai com
    motivo `target` — continua censura."""
    completa = oportunidade(aposta_=aposta(0.15, sale_complete=True))
    assert motivo(completa) == ("C", "venda_sem_praca:complete")
    a = aposta(0.15)
    assert a.sale_observed_at is not None
    migrou = oportunidade(aposta_=replace(a, token_migrated_at=a.sale_observed_at))
    assert motivo(migrou) == ("C", "venda_sem_praca:migrated_at")
    concluiu = oportunidade(
        aposta_=replace(a, token_completed_at=a.sale_observed_at - timedelta(seconds=1))
    )
    assert motivo(concluiu) == ("C", "venda_sem_praca:completed_at")
    depois = oportunidade(
        aposta_=replace(a, token_migrated_at=a.sale_observed_at + timedelta(seconds=1))
    )
    assert motivo(depois) == ("A", "avaliavel")
