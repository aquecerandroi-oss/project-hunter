"""Markdown report of the WIN family: verdict first, the pre-registered numbers, then the
descriptives that decide nothing. Portuguese, like the notes it is pasted into.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np

from hunter_indicators.b3.calendar_2026 import BRT
from infra.research.b3.evaluate import Arm, Result, Row
from infra.research.b3.sessions import Population
from infra.research.b3.simulate import Status
from infra.research.b3.variants import PlanSet


def _f(x: float, digits: int = 3) -> str:
    return "—" if not math.isfinite(x) else f"{x:+.{digits}f}".replace(".", ",")


def _ci(ci: tuple[float, float]) -> str:
    return f"[{_f(ci[0])}; {_f(ci[1])}]"


def _ok_rows(arm: Arm) -> list[Row]:
    return [r for r in arm.rows if r.outcome.status is Status.OK]


def _group_mean(rows: Sequence[Row], key: str) -> str:
    groups: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        o = r.outcome
        if key == "lado":
            k = o.side.value
        elif key == "ano":
            k = str(o.plan.trading_date.year)
        else:
            k = o.plan.decided_at.astimezone(BRT).strftime("%Hh")
        groups[k].append(float(o.net_bp or 0))
    return " · ".join(
        f"{k}: {_f(float(np.mean(v)))} (n={len(v)})" for k, v in sorted(groups.items())
    )


def _exits(rows: Sequence[Row]) -> str:
    counts = Counter(r.outcome.exit_reason.value for r in rows if r.outcome.exit_reason is not None)
    total = sum(counts.values())
    return " · ".join(f"{k} {v / total:.1%}" for k, v in sorted(counts.items())) if total else "—"


def _concentration(rows: Sequence[Row]) -> str:
    if not rows:
        return "—"
    by_month: dict[tuple[int, int], list[float]] = defaultdict(list)
    for r in rows:
        d = r.outcome.plan.trading_date
        by_month[(d.year, d.month)].append(float(r.outcome.net_bp or 0))
    top_n = max(len(v) for v in by_month.values())
    total = sum(sum(v) for v in by_month.values())
    top_sum = max((sum(v) for v in by_month.values()), key=abs)
    share = f"{top_sum / total:.1%}" if total else "—"
    return f"mês mais cheio {top_n / len(rows):.1%} das operações; maior |resultado| de um mês = {share} do total"


def _funnel_reasons(planset: PlanSet, key: str, days: set[date]) -> str:
    counts = Counter(reason for d, reason in planset.no_plan.get(key, []) if d in days)
    return " · ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "—"


def _arm_line(name: str, arm: Arm) -> str:
    return (
        f"| {name} | {arm.n_plans} | {arm.n_no_entry} | {arm.n_censored} | {arm.n_ok} | "
        f"{_f(arm.mean)} | {_f(arm.stress_mean)} |"
    )


def render_hypothesis(
    r: Result, pop: Population, planset: PlanSet, extras: Mapping[str, str]
) -> list[str]:
    primary_days = {s.window.trading_date for s in pop.primary}
    holdout_days = {s.window.trading_date for s in pop.holdout}
    ok = _ok_rows(r.primary)
    out = [
        f"## {r.hypothesis} — **{r.verdict}**",
        "",
        *(f"- motivo: {m}" for m in r.reasons),
        "",
        "| braço | planos | sem barra na entrada | censuradas | com desfecho | média bp | média bp (estresse) |",
        "|---|---:|---:|---:|---:|---:|---:|",
        _arm_line("primário (congelado)", r.primary),
        *(_arm_line(f"patamar {k}", a) for k, a in r.neighbours.items()),
    ]
    if r.holdout is not None:
        out.append(_arm_line("holdout (congelado)", r.holdout))
    out += [
        "",
        f"- meses com operação no primário: {r.months}",
        f"- IC de meses (0,8333 %–99,1667 %): {_ci(r.ci)} · no estresse: {_ci(r.stress_ci)}",
        f"- permutação de lados: p = {_f(r.p_raw, 4)} · Holm (família de 3) = {_f(r.p_holm, 4)}"
        " — associação condicional aos instantes e à geometria; não testa a seleção",
        f"- metades: {_f(r.halves[0])} / {_f(r.halves[1])} · no estresse: "
        f"{_f(r.stress_halves[0])} / {_f(r.stress_halves[1])}",
        f"- censura: {r.censor_share:.2%} das operações · grade incompatível + sem dado: {r.data_share:.2%}",
        "",
        "Cláusulas: " + " · ".join(f"{'✓' if v else '✗'} {k}" for k, v in r.clauses.items()),
        "",
        "**Publicado sem decidir:**",
        "",
        f"- funil sem plano (primário): {_funnel_reasons(planset, r.hypothesis, primary_days)}",
        f"- funil sem plano (holdout): {_funnel_reasons(planset, r.hypothesis, holdout_days)}",
        f"- por lado: {_group_mean(ok, 'lado')}",
        f"- por ano: {_group_mean(ok, 'ano')}",
        f"- saídas: {_exits(ok)}",
        f"- concentração: {_concentration(ok)}",
    ]
    if r.hypothesis == "H-040":
        out.append(f"- por hora da decisão (BRT): {_group_mean(ok, 'hora')}")
    out += [f"- {k}: {v}" for k, v in extras.items()]
    return out + [""]


def render(
    results: Mapping[str, Result],
    pop: Population,
    planset: PlanSet,
    *,
    phase: str,
    header: Sequence[str],
    extras: Mapping[str, Mapping[str, str]],
) -> str:
    f = pop.funnel
    first = pop.sessions[0].window.trading_date if pop.sessions else None
    last = pop.sessions[-1].window.trading_date if pop.sessions else None
    cut = pop.holdout[0].window.trading_date if pop.holdout else None
    lines = [
        f"# H-039/H-040/H-041 — relatório da fase `{phase}` (retrospectiva no WIN, aproximação OHLC de 1 min)",
        "",
        *header,
        "",
        f"- N_hist: {f['n_hist']} pregões ({first} → {last}); primário {len(pop.primary)}, holdout {len(pop.holdout)}"
        f" (holdout desde {cut})",
        f"- funil de calendário: {dict(f)}; datas do WIN antes da cobertura do calendário: {pop.before_coverage}",
        "- ressalva (emenda 1): 'sem dado' olha a disponibilidade até 16:30, depois dos instantes de"
        " decisão — seleção por carimbo, nunca por preço; O = 10:00 BRT é suposto, conferido só por"
        " compatibilidade de carimbos; trajetória por aproximação OHLC de 1 min, não execução observada",
        "",
    ]
    for hyp, r in results.items():
        lines += render_hypothesis(r, pop, planset, extras.get(hyp, {}))
    lines += [
        "Nada neste relatório autoriza dinheiro real. CONFIRMA = candidato a coorte prospectiva em papel;"
        " NÃO CONFIRMA não é refutação; REFUTA é sobre o tamanho (+1,5 bp), não sobre qualquer efeito.",
        "",
    ]
    return "\n".join(lines)
