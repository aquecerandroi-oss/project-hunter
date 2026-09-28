"""`ler_h022` de ponta a ponta sobre populações SINTÉTICAS com resposta conhecida.

Cobre: CONFIRMA só com toda a previsão; REFUTA de efeito nulo estreito; estresse que
derruba (r3 b); parada pela guarda (r3 5); limite de dado; piloto fora para sempre (r3 5);
o export é o retrato em L = corte + 2 h, tirado em [L, L + 1 h] (revisão do J, must-fix 2);
a trapaça de antecipação levanta nos três braços (must-fix 3); a ordem do export não muda
nada (must-fix 4); a linha de L nunca muda a classe de C (r2 F); proposta de C sem R1
conta em `desconhecida`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from infra.research.exp_m26.calendario import LeituraAntecipada
from infra.research.exp_m26.constantes import RULE_SET_C, RULE_SET_H, RULE_SET_L
from infra.research.exp_m26.estado_token import (
    EstadoToken,
    ExportSemProvaDeVisibilidade,
    Mudanca,
    ProvaDeVisibilidade,
)
from infra.research.exp_m26.leitura import Entrada, ExportForaDaJanela, ler_h022
from infra.research.exp_m26.modelo import Oportunidade
from infra.research.exp_m26.tests.fabrica import aposta, oportunidade
from infra.research.guards import LookAheadError
from infra.research.verdict import CONFIRMA, NAO_CONFIRMA, REFUTA

SEED = datetime(2026, 9, 29, tzinfo=UTC)
T0 = SEED + timedelta(hours=48)
CORTE = datetime(2026, 10, 8, tzinfo=UTC)
LEITURA = CORTE + timedelta(hours=2)
EXPORT = LEITURA + timedelta(minutes=30)
REPS = 300


def _pop(
    y_true: float,
    y_false: float,
    *,
    n_true: int = 6,
    n_false: int = 17,
    ruido: float = 0.02,
    cens_true: int = 0,
    dh: float = 0.05,
) -> list[Oportunidade]:
    out: list[Oportunidade] = []
    i = 0
    for b in range(28):
        base = T0 + timedelta(hours=6 * b, minutes=10)
        for k in range(n_true + n_false + cens_true):
            i += 1
            at = base + timedelta(seconds=10 * k)
            classe = "true" if k < n_true + cens_true else "false"
            y = (y_true if classe == "true" else y_false) + ruido * (((i * 7) % 5) - 2) / 2
            kw = {
                "curve_progress_pct": Decimal(str(round(0.05 + 0.85 * ((i * 37) % 100) / 100, 4))),
                "mcap_slope_15m": Decimal("0.2") if i % 2 else Decimal("-0.2"),
                "aposta_": aposta(
                    None if k < cens_true else y, entry_at=at + timedelta(seconds=20)
                ),
            }
            o = oportunidade(f"m{i}", at=at, classe=classe, y=y, **kw)  # type: ignore[arg-type]
            out.append(o)
            if classe == "true" and k >= cens_true:
                assert o.aposta is not None
                out.append(replace(o, rule_set_id=RULE_SET_L, proposal_id=f"l{i}"))
                h = aposta(y + dh, entry_at=o.aposta.entry_at)
                out.append(replace(o, rule_set_id=RULE_SET_H, proposal_id=f"h{i}", aposta=h))
    return out


def _entrada(
    ops: list[Oportunidade],
    aposentadorias: dict[str, datetime | None] | None = None,
    exportado_em: datetime = EXPORT,
    estados: dict[str, EstadoToken] | None = None,
) -> Entrada:
    propostas = tuple(
        (o.rule_set_id, o.mint, o.evaluated_at) for o in ops if o.proposal_id is not None
    )
    nunca_concluiu = {o.mint: EstadoToken(o.mint, True, None, None, ()) for o in ops}
    return Entrada(
        seed=SEED,
        exportado_em=exportado_em,
        oportunidades=tuple(ops),
        propostas=propostas,
        aposentadorias=aposentadorias or {},
        estados={**nunca_concluiu, **(estados or {})},
        prova=ProvaDeVisibilidade(ve_toda_atividade=True),
    )


def test_confirma_quando_toda_a_previsao_bate() -> None:
    r = ler_h022(_entrada(_pop(0.12, 0.0)), reps=REPS)
    p = r["primaria"]
    assert r["corte"]["instante"] == CORTE.isoformat()
    assert r["leitura"] == LEITURA.isoformat()
    assert (p["estratos"], p["n_true"], p["n_false"]) == (28, 168, 476)
    assert p["d"] == pytest.approx(0.12, abs=0.01)
    assert p["rotulo"] == CONFIRMA, p["motivos"]
    assert r["rotulo_h022"] == CONFIRMA
    s = r["secundaria"]
    assert s["d"] == pytest.approx(0.05)
    assert s["rotulo"] == CONFIRMA, s["motivos"]


def test_refuta_um_efeito_nulo_estreito() -> None:
    r = ler_h022(_entrada(_pop(0.0, 0.0, ruido=0.01, dh=0.0)), reps=REPS)
    assert r["primaria"]["rotulo"] == REFUTA
    assert r["secundaria"]["rotulo"] == REFUTA


def test_estresse_de_perda_integral_derruba_o_rotulo() -> None:
    r = ler_h022(_entrada(_pop(0.10, 0.0, cens_true=1)), reps=REPS)
    p = r["primaria"]
    assert r["denominadores"]["true"]["C"] == 28
    assert p["d"] == pytest.approx(0.10, abs=0.01)
    assert p["estresse"]["d"] < 0
    assert p["rotulo"] == NAO_CONFIRMA
    assert any("estresse" in m for m in p["motivos"])
    assert p["diagnosticos"]["inversao_d0"] is not None


def test_parada_pela_guarda_e_instrumento_qualquer_que_seja_o_n() -> None:
    parada = T0 + timedelta(days=3)
    e = _entrada(
        _pop(0.12, 0.0),
        aposentadorias={RULE_SET_H: parada},
        exportado_em=parada + timedelta(hours=2, minutes=5),
    )
    r = ler_h022(e, reps=REPS)
    assert r["corte"]["motivo"] == "parada_guarda"
    assert r["primaria"]["rotulo"] == NAO_CONFIRMA
    assert r["primaria"]["categoria"] == "instrumento"
    assert r["secundaria"]["categoria"] == "instrumento"


def test_limite_de_dado() -> None:
    fim = datetime(2026, 10, 22, 2, 10, tzinfo=UTC)
    r = ler_h022(_entrada(_pop(0.12, 0.0, n_true=3), exportado_em=fim), reps=REPS)
    assert r["corte"]["motivo"] == "dia_21"
    assert (r["primaria"]["rotulo"], r["primaria"]["categoria"]) == (NAO_CONFIRMA, "limite_de_dado")


def test_piloto_fora_para_sempre() -> None:
    ops = _pop(0.12, 0.0)
    antes = oportunidade("piloto", at=T0 - timedelta(hours=1), y=5.0)
    depois = replace(
        oportunidade("piloto", at=T0 + timedelta(hours=2), y=5.0), rule_set_id=RULE_SET_L
    )
    h = replace(depois, rule_set_id=RULE_SET_H)
    r = ler_h022(_entrada([*ops, antes, depois, h]), reps=REPS)
    base = ler_h022(_entrada(ops), reps=REPS)
    assert r["funil"]["mints_do_piloto"] == 1
    assert r["primaria"]["d"] == base["primaria"]["d"]
    assert r["secundaria"]["comuns"] == base["secundaria"]["comuns"]


def test_o_export_e_o_retrato_em_l() -> None:
    """Fechou depois de L (mas antes do export): na leitura estava aberta — C."""
    ops = _pop(0.12, 0.0)
    alvo = next(o for o in ops if o.rule_set_id == RULE_SET_C and o.mint == "m1")
    assert alvo.aposta is not None
    tarde = replace(
        alvo.aposta,
        exit_at=LEITURA + timedelta(minutes=20),
        sale_observed_at=LEITURA + timedelta(minutes=20),
    )
    ops = [replace(o, aposta=tarde) if o is alvo else o for o in ops]
    r = ler_h022(_entrada(ops), reps=REPS)
    assert r["denominadores"]["true"]["C"] == 1
    assert r["exportado_em"] == EXPORT.isoformat()


def _conclusao_retroativa(
    ops: list[Oportunidade], registrada_em: datetime
) -> dict[str, EstadoToken]:
    """Toda venda `true` de C ganha um `completed_at` anterior à venda, registrado em
    `registrada_em` (o `gd` retrospectivo do indexador, escrito por `LEAST`)."""
    out: dict[str, EstadoToken] = {}
    for o in ops:
        a = o.aposta
        if o.rule_set_id != RULE_SET_C or o.breakout_15m is not True or a is None:
            continue
        if a.sale_observed_at is None:
            continue
        antes = a.sale_observed_at - timedelta(minutes=1)
        mud = Mudanca(1, "completed_at", None, antes, registrada_em)
        out[o.mint] = EstadoToken(o.mint, True, antes, None, (mud,))
    return out


def test_conclusao_registrada_depois_de_l_nao_muda_a_leitura_de_l() -> None:
    """Must-fix 2 (Astra, J rodada 2), dentro da janela aceita: em L as vendas `true`
    são avaliáveis; em L + 10 min chega uma conclusão anterior a elas; o export sai em
    L + 30 min. A leitura de L é a mesma, byte a byte. Registrada ANTES de L, a mesma
    conclusão censura as vendas (controle: o mecanismo de censura continua vivo)."""
    ops = _pop(0.12, 0.0)
    limpo = ler_h022(_entrada(ops), reps=REPS)
    tarde = _conclusao_retroativa(ops, LEITURA + timedelta(minutes=10))
    assert len(tarde) == 168
    assert ler_h022(_entrada(ops, estados=tarde), reps=REPS) == limpo
    assert limpo["rotulo_h022"] == CONFIRMA
    cedo = _conclusao_retroativa(ops, LEITURA - timedelta(minutes=10))
    r = ler_h022(_entrada(ops, estados=cedo), reps=REPS)
    assert r["denominadores"]["true"]["C"] == 168
    assert r["funil"]["motivos"]["C:venda_sem_praca:completed_at"] == 168
    assert r["funil"]["estado_token_via"] == {"history": 168 + 476}


def test_token_sem_estado_em_l_censura_a_venda_e_estado_ausente_no_export_e_recusado() -> None:
    ops = _pop(0.12, 0.0)
    alvo = next(o for o in ops if o.rule_set_id == RULE_SET_C and o.breakout_15m is True)
    a = alvo.aposta
    assert a is not None and a.sale_observed_at is not None
    depois_da_venda = a.sale_observed_at + timedelta(minutes=1)  # não censuraria por si
    antes = Mudanca(1, "completed_at", None, depois_da_venda, LEITURA - timedelta(hours=1))
    casos = {
        "token_ausente": EstadoToken(alvo.mint, False, None, None, ()),
        "current_row_pre_history": EstadoToken(alvo.mint, True, depois_da_venda, None, ()),
        "historico_diverge": EstadoToken(alvo.mint, True, None, None, (antes,)),
    }
    for via, estado in casos.items():
        r = ler_h022(_entrada(ops, estados={alvo.mint: estado}), reps=REPS)
        assert r["funil"]["motivos"][f"C:estado_do_token_desconhecido:{via}"] == 1, via
        assert r["funil"]["estado_token_via"][via] == 1, via
    e = _entrada(ops)
    sem = replace(e, estados={k: v for k, v in e.estados.items() if k != alvo.mint})
    with pytest.raises(ValueError, match="estado_token"):
        ler_h022(sem, reps=REPS)


def test_export_sem_prova_de_visibilidade_em_l_e_recusado() -> None:
    """Astra (J rodada 4): uma transação que carimbou antes de L e ainda não estava visível
    quando o export começou faria dois exports da janela lerem L diferente. O export que não
    prova visibilidade é recusado; o seguinte, depois do commit, é o único aceito."""
    ops = _pop(0.12, 0.0)
    ok = ProvaDeVisibilidade(ve_toda_atividade=True)
    for prova in (
        replace(ok, escritoras_abertas_desde=LEITURA - timedelta(seconds=1)),
        replace(ok, escritoras_sem_inicio=1),
        replace(ok, ve_toda_atividade=False),
    ):
        with pytest.raises(ExportSemProvaDeVisibilidade):
            ler_h022(replace(_entrada(ops), prova=prova), reps=REPS)
    depois = replace(ok, escritoras_abertas_desde=LEITURA + timedelta(seconds=1))
    assert ler_h022(replace(_entrada(ops), prova=depois), reps=REPS)["rotulo_h022"] == CONFIRMA


def test_export_fora_da_janela_e_recusado() -> None:
    """Um export tirado horas depois de L pode trazer o que só chegou depois de L
    (`completed_at` recuado por LEAST, fechamento processado com `exit_at` antigo)."""
    ops = _pop(0.12, 0.0)
    with pytest.raises(ExportForaDaJanela):
        ler_h022(_entrada(ops, exportado_em=LEITURA + timedelta(hours=1, seconds=1)), reps=REPS)
    with pytest.raises(LeituraAntecipada):
        ler_h022(_entrada(ops, exportado_em=LEITURA - timedelta(seconds=1)), reps=REPS)
    assert ler_h022(_entrada(ops, exportado_em=LEITURA), reps=REPS)["rotulo_h022"] == CONFIRMA


def test_trapaca_de_antecipacao_e_pega_em_c() -> None:
    ops = _pop(0.12, 0.0)
    trapaca = replace(ops[0], features_computed_at=ops[0].evaluated_at + timedelta(minutes=3))
    with pytest.raises(LookAheadError):
        ler_h022(_entrada([trapaca, *ops[1:]]), reps=REPS)


def test_trapaca_de_antecipacao_e_pega_em_l_e_h() -> None:
    """Must-fix 3: C limpo, pernas L/H com a feature dobrada 1 h depois do tique. A
    igualdade de dois minutos futuros não torna o par causal."""
    ops = [
        o
        if o.rule_set_id == RULE_SET_C
        else replace(o, features_computed_at=o.evaluated_at + timedelta(hours=1))
        for o in _pop(0.12, 0.0)
    ]
    with pytest.raises(LookAheadError):
        ler_h022(_entrada(ops), reps=REPS)


def test_a_ordem_do_export_nao_muda_nada() -> None:
    """Must-fix 4: mesma população, mesma semente, qualquer ordem ⇒ o mesmo relatório."""
    ops = _pop(0.03, 0.0, ruido=0.2)
    assert ler_h022(_entrada(ops), reps=REPS) == ler_h022(_entrada(ops[::-1]), reps=REPS)


def test_linha_de_l_nunca_muda_a_classe_de_c() -> None:
    ops = _pop(0.12, 0.0)
    falso = next(
        o
        for o in ops
        if o.rule_set_id == RULE_SET_C and o.line_reason is None and o.breakout_15m is False
    )
    l_true = replace(
        falso,
        rule_set_id=RULE_SET_L,
        breakout_15m=True,
        evaluated_at=falso.evaluated_at + timedelta(minutes=30),
        features_end_time=falso.features_end_time + timedelta(minutes=30),
        features_computed_at=falso.evaluated_at + timedelta(minutes=29),
    )
    com = ler_h022(_entrada([*ops, l_true]), reps=REPS)
    sem = ler_h022(_entrada(ops), reps=REPS)
    assert com["denominadores"]["false"] == sem["denominadores"]["false"]
    assert com["primaria"]["d"] == sem["primaria"]["d"]


def test_proposta_de_c_sem_registro_conta_em_desconhecida() -> None:
    ops = _pop(0.12, 0.0)
    e = _entrada(ops)
    e = replace(e, propostas=(*e.propostas, (RULE_SET_C, "orfa", T0 + timedelta(hours=3))))
    r = ler_h022(e, reps=REPS)
    assert r["denominadores"]["orfas_c"] == 1
    assert r["denominadores"]["U"] == 1
