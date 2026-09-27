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
        "token_completed_at": None,
        "token_migrated_at": None,
        "high_water_x": 1.2,
        "fee_buy_sol": "0.001225",
        "fee_sell_sol": "0.0014",
        "curve_proceeds_sol": "0.08",
    }
    return {**base, **kw}


META = json.dumps({"tipo": "meta", "exportado_em": "2026-11-01T02:10:00.123+00:00"})


def linhas_export(*ops: dict[str, Any], meta: str = META) -> list[str]:
    return [
        meta,
        *(_braco(rs) for rs in BRACOS),
        *(json.dumps(o) for o in ops),
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
        "default_transaction_read_only",
    ):
        assert chave in sql
