"""The frozen rules of H-039/H-040/H-041 and their plateau neighbours, and the plan lists.

One :class:`Variant` per (hypothesis, parameter set): the frozen one and one per declared
neighbour, one parameter at a time. :func:`compute_plans` runs every variant over every
N_hist session (primary and holdout together, in date order — the H-041 baseline crosses
the cut without resetting) and :func:`digest` turns the plans into the sha256 freeze.
Nothing here simulates a trade.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

from hunter_indicators.b3.contraction import (
    CONTRACTION_V1,
    ContractionParams,
    amplitude_profile,
    contraction_steps,
    scan_contraction,
)
from hunter_indicators.b3.intraday_plan import TradePlan
from hunter_indicators.b3.orb import ORB_V1, OrbParams, scan_orb
from hunter_indicators.b3.reversal15 import (
    REVERSAL15_V1,
    Reversal15Params,
    reversal_steps,
    scan_reversal,
)
from infra.research.b3.sessions import SessionData

HYPOTHESES = ("H-039", "H-040", "H-041")
MIN_TRADES = {"H-039": 400, "H-040": 4000, "H-041": 200}

Params = OrbParams | Reversal15Params | ContractionParams


@dataclass(frozen=True, slots=True)
class Variant:
    key: str
    hypothesis: str
    label: str
    params: Params

    @property
    def frozen(self) -> bool:
        return self.label == "congelado"


def _v(hyp: str, label: str, params: Params) -> Variant:
    key = hyp if label == "congelado" else f"{hyp}@{label}"
    return Variant(key, hyp, label, params)


def variants() -> list[Variant]:
    c = CONTRACTION_V1
    return [
        _v("H-039", "congelado", ORB_V1),
        _v("H-039", "L15", replace(ORB_V1, version="orb_win/1@L15", range_minutes=15)),
        _v("H-039", "L60", replace(ORB_V1, version="orb_win/1@L60", range_minutes=60)),
        _v("H-040", "congelado", REVERSAL15_V1),
        _v("H-040", "D10", replace(REVERSAL15_V1, version="reversal15_win/1@D10", bar_minutes=10)),
        _v("H-040", "D30", replace(REVERSAL15_V1, version="reversal15_win/1@D30", bar_minutes=30)),
        _v("H-041", "congelado", c),
        _v(
            "H-041",
            "theta0.5",
            replace(c, version="contraction_win/1@theta0.5", theta=Decimal("0.5")),
        ),
        _v(
            "H-041",
            "theta0.7",
            replace(c, version="contraction_win/1@theta0.7", theta=Decimal("0.7")),
        ),
        _v("H-041", "k4", replace(c, version="contraction_win/1@k4", window_bars=4)),
        _v("H-041", "k9", replace(c, version="contraction_win/1@k9", window_bars=9)),
        _v(
            "H-041",
            "target1.5",
            replace(c, version="contraction_win/1@target1.5", target_r=Decimal("1.5")),
        ),
        _v(
            "H-041",
            "target3",
            replace(c, version="contraction_win/1@target3", target_r=Decimal("3")),
        ),
    ]


@dataclass(slots=True)
class PlanSet:
    plans: dict[str, list[TradePlan]] = field(default_factory=dict[str, list[TradePlan]])
    no_plan: dict[str, list[tuple[date, str]]] = field(
        default_factory=dict[str, list[tuple[date, str]]]
    )
    armed_sessions: dict[str, int] = field(default_factory=dict[str, int])
    ratios: dict[str, list[Fraction]] = field(default_factory=dict[str, list[Fraction]])


def _run(variant: Variant, sessions: Sequence[SessionData], out: PlanSet) -> None:
    plans: list[TradePlan] = []
    reasons: list[tuple[date, str]] = []
    p = variant.params
    profiles: list[dict[int, Fraction]] = []
    armed = 0
    ratios: list[Fraction] = []
    for s in sessions:
        if isinstance(p, OrbParams):
            got = scan_orb(s.win, s.window, p)
            if isinstance(got, TradePlan):
                plans.append(got)
            else:
                reasons.append((got.trading_date, got.reason))
        elif isinstance(p, Reversal15Params):
            plans.extend(scan_reversal(s.win, s.window, p))
            for _, last, side in reversal_steps(s.win, s.window, p):
                if last is None or side is None:
                    reasons.append((s.window.trading_date, "empty_bar" if last is None else "doji"))
        else:
            previous = profiles[-p.baseline_sessions :]
            steps = list(contraction_steps(s.win, s.window, previous, p))
            ratios.extend(x.ratio for x in steps)
            armed += any(x.ratio <= p.theta for x in steps)
            got = scan_contraction(s.win, s.window, previous, p)
            if isinstance(got, TradePlan):
                plans.append(got)
            else:
                reasons.append((got.trading_date, got.reason))
            profiles.append(amplitude_profile(s.win, s.window, p))
    out.plans[variant.key] = plans
    out.no_plan[variant.key] = reasons
    if isinstance(p, ContractionParams):
        out.armed_sessions[variant.key] = armed
        out.ratios[variant.key] = ratios


def compute_plans(sessions: Sequence[SessionData]) -> PlanSet:
    out = PlanSet()
    for variant in variants():
        _run(variant, sessions, out)
    return out


def digest(planset: PlanSet) -> tuple[str, str]:
    """One line per plan (``variant<TAB>identity``), and the sha256 of that text."""
    lines = [
        f"{key}\t{plan.identity()}" for key in sorted(planset.plans) for plan in planset.plans[key]
    ]
    text = "\n".join(lines) + "\n"
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()
