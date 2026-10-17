"""Command line of the WIN family retrospective (H-039/H-040/H-041), in three phases.

    uv run python -m infra.research.b3.run_family --phase freeze  --win WIN.csv --ibov IBOV.csv \
        --utc-offset-hours -3 [--offset-reason "..."] [--out .claude/state/h039-041/run]
    ... --phase primary   (outcomes of the primary only; refuses if the plans changed)
    ... --phase holdout   (once, after the primary report exists)

``freeze`` writes the population (funnel, exclusion list, N_hist dates, cut, timestamp
diagnostics), every plan of every variant, and the configuration with the sha256 of the
pinned code (:mod:`infra.research.b3.freeze`), **before** any trajectory after a decision
is simulated. ``primary`` and ``holdout`` refuse up front if their output exists, then
recompute all of it and refuse if anything differs; ``holdout`` also refuses unless it
reproduces the published primary report byte for byte. No phase overwrites a file.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping, Sequence
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np

from hunter_indicators.b3.calendar_2026 import WIN_SPEC
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.intraday_plan import TradePlan
from infra.research.b3.evaluate import (
    Result,
    evaluate_primary,
    finalize_holdout,
    gross_raw_bp,
    simulate_rows,
)
from infra.research.b3.freeze import (
    FreezeViolation,
    check_frozen,
    config_text,
    refuse_existing,
    sha,
    write_new,
)
from infra.research.b3.mt5_csv import (
    OffsetUndetectable,
    confirm_offset,
    decode_export,
    detect_server_offset,
    first_minutes,
    parse_export,
    require_tick_grid,
    to_bars,
)
from infra.research.b3.report_b3 import render
from infra.research.b3.sessions import Population, build_population, overnight_gaps
from infra.research.b3.simulate import Costs, Status
from infra.research.b3.stats_b3 import REPS
from infra.research.b3.variants import PlanSet, compute_plans, digest

DEFAULT_OUT = Path(".claude/state/h039-041/run")


def load(
    win_path: Path, ibov_path: Path, offset: timedelta, reason: str | None
) -> tuple[Population, list[str]]:
    raw_win = parse_export(decode_export(win_path.read_bytes()))
    raw_ibov = parse_export(decode_export(ibov_path.read_bytes()))
    try:
        detected: timedelta | None = detect_server_offset(raw_ibov)
        note = f"fuso detectado {detected}"
    except OffsetUndetectable as exc:
        detected, note = None, f"fuso não detectável ({exc}); confirmação manual: {reason!r}"
    confirm_offset(offset, detected, manual_reason=reason)
    win = to_bars(raw_win, offset)
    require_tick_grid(win, WIN_SPEC.tick_size)
    pop = build_population(win, to_bars(raw_ibov, offset))
    header = [
        f"- arquivos: WIN `{win_path.name}` sha256 {hashlib.sha256(win_path.read_bytes()).hexdigest()}; "
        f"Ibovespa `{ibov_path.name}` sha256 {hashlib.sha256(ibov_path.read_bytes()).hexdigest()}",
        f"- fuso declarado {offset}; {note}",
        f"- primeiro minuto do Ibovespa por pregão (hora do servidor): {dict(first_minutes(raw_ibov).most_common(5))}",
        f"- primeiro minuto do WIN por pregão (hora do servidor): {dict(first_minutes(raw_win).most_common(5))}",
    ]
    return pop, header


def population_text(pop: Population, header: Sequence[str]) -> str:
    gaps = sorted(overnight_gaps(pop.sessions), key=lambda g: abs(g[1]), reverse=True)[:20]
    primary = {s.window.trading_date for s in pop.primary}
    lines = [*header, f"funil: {dict(pop.funnel)}", f"antes da cobertura: {pop.before_coverage}"]
    lines += [
        f"maiores saltos entre pregões (bp, diagnóstico de rolagem): {[(str(d), str(g)) for d, g in gaps]}"
    ]
    lines += [f"excluído {d} {step}" for d, step in pop.excluded]
    lines += [
        f"{s.window.trading_date} {'P' if s.window.trading_date in primary else 'H'}"
        for s in pop.sessions
    ]
    return "\n".join(lines) + "\n"


def extras(
    results: Mapping[str, Result], planset: PlanSet, pop: Population
) -> dict[str, dict[str, str]]:
    by_date = {s.window.trading_date: s for s in pop.sessions}
    out: dict[str, dict[str, str]] = {}
    for hyp, r in results.items():
        ok_plans = [row.outcome.plan for row in r.primary.rows if row.outcome.status is Status.OK]
        two = simulate_rows(ok_plans, by_date, flip=False, costs=Costs(Decimal("1.28"), 2))
        vals = [float(x.outcome.net_bp) for x in two if x.outcome.net_bp is not None]
        e = {"2 ticks por perna (média bp)": f"{np.mean(vals):+.3f}" if vals else "—"}
        label = "bruto: saída da operação deslizada − abertura bruta, sem tarifa (média bp)"
        e[label] = f"{gross_raw_bp(r.primary.rows):+.3f}"
        if hyp == "H-039":
            widths = [
                float(
                    (
                        Decimal(p.supporting_features["range_high"])
                        / Decimal(p.supporting_features["range_low"])
                        - 1
                    )
                    * 10000
                )
                for p in ok_plans
            ]
            e["largura da FA (mediana, bp)"] = f"{np.median(widths):.1f}" if widths else "—"
            longs = [
                TradePlan(
                    "always_long",
                    s.window.trading_date,
                    Side.BUY,
                    s.window.open_at + timedelta(minutes=30),
                    s.window.exit_at,
                    None,
                    Decimal("0.5"),
                    None,
                    "descritivo",
                )
                for s in pop.primary
            ]
            lv = [
                float(x.outcome.net_bp)
                for x in simulate_rows(longs, by_date, flip=False)
                if x.outcome.net_bp is not None
            ]
            e["sempre comprado O+30 → 16:30, stop de catástrofe de 50 % (média bp)"] = (
                f"{np.mean(lv):+.3f} (n={len(lv)})" if lv else "—"
            )
        if hyp == "H-041":
            ratios = [float(x) for x in planset.ratios.get(hyp, [])]
            e["pregões armados (c ≤ θ em algum j, N_hist inteiro)"] = (
                f"{planset.armed_sessions.get(hyp, 0)} de {len(pop.sessions)}"
            )
            if ratios:
                q = np.quantile(ratios, [0.1, 0.5, 0.9])
                e["c nos instantes mensuráveis (p10/p50/p90)"] = (
                    f"{q[0]:.3f} / {q[1]:.3f} / {q[2]:.3f}"
                )
        out[hyp] = e
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="H-039/H-040/H-041 retrospective on the WIN")
    ap.add_argument("--phase", choices=("freeze", "primary", "holdout"), required=True)
    ap.add_argument("--win", type=Path, required=True)
    ap.add_argument("--ibov", type=Path, required=True)
    ap.add_argument(
        "--utc-offset-hours", type=int, required=True, help="server clock = UTC + this (BRT = -3)"
    )
    ap.add_argument(
        "--offset-reason", default=None, help="written reason when the data cannot show the offset"
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--reps", type=int, default=REPS)
    ap.add_argument(
        "--fixture-only",
        action="store_true",
        help="allow fewer replicates than the frozen 10 000 (synthetic test fixtures only)",
    )
    a = ap.parse_args(argv)
    if a.reps != REPS and not a.fixture_only:
        raise FreezeViolation(f"the pre-registration fixes {REPS} replicates; got {a.reps}")
    out: Path = a.out
    if a.phase != "freeze":
        refuse_existing(out / f"{a.phase}_report.md")
    if a.phase == "holdout" and not (out / "primary_report.md").exists():
        raise FreezeViolation("the holdout is read only after the primary report exists")
    pop, header = load(a.win, a.ibov, timedelta(hours=a.utc_offset_hours), a.offset_reason)
    planset = compute_plans(pop.sessions)
    plans_text, plans_sha = digest(planset)
    current = {
        "population.txt": population_text(pop, header),
        "plans.txt": plans_text,
        "config.txt": config_text(a.reps),
    }
    if a.phase == "freeze":
        out.mkdir(parents=True, exist_ok=True)
        for name, text in current.items():
            write_new(out / name, text)
        write_new(out / "manifest.txt", "".join(f"{sha(v)} *{k}\n" for k, v in current.items()))
        sys.stdout.write(f"frozen: plans {plans_sha}\n")
        return 0
    check_frozen(out, current)
    results = evaluate_primary(planset, pop, reps=a.reps)
    head = [*header, f"- planos congelados sha256 {plans_sha}"]
    if a.reps != REPS:
        head.insert(0, f"**NÃO É A CONSULTA: {a.reps} réplicas (fixture de teste), não {REPS}.**")
    primary = render(
        results, pop, planset, phase="primary", header=head, extras=extras(results, planset, pop)
    )
    if a.phase == "primary":
        write_new(out / "primary_report.md", primary)
    else:
        if sha(primary) != sha((out / "primary_report.md").read_text(encoding="utf-8")):
            raise FreezeViolation(
                "the recomputed primary differs from the published primary report"
            )
        finalize_holdout(results, planset, pop)
        holdout = render(
            results,
            pop,
            planset,
            phase="holdout",
            header=head,
            extras=extras(results, planset, pop),
        )
        write_new(out / "holdout_report.md", holdout)
    for hyp, r in results.items():
        sys.stdout.write(f"{hyp}: {r.verdict}\n")
    sys.stdout.write(f"report: {out / f'{a.phase}_report.md'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
