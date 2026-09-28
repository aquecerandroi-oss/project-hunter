"""O export (`export_h022.sql`, uma linha JSON por registro) vira `Entrada` — puro.

Decimais do JSON entram como `Decimal` (`parse_float=Decimal`), nunca `float`; tempo sem
fuso é recusado. O seed é o `created_at` de C, e os três braços têm de ser do mesmo seed
(a mesma migração `0068`): senão o export não é o do experimento.

O estado do token (`completed_at`/`migrated_at`) **não** vem da oportunidade: vem da linha
`estado_token` do mint (o histórico, `0067`), exatamente uma por mint com oportunidade, e é
resolvido em L pela leitura (`estado_token.em`). A aposta sai daqui `nao_resolvido`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from infra.research.exp_m26.constantes import BRACOS, RULE_SET_C
from infra.research.exp_m26.estado_token import EstadoToken, de_registro, prova_de_registro
from infra.research.exp_m26.leitura import Entrada
from infra.research.exp_m26.modelo import Aposta, Oportunidade

_MESMO_SEED = timedelta(minutes=1)


def _dt(v: Any, campo: str) -> datetime:
    if not isinstance(v, str):
        raise ValueError(f"{campo}: esperado instante ISO, veio {v!r}")
    t = datetime.fromisoformat(v)
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError(f"{campo}: instante sem fuso ({v}); o moinho só lê UTC aware")
    return t


def _dt_opt(v: Any, campo: str) -> datetime | None:
    return None if v is None else _dt(v, campo)


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _aposta(r: Mapping[str, Any], size_sol: Decimal) -> Aposta | None:
    if r.get("bet_id") is None:
        return None
    spent = _dec(r["sol_spent"])
    if spent is None:
        raise ValueError(f"aposta {r['bet_id']}: sem sol_spent")
    return Aposta(
        entry_at=_dt(r["entry_at"], "entry_at"),
        fill_observed_at=_dt(r["fill_observed_at"], "fill_observed_at"),
        fill_source=str(r["fill_source"]),
        sol_spent=spent,
        size_sol=size_sol,
        status=str(r["bet_status"]),
        exit_at=_dt_opt(r.get("exit_at"), "exit_at"),
        exit_reason=r.get("exit_reason"),
        pnl_sol=_dec(r.get("pnl_sol")),
        outcome_quality=str(r["outcome_quality"]),
        sale_observed_at=_dt_opt(r.get("sale_observed_at"), "sale_observed_at"),
        sale_complete=r.get("sale_complete"),
        token_completed_at=None,
        token_migrated_at=None,
        high_water_x=_dec(r.get("high_water_x")),
        fee_buy_sol=_dec(r.get("fee_buy_sol")),
        fee_sell_sol=_dec(r.get("fee_sell_sol")),
        curve_proceeds_sol=_dec(r.get("curve_proceeds_sol")),
        token_estado_via="nao_resolvido",  # noqa: S106 - a label, not a secret
    )


def _oportunidade(r: Mapping[str, Any], size_sol: Decimal) -> Oportunidade:
    return Oportunidade(
        rule_set_id=str(r["rule_set_id"]),
        mint=str(r["mint"]),
        evaluated_at=_dt(r["evaluated_at"], "evaluated_at"),
        features_end_time=_dt(r["features_end_time"], "features_end_time"),
        features_computed_at=_dt_opt(r.get("features_computed_at"), "features_computed_at"),
        fidelity=str(r["fidelity"]),
        coverage_status=str(r["coverage_status"]),
        line_reason=r.get("line_reason"),
        higher_lows=r.get("higher_lows"),
        breakout_15m=r.get("breakout_15m"),
        distance_to_support_pct=_dec(r.get("distance_to_support_pct")),
        mcap_slope_15m=_dec(r.get("mcap_slope_15m")),
        curve_progress_pct=_dec(r.get("curve_progress_pct")),
        proposal_refusals=tuple(r.get("proposal_refusals") or ()),
        no_proposal_reason=r.get("no_proposal_reason"),
        proposal_id=None if r.get("proposal_id") is None else str(r["proposal_id"]),
        proposal_status=r.get("proposal_status"),
        proposal_refusal=r.get("proposal_refusal"),
        aposta=_aposta(r, size_sol),
        prior_other_bet=bool(r.get("prior_other_bet")),
    )


def ler_export(linhas: Iterable[str]) -> Entrada:
    registros = [json.loads(x, parse_float=Decimal) for x in linhas if x.strip()]
    metas = [r for r in registros if r.get("tipo") == "meta"]
    if len(metas) != 1:
        raise ValueError(f"export com {len(metas)} linhas 'meta': falta exportado_em único")
    bracos = {r["rule_set_id"]: r for r in registros if r.get("tipo") == "braco"}
    if set(bracos) != set(BRACOS):
        raise ValueError(f"export sem os três braços do EXP-M26 (veio {sorted(bracos)})")
    criados = {rs: _dt(b["created_at"], "created_at") for rs, b in bracos.items()}
    seed = criados[RULE_SET_C]
    if any(abs(t - seed) > _MESMO_SEED for t in criados.values()):
        raise ValueError(f"os três braços não são do mesmo seed: {criados}")
    tamanhos = {rs: Decimal(str(b["size_sol"])) for rs, b in bracos.items()}
    ops: list[Oportunidade] = []
    props: list[tuple[str, str, datetime]] = []
    estados: dict[str, EstadoToken] = {}
    for r in registros:
        tipo = r.get("tipo")
        if tipo == "oportunidade":
            ops.append(_oportunidade(r, tamanhos[str(r["rule_set_id"])]))
        elif tipo == "proposta":
            props.append(
                (str(r["rule_set_id"]), str(r["mint"]), _dt(r["proposed_at"], "proposed_at"))
            )
        elif tipo == "estado_token":
            s = de_registro(r)
            if s.mint in estados:
                raise ValueError(f"estado_token duplicado para {s.mint}")
            estados[s.mint] = s
        elif tipo not in ("braco", "meta"):
            raise ValueError(f"linha de tipo desconhecido no export: {tipo!r}")
    faltam = sorted({o.mint for o in ops} - set(estados))
    if faltam:
        raise ValueError(f"export sem estado_token para {len(faltam)} mints: {faltam[:5]}")
    return Entrada(
        seed=seed,
        exportado_em=_dt(metas[0]["exportado_em"], "exportado_em"),
        oportunidades=tuple(ops),
        propostas=tuple(props),
        aposentadorias={rs: _dt_opt(b.get("retired_at"), "retired_at") for rs, b in bracos.items()},
        estados=estados,
        prova=prova_de_registro(metas[0]),
    )
