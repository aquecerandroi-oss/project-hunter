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
) -> Entrada:
    propostas = tuple(
        (o.rule_set_id, o.mint, o.evaluated_at) for o in ops if o.proposal_id is not None
    )
    return Entrada(
        seed=SEED,
        exportado_em=exportado_em,
        oportunidades=tuple(ops),
        propostas=propostas,
        aposentadorias=aposentadorias or {},
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
