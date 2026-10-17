"""Outcomes, statistics and verdicts of H-039/H-040/H-041 (contract items h and i of H-039).

:func:`evaluate_primary` simulates only primary sessions; :func:`finalize_holdout` adds the
holdout once, afterwards. The verdict follows the frozen order: LIMITE DE DADO → CONFIRMA
(every clause, censoring resolved under the stress scenario) → REFUTA (upper CI < MRE) →
NÃO CONFIRMA. A clause without a number fails; it never approves.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import numpy as np

from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.intraday_plan import TradePlan
from infra.research.b3.sessions import Population, SessionData
from infra.research.b3.simulate import WIN_COSTS, Costs, Outcome, Status, simulate
from infra.research.b3.stats_b3 import (
    REPS,
    SEED,
    first_half_mask,
    half_cut,
    holm,
    monthly_bootstrap_ci,
    side_permutation_p,
)
from infra.research.b3.variants import HYPOTHESES, MIN_TRADES, PlanSet, variants

MRE_BP = 1.5
MIN_MONTHS = 24
MAX_DATA_SHARE = 0.10
MAX_CENSOR_SHARE = 0.05


@dataclass(frozen=True, slots=True)
class Row:
    outcome: Outcome
    flipped: Outcome | None


@dataclass(slots=True)
class Arm:
    """One variant on one partition: counts, net bp of trades with outcome, stress values."""

    n_plans: int
    n_no_entry: int
    n_censored: int
    rows: list[Row]
    net: np.ndarray
    stress: np.ndarray
    dates: list[date]
    stress_dates: list[date]
    plan_dates: list[date]

    @property
    def months(self) -> np.ndarray:
        """Calendar months with at least one operation (a plan: the funnel's "operações")."""
        return np.unique(np.array([_month(d) for d in self.plan_dates], dtype=np.int64))

    @property
    def n_ok(self) -> int:
        return int(self.net.size)

    @property
    def mean(self) -> float:
        return float(self.net.mean()) if self.net.size else math.nan

    @property
    def stress_mean(self) -> float:
        return float(self.stress.mean()) if self.stress.size else math.nan


def _month(d: date) -> int:
    return d.year * 12 + d.month


def simulate_rows(
    plans: Sequence[TradePlan],
    by_date: Mapping[date, SessionData],
    *,
    flip: bool,
    costs: Costs = WIN_COSTS,
) -> list[Row]:
    rows: list[Row] = []
    for plan in plans:
        bars = by_date[plan.trading_date].win
        out = simulate(plan, bars, costs=costs)
        flipped = simulate(plan, bars, costs=costs, flip=True) if flip else None
        if flipped is not None and flipped.status is not out.status:
            raise AssertionError(f"censoring must not depend on the side: {plan.identity()}")
        rows.append(Row(out, flipped))
    return rows


def arm_of(n_plans: int, rows: Sequence[Row]) -> Arm:
    ok = [r for r in rows if r.outcome.status is Status.OK]
    cens = [r for r in rows if r.outcome.status is Status.CENSORED]
    net = np.array([float(r.outcome.net_bp or 0) for r in ok])
    both = ok + cens
    stress = np.array([float(r.outcome.stress_bp or 0) for r in both])
    return Arm(
        n_plans=n_plans,
        n_no_entry=sum(1 for r in rows if r.outcome.status is Status.NO_ENTRY),
        n_censored=len(cens),
        rows=list(rows),
        net=net,
        stress=stress,
        dates=[r.outcome.plan.trading_date for r in ok],
        stress_dates=[r.outcome.plan.trading_date for r in both],
        plan_dates=[r.outcome.plan.trading_date for r in rows],
    )


def _halves(values: np.ndarray, dates: list[date], cut: date | None) -> tuple[float, float]:
    """Means before/after the half cut of the **operations**, shared by main and stress."""
    if not dates or cut is None:
        return math.nan, math.nan
    first = first_half_mask(dates, cut)
    a, b = values[first], values[~first]
    return (float(a.mean()) if a.size else math.nan, float(b.mean()) if b.size else math.nan)


@dataclass(slots=True)
class Result:
    hypothesis: str
    primary: Arm
    ci: tuple[float, float]
    stress_ci: tuple[float, float]
    p_raw: float
    halves: tuple[float, float]
    stress_halves: tuple[float, float]
    neighbours: dict[str, Arm]
    data_share: float
    months: int
    p_holm: float = math.nan
    holdout: Arm | None = None
    verdict: str = ""
    reasons: list[str] = field(default_factory=list[str])
    clauses: dict[str, bool] = field(default_factory=dict[str, bool])

    @property
    def censor_share(self) -> float:
        ops = self.primary.n_plans
        return self.primary.n_censored / ops if ops else math.nan


def _strata(hyp: str, rows: Sequence[Row], by_date: Mapping[date, SessionData]) -> np.ndarray:
    keys: list[int] = []
    for r in rows:
        plan = r.outcome.plan
        slot = 0
        if hyp == "H-040":
            open_at = by_date[plan.trading_date].window.open_at
            slot = int((plan.decided_at - open_at).total_seconds() // 60)
        keys.append(_month(plan.trading_date) * 1000 + slot)
    return np.array(keys)


def data_share(pop: Population) -> float:
    f = pop.funnel
    base = f["calendar_sessions"] - f["ash_wednesday"] - f["win_expiry"]
    return (f["grid_incompatible"] + f["no_data"]) / base if base else math.nan


def evaluate_primary(
    planset: PlanSet, pop: Population, *, reps: int = REPS, seed: int = SEED
) -> dict[str, Result]:
    by_date = {s.window.trading_date: s for s in pop.sessions}
    primary_days = {s.window.trading_date for s in pop.primary}
    results: dict[str, Result] = {}
    for hyp in HYPOTHESES:
        frozen = [p for p in planset.plans[hyp] if p.trading_date in primary_days]
        arm = arm_of(len(frozen), simulate_rows(frozen, by_date, flip=True))
        ok = [r for r in arm.rows if r.outcome.status is Status.OK]
        cut = half_cut(arm.plan_dates)
        p_raw = side_permutation_p(
            arm.net,
            np.array([float(r.flipped.net_bp or 0) for r in ok if r.flipped is not None]),
            np.array([r.outcome.side is Side.BUY for r in ok]),
            _strata(hyp, ok, by_date),
            reps=reps,
            seed=seed,
        )
        neighbours: dict[str, Arm] = {}
        for v in variants():
            if v.hypothesis == hyp and not v.frozen:
                plans = [p for p in planset.plans[v.key] if p.trading_date in primary_days]
                neighbours[v.label] = arm_of(len(plans), simulate_rows(plans, by_date, flip=False))
        results[hyp] = Result(
            hypothesis=hyp,
            primary=arm,
            ci=monthly_bootstrap_ci(
                arm.net, _months_of(arm.dates), blocks=arm.months, reps=reps, seed=seed
            ),
            stress_ci=monthly_bootstrap_ci(
                arm.stress, _months_of(arm.stress_dates), blocks=arm.months, reps=reps, seed=seed
            ),
            p_raw=p_raw,
            halves=_halves(arm.net, arm.dates, cut),
            stress_halves=_halves(arm.stress, arm.stress_dates, cut),
            neighbours=neighbours,
            data_share=data_share(pop),
            months=int(arm.months.size),
        )
    # the family always has three members; a hypothesis in LIMITE (or without p) enters with 1
    family = [
        1.0 if limit_reasons(r) or not math.isfinite(r.p_raw) else r.p_raw for r in results.values()
    ]
    adjusted = holm(family)
    for r, p in zip(results.values(), adjusted, strict=True):
        r.p_holm = p
        apply_verdict(r, final=False)
    return results


def finalize_holdout(results: dict[str, Result], planset: PlanSet, pop: Population) -> None:
    by_date = {s.window.trading_date: s for s in pop.sessions}
    holdout_days = {s.window.trading_date for s in pop.holdout}
    for hyp, r in results.items():
        plans = [p for p in planset.plans[hyp] if p.trading_date in holdout_days]
        r.holdout = arm_of(len(plans), simulate_rows(plans, by_date, flip=False))
        apply_verdict(r, final=True)


def _pos(x: float) -> bool:
    return math.isfinite(x) and x > 0


def _months_of(dates: Sequence[date]) -> np.ndarray:
    return np.array([_month(d) for d in dates], dtype=np.int64)


def limit_reasons(r: Result) -> list[str]:
    """The frozen LIMITE DE DADO tests (operations = plans, the funnel's vocabulary)."""
    limits: list[str] = []
    if r.months < MIN_MONTHS:
        limits.append(f"{r.months} meses com operação no primário (< {MIN_MONTHS})")
    if r.primary.n_ok < MIN_TRADES[r.hypothesis]:
        limits.append(f"{r.primary.n_ok} operações com desfecho (< {MIN_TRADES[r.hypothesis]})")
    if not (math.isfinite(r.data_share) and r.data_share <= MAX_DATA_SHARE):
        limits.append(f"grade incompatível + sem dado = {r.data_share:.1%} (> 10 %)")
    if not (math.isfinite(r.censor_share) and r.censor_share <= MAX_CENSOR_SHARE):
        limits.append(f"censura = {r.censor_share:.1%} das operações (> 5 %)")
    return limits


def apply_verdict(r: Result, *, final: bool) -> None:
    limits = limit_reasons(r)
    c: dict[str, bool] = {
        "média ≥ +1,5 bp": math.isfinite(r.primary.mean) and r.primary.mean >= MRE_BP,
        "IC inferior > 0": _pos(r.ci[0]),
        "Holm p < 0,05": math.isfinite(r.p_holm) and r.p_holm < 0.05,
        "metade 1 > 0": _pos(r.halves[0]),
        "metade 2 > 0": _pos(r.halves[1]),
    }
    for label, arm in r.neighbours.items():
        c[f"patamar {label} > 0"] = _pos(arm.mean)
    stress_ok = (
        math.isfinite(r.primary.stress_mean)
        and r.primary.stress_mean >= MRE_BP
        and _pos(r.stress_ci[0])
        and _pos(r.stress_halves[0])
        and _pos(r.stress_halves[1])
        and all(_pos(a.stress_mean) for a in r.neighbours.values())
    )
    if final:
        h = r.holdout
        c["holdout > 0"] = h is not None and _pos(h.mean)
        stress_ok = stress_ok and h is not None and _pos(h.stress_mean)
    c["censura resolvida (estresse)"] = stress_ok
    r.clauses = c
    if limits:
        r.verdict, r.reasons = "NÃO CONFIRMA", ["LIMITE DE DADO: " + "; ".join(limits)]
    elif all(c.values()):
        r.verdict, r.reasons = ("CONFIRMA", []) if final else ("PENDENTE DO HOLDOUT", [])
    elif math.isfinite(r.ci[1]) and r.ci[1] < MRE_BP:
        r.verdict, r.reasons = "REFUTA", [f"limite superior do IC {r.ci[1]:.3f} < +1,5 bp"]
    else:
        r.verdict, r.reasons = "NÃO CONFIRMA", [k for k, ok in c.items() if not ok]


def gross_raw_bp(rows: Sequence[Row]) -> float:
    """Descriptive: model exit level minus raw entry open, no fee, no slippage on the prices.

    The exit level comes from the simulated (slipped) trade — a stop is placed from the
    slipped fill — so this is not a full re-simulation without slippage (labelled as such).
    """
    vals = [
        float(r.outcome.gross_raw_points / r.outcome.raw_entry * Decimal(10000))
        for r in rows
        if r.outcome.status is Status.OK
        and r.outcome.gross_raw_points is not None
        and r.outcome.raw_entry
    ]
    return float(np.mean(vals)) if vals else math.nan
