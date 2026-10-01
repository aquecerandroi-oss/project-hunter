"""EXP-M26 F — funil de viabilidade de 24 h (sem desfecho), desenho §4 "Funil F".

R1 só escreve para conjuntos do EXP-M26 e nenhum foi semeado: a porta pura de
``grafico_ctrl_v1/1`` (C) é avaliada FORA do Lab, com o código de R1, sobre as linhas
retidas por I1 (K = 60):

- porta pura: ``evaluate_entry(entry_features_of(row, spec), spec.gate)`` com o ``spec`` de C
  construído dos parâmetros congelados da semente (``infra/migrations/ddl/meme_mature_chart_arms``);
- 1.ª oportunidade por mint, ordenada por ``end_time`` ANTES de ver a linha;
- cobertura: ``coverage_of`` (o mesmo de R1) sobre as fotos de ``(T − 16 min, T]`` recebidas até T;
- classe: ``classe_linha`` do J (``infra/research/exp_m26/classes.py``);
- recusas da camada de propostas que C teria: pedigree (``evaluate_pedigree``, PEDIGREE_V1) e
  foto da cotação (``no_snapshot_for_quote``). E = creator_serial/symbol_clone; I = o resto.

Nenhum desfecho (aposta, PnL, saída) é lido.

    uv run --no-sync python .claude/state/m26/f/f_funil.py fase1   # escreve f2_pontos.sql
    uv run --no-sync python .claude/state/m26/f/f_funil.py fase2   # lê f2_*.csv, imprime o funil
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from hunter_indicators.meme.lines import LinePoint
from hunter_indicators.meme.pedigree import PEDIGREE_V1, PedigreeFeatures, evaluate_pedigree
from hunter_indicators.meme.rules import evaluate_entry
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_opportunities_coverage import coverage_of
from hunter_meme_worker.proposals import GateRow, entry_features_of
from infra.migrations.ddl.meme_mature_chart_arms import ARMS
from infra.research.exp_m26.classes import classe_linha
from infra.research.exp_m26.modelo import Oportunidade

AQUI = Path(__file__).resolve().parent
JANELA = (datetime(2026, 9, 28, 6, 30, tzinfo=UTC), datetime(2026, 10, 1, 0, 0, tzinfo=UTC))
"""F: [28/09 06:30Z, 01/10 00:00Z). Começa 2 h depois da 0067 (28/09 04:24:42Z): todo mint de
idade ≤ 7 200 s na janela nasceu com o histórico instalado. O superconjunto começa em 27/09
06:00Z (K = 60 no ar): um mint cuja 1.ª passagem foi antes da janela não entra nela."""


def _spec_c() -> RuleSetSpec:
    rid, name, version, body = ARMS[0]
    return RuleSetSpec.from_params(
        id=rid, name=name, version=version, kind="research_only", exp_ref="EXP-M26",
        status="active", code_ref="f", params=json.loads("{" + body + "}"),
    )


def _ts(v: str) -> datetime | None:
    return None if v == "" else datetime.fromisoformat(v).astimezone(UTC)


def _dec(v: str) -> Decimal | None:
    return None if v == "" else Decimal(v)


def _bool(v: str) -> bool | None:
    return None if v == "" else v == "t"


def _int(v: str) -> int | None:
    return None if v == "" else int(v)


def _row(r: dict[str, str]) -> GateRow:
    return GateRow(
        mint=r["mint"], end_time=_ts(r["end_time"]),  # type: ignore[arg-type]
        created_at=_ts(r["created_at"]), curve_progress_pct=_dec(r["curve_progress_pct"]),
        progress_reason=r["progress_reason"] or None, mcap_sol=_dec(r["mcap_sol"]),
        creator_sold=_bool(r["creator_net_seller"]),
        curve_volume_1m_sol=_dec(r["curve_volume_1m_sol"]),
        completed_at=_ts(r["completed_at_k"]), migrated_at=_ts(r["migrated_at_k"]), snapshot=None,
        higher_lows=_bool(r["higher_lows"]), breakout_15m=_bool(r["breakout_15m"]),
        distance_to_support_pct=_dec(r["distance_to_support_pct"]),
        line_reason=r["line_reason"] or None, mayhem_enabled=_bool(r["mayhem_enabled"]),
        mayhem_state=r["mayhem_state"] or None, computed_at=_ts(r["computed_at"]),
        line_points=_int(r["line_points"]), mcap_slope_15m=_dec(r["mcap_slope_15m"]),
    )


def fase1() -> None:
    spec = _spec_c()
    primeira: dict[str, tuple[GateRow, dict[str, str]]] = {}
    recusas: Counter[str] = Counter()
    linhas = 0
    with (AQUI / "f1_superset.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):  # já em ordem (end_time, mint)
            linhas += 1
            row = _row(r)
            if row.mint in primeira:
                continue
            decision = evaluate_entry(entry_features_of(row, spec), spec.gate)
            if decision.allowed:
                primeira[row.mint] = (row, r)
            else:
                recusas.update(decision.refusals)
    na_janela = {m: v for m, v in primeira.items() if JANELA[0] <= v[0].end_time < JANELA[1]}
    print(f"linhas do superconjunto: {linhas}; mints com 1.a passagem desde 27/09 06:00Z: "
          f"{len(primeira)}; com a 1.a na janela F: {len(na_janela)}")
    print("recusas da porta pura nas linhas do superconjunto (antes da 1.a passagem):",
          dict(recusas.most_common()))
    (AQUI / "f1_primeiras.json").write_text(
        json.dumps({m: v[1] for m, v in sorted(na_janela.items())}, indent=0), encoding="utf-8"
    )
    pares = ",\n".join(
        f"  ('{m}', TIMESTAMPTZ '{v[0].end_time.isoformat()}')" for m, v in sorted(na_janela.items())
    )
    sql = (AQUI / "f2_modelo.sql").read_text(encoding="utf-8").replace("--PARES--", pares)
    (AQUI / "f2_pontos.sql").write_text(sql, encoding="utf-8")


def _pontos() -> dict[str, list[LinePoint]]:
    out: dict[str, list[LinePoint]] = defaultdict(list)
    with (AQUI / "f2_pontos.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["tipo"] != "ponto":
                continue
            out[r["mint"]].append(LinePoint(
                observed_at=_ts(r["observed_at"]), received_at=_ts(r["received_at"]),  # type: ignore[arg-type]
                mcap_sol=_dec(r["mcap_sol"]),
            ))
    return out


def _pedigree() -> dict[str, PedigreeFeatures]:
    out: dict[str, PedigreeFeatures] = {}
    with (AQUI / "f2_pontos.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["tipo"] == "pedigree":
                out[r["mint"]] = PedigreeFeatures(
                    creator_prior_mints_1h=_int(r["creator_prior_mints_1h"]),
                    symbol_dup_24h=_int(r["symbol_dup_24h"]),
                )
    return out


def _dia(t: datetime) -> str:
    return t.date().isoformat()


def fase2() -> None:
    primeiras = json.loads((AQUI / "f1_primeiras.json").read_text(encoding="utf-8"))
    pontos, pedigree = _pontos(), _pedigree()
    por_dia: dict[str, Counter[str]] = defaultdict(Counter)
    detalhes: Counter[str] = Counter()
    recusas_nome: Counter[str] = Counter()
    vias: Counter[str] = Counter()
    atraso: list[float] = []
    for mint, r in primeiras.items():
        row = _row(r)
        t = row.end_time
        status, _ = coverage_of(pontos.get(mint, []), end_time=t, created_at=row.created_at)
        evaluated = max(t + timedelta(seconds=60), row.computed_at or t)
        o = Oportunidade(
            rule_set_id=ARMS[0][0], mint=mint, evaluated_at=evaluated, features_end_time=t,
            features_computed_at=row.computed_at, fidelity="faithful", coverage_status=status,
            line_reason=row.line_reason, higher_lows=row.higher_lows,
            breakout_15m=row.breakout_15m, distance_to_support_pct=row.distance_to_support_pct,
            mcap_slope_15m=row.mcap_slope_15m, curve_progress_pct=row.curve_progress_pct,
            proposal_refusals=(), no_proposal_reason=None, proposal_id=None,
            proposal_status=None, proposal_refusal=None, aposta=None, prior_other_bet=False,
        )
        classe, det = classe_linha(o)
        lineage = pedigree.get(mint)
        refus = ("pedigree_unknown",) if lineage is None else evaluate_pedigree(lineage, PEDIGREE_V1)
        if r["snapshot_ok"] != "t":
            refus += ("no_snapshot_for_quote",)
        recusas_nome.update(refus)
        vias[r["via"]] += 1
        if row.computed_at is not None:
            atraso.append((row.computed_at - t).total_seconds())
        d = _dia(t)
        por_dia[d]["oportunidades"] += 1
        if "creator_serial" in refus or "symbol_clone" in refus:
            por_dia[d]["E"] += 1
            continue
        por_dia[d]["nao_E"] += 1
        por_dia[d][classe] += 1
        detalhes[f"{classe}:{det}"] += 1
        if classe == "desconhecida":
            por_dia[d]["U"] += 1
        elif refus:
            por_dia[d]["I"] += 1
            por_dia[d][f"I_{classe}"] += 1
    total: Counter[str] = Counter()
    for d in sorted(por_dia):
        total.update(por_dia[d])
        print(d, dict(sorted(por_dia[d].items())))
    print("TOTAL", dict(sorted(total.items())))
    horas = (JANELA[1] - JANELA[0]).total_seconds() / 3600
    print(f"janela {JANELA[0].isoformat()} -> {JANELA[1].isoformat()} = {horas:.1f} h")
    for chave in ("oportunidades", "true", "false"):
        print(f"  {chave}/dia (janela inteira) = {total[chave] * 24 / horas:.1f}")
    nao_e = total["nao_E"]
    falha = total["U"] + total["I"]
    print(f"  (U + I) / nao_E = {falha}/{nao_e} = {100 * falha / nao_e:.1f} %")
    print(f"  U / nao_E = {100 * total['U'] / nao_e:.1f} %; I / nao_E = {100 * total['I'] / nao_e:.1f} %")
    print("classe:detalhe", dict(detalhes.most_common()))
    print("recusas da camada de propostas (por nome, todas):", dict(recusas_nome.most_common()))
    print("via do estado do token:", dict(vias))
    atraso.sort()
    if atraso:
        q = [atraso[int(p * (len(atraso) - 1))] for p in (0.5, 0.9, 0.99, 1.0)]
        tarde = sum(1 for a in atraso if a > 60)
        print(f"computed_at - end_time (s): p50 {q[0]:.1f} p90 {q[1]:.1f} p99 {q[2]:.1f} "
              f"max {q[3]:.1f}; > 60 s: {tarde}")


def extra() -> None:
    """Descritivos sem desfecho: cobertura, idade na 1.a oportunidade, true/false por bloco de 6 h."""
    primeiras = json.loads((AQUI / "f1_primeiras.json").read_text(encoding="utf-8"))
    pontos, pedigree = _pontos(), _pedigree()
    cob: Counter[str] = Counter()
    idades: list[int] = []
    blocos: dict[str, Counter[str]] = defaultdict(Counter)
    for mint, r in primeiras.items():
        row = _row(r)
        lineage = pedigree.get(mint)
        refus = ("pedigree_unknown",) if lineage is None else evaluate_pedigree(lineage, PEDIGREE_V1)
        if "creator_serial" in refus or "symbol_clone" in refus:
            continue
        t = row.end_time
        status, _ = coverage_of(pontos.get(mint, []), end_time=t, created_at=row.created_at)
        cob[status] += 1
        idades.append(int((t - row.created_at).total_seconds()))  # type: ignore[operator]
        o = Oportunidade(
            rule_set_id=ARMS[0][0], mint=mint, evaluated_at=max(t + timedelta(seconds=60), row.computed_at or t),
            features_end_time=t, features_computed_at=row.computed_at, fidelity="faithful",
            coverage_status=status, line_reason=row.line_reason, higher_lows=row.higher_lows,
            breakout_15m=row.breakout_15m, distance_to_support_pct=row.distance_to_support_pct,
            mcap_slope_15m=row.mcap_slope_15m, curve_progress_pct=row.curve_progress_pct,
            proposal_refusals=(), no_proposal_reason=None, proposal_id=None, proposal_status=None,
            proposal_refusal=None, aposta=None, prior_other_bet=False,
        )
        blocos[f"{t.date().isoformat()}T{(t.hour // 6) * 6:02d}"][classe_linha(o)[0]] += 1
    idades.sort()
    print("cobertura (nao_E):", dict(cob))
    print("idade na 1.a oportunidade (s): p10/p50/p90 =",
          [idades[int(p * (len(idades) - 1))] for p in (0.1, 0.5, 0.9)])
    print("blocos de 6 h (true/false):", {b: f"{c['true']}/{c['false']}" for b, c in sorted(blocos.items())})
    print("blocos com os dois grupos:", sum(1 for c in blocos.values() if c["true"] and c["false"]),
          "de", len(blocos))


if __name__ == "__main__":
    {"fase1": fase1, "fase2": fase2, "extra": extra}[sys.argv[1]]()
