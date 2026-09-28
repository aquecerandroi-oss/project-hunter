"""O parser do export (`export_h022.sql` → JSON por linha → `Entrada`), com linhas
SINTÉTICAS escritas à mão no formato que `json_build_object` produz."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from infra.research.exp_m26.carga import ler_export
from infra.research.exp_m26.constantes import BRACOS, RULE_SET_C, RULE_SET_L
from infra.research.exp_m26.estado_token import ProvaDeVisibilidade

_SQL = Path(__file__).resolve().parents[1] / "export_h022.sql"


def _braco(rs: str, **kw: Any) -> str:
    return json.dumps(
        {
            "tipo": "braco",
            "rule_set_id": rs,
            "created_at": "2026-09-29T12:00:00+00:00",
            "retired_at": None,
            "size_sol": "0.07",
            **kw,
        }
    )


def op_export(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tipo": "oportunidade",
        "rule_set_id": RULE_SET_C,
        "mint": "Mint1pump",
        "evaluated_at": "2026-10-01T10:01:02.5+00:00",
        "features_end_time": "2026-10-01T10:01:00+00:00",
        "features_computed_at": "2026-10-01T10:01:00.8+00:00",
        "fidelity": "faithful",
        "coverage_status": "covered",
        "line_reason": None,
        "higher_lows": True,
        "breakout_15m": True,
        "distance_to_support_pct": 0.123456,
        "mcap_slope_15m": -0.5,
        "curve_progress_pct": 0.4321,
        "proposal_refusals": [],
        "no_proposal_reason": None,
        "proposal_id": "p1",
        "proposal_status": "filled",
        "proposal_refusal": None,
        "prior_other_bet": False,
        "bet_id": "b1",
        "entry_at": "2026-10-01T10:01:30+00:00",
        "fill_observed_at": "2026-10-01T10:01:30+00:00",
        "fill_source": "chain",
        "sol_spent": "0.0700000000",
        "bet_status": "closed",
        "exit_at": "2026-10-01T10:06:30+00:00",
        "exit_reason": "target",
        "pnl_sol": 0.0105000001,
        "outcome_quality": "measured",
        "sale_observed_at": "2026-10-01T10:06:30+00:00",
        "sale_complete": False,
        "high_water_x": 1.2,
        "fee_buy_sol": "0.001225",
        "fee_sell_sol": "0.0014",
        "curve_proceeds_sol": "0.08",
    }
    return {**base, **kw}


META = json.dumps({"tipo": "meta", "exportado_em": "2026-11-01T02:10:00.123+00:00"})


def estado_export(mint: str = "Mint1pump", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tipo": "estado_token",
        "mint": mint,
        "token_existe": True,
        "completed_at_atual": None,
        "migrated_at_atual": None,
        "historico": [],
    }
    return {**base, **kw}


def linhas_export(
    *ops: dict[str, Any], meta: str = META, estados: list[dict[str, Any]] | None = None
) -> list[str]:
    if estados is None:
        estados = [estado_export(m) for m in sorted({str(o["mint"]) for o in ops})]
    return [
        meta,
        *(_braco(rs) for rs in BRACOS),
        *(json.dumps(o) for o in ops),
        *(json.dumps(s) for s in estados),
        json.dumps(
            {
                "tipo": "proposta",
                "rule_set_id": RULE_SET_L,
                "mint": "Orfa",
                "proposed_at": "2026-10-02T00:00:00+00:00",
            }
        ),
    ]


def test_parse_preserva_decimal_e_utc() -> None:
    e = ler_export(linhas_export(op_export()))
    assert e.seed == datetime(2026, 9, 29, 12, tzinfo=UTC)
    assert e.exportado_em == datetime(2026, 11, 1, 2, 10, 0, 123000, tzinfo=UTC)
    (o,) = e.oportunidades
    assert o.distance_to_support_pct == Decimal("0.123456")
    assert o.aposta is not None
    assert o.aposta.pnl_sol == Decimal("0.0105000001")
    assert o.aposta.size_sol == Decimal("0.07")
    assert o.aposta.sol_spent == Decimal("0.0700000000")
    assert o.evaluated_at.tzinfo is not None
    assert e.propostas == ((RULE_SET_L, "Orfa", datetime(2026, 10, 2, tzinfo=UTC)),)
    assert dict(e.aposentadorias) == dict.fromkeys(BRACOS)


def test_sem_aposta_e_recusas() -> None:
    op = op_export(
        bet_id=None,
        proposal_id=None,
        proposal_status=None,
        no_proposal_reason="refused",
        proposal_refusals=["pedigree_unknown", "creator_serial"],
    )
    (o,) = ler_export(linhas_export(op)).oportunidades
    assert o.aposta is None
    assert o.proposal_refusals == ("pedigree_unknown", "creator_serial")


def test_tempo_sem_fuso_e_recusado() -> None:
    with pytest.raises(ValueError, match="fuso"):
        ler_export(linhas_export(op_export(evaluated_at="2026-10-01T10:01:02")))


def test_export_incompleto_ou_estranho_e_recusado() -> None:
    with pytest.raises(ValueError, match="braço"):
        ler_export([META, json.dumps(op_export())])
    with pytest.raises(ValueError, match="tipo"):
        ler_export([*linhas_export(), json.dumps({"tipo": "outro"})])


def test_export_sem_o_seu_instante_e_recusado() -> None:
    with pytest.raises(ValueError, match="exportado_em"):
        ler_export(linhas_export()[1:])
    with pytest.raises(ValueError, match="exportado_em"):
        ler_export([META, *linhas_export()])


def test_estado_do_token_vem_do_historico_e_nunca_da_linha_da_oportunidade() -> None:
    """O export não traz mais `completed_at`/`migrated_at` correntes na oportunidade: o
    estado é o histórico por mint (`estado_token`), resolvido em L pela leitura. Uma linha
    velha que ainda os traga é ignorada; a aposta sai da carga sem estado resolvido."""
    hist = [
        {
            "id": 3,
            "coluna": "completed_at",
            "antes": None,
            "depois": "2026-10-01T10:05:00+00:00",
            "registrado_em": "2026-10-01T10:05:01+00:00",
        }
    ]
    linhas = linhas_export(
        op_export(token_completed_at="2026-10-01T09:00:00+00:00"),
        estados=[estado_export(historico=hist, completed_at_atual="2026-10-01T10:05:00+00:00")],
    )
    e = ler_export(linhas)
    (o,) = e.oportunidades
    assert o.aposta is not None
    assert (o.aposta.token_completed_at, o.aposta.token_estado_via) == (None, "nao_resolvido")
    (m,) = e.estados["Mint1pump"].historico
    assert (m.id, m.coluna, m.depois) == (
        3,
        "completed_at",
        datetime(2026, 10, 1, 10, 5, tzinfo=UTC),
    )


def test_a_prova_de_visibilidade_vem_da_linha_meta() -> None:
    """Sem os campos, a prova é a que recusa (`ve_toda_atividade` falso); com eles, lidos
    como vieram — inteiros, `Decimal`, instante com fuso."""
    assert ler_export(linhas_export(op_export())).prova == ProvaDeVisibilidade()
    meta = json.dumps(
        {
            "tipo": "meta",
            "exportado_em": "2026-11-01T02:10:00.123+00:00",
            "escritoras_abertas_desde": "2026-11-01T02:09:59+00:00",
            "escritoras_sem_inicio": 2,
            "preparadas": 1,
            "relogio_recuou_s": -0.000021,
            "ve_toda_atividade": True,
        }
    )
    prova = ler_export(linhas_export(op_export(), meta=meta)).prova
    assert prova == ProvaDeVisibilidade(
        escritoras_abertas_desde=datetime(2026, 11, 1, 2, 9, 59, tzinfo=UTC),
        escritoras_sem_inicio=2,
        preparadas=1,
        relogio_recuou_s=Decimal("-0.000021"),
        ve_toda_atividade=True,
    )


def test_oportunidade_sem_estado_ou_estado_duplicado_e_recusado() -> None:
    with pytest.raises(ValueError, match="estado_token"):
        ler_export(linhas_export(op_export(), estados=[]))
    with pytest.raises(ValueError, match="estado_token"):
        ler_export(linhas_export(op_export(), estados=[estado_export(), estado_export()]))


def test_seed_e_o_created_at_de_c_e_os_tres_sao_do_mesmo_seed() -> None:
    linhas = linhas_export()
    linhas[2] = _braco(BRACOS[1], created_at="2026-09-30T12:00:00+00:00")
    with pytest.raises(ValueError, match="seed"):
        ler_export(linhas)


def test_o_sql_e_so_leitura_e_cobre_os_tres_bracos() -> None:
    sql = _SQL.read_text(encoding="utf-8")
    corpo = "\n".join(x for x in sql.splitlines() if not x.lstrip().startswith("--")).lower()
    for proibido in ("insert", "update", "delete", "drop", "alter", "create", "truncate"):
        assert f"{proibido} " not in corpo
    for rs in BRACOS:
        assert rs in sql
    for chave in (
        "'meta'",
        "now()",
        "'oportunidade'",
        "'proposta'",
        "'braco'",
        "'estado_token'",
        "meme_token_state_history",
        "escritoras_abertas_desde",
        "escritoras_sem_inicio",
        "pg_prepared_xacts",
        "relogio_recuou_s",
        "'USAGE'",
        "pg_stat_activity",
        "default_transaction_read_only",
    ):
        assert chave in sql
    assert "'token_completed_at'" not in sql, "o estado corrente não entra na oportunidade"
    assert "'token_migrated_at'" not in sql, "o estado corrente não entra na oportunidade"
