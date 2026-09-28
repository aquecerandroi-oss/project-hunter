"""R84 — protocolo H-024 sobre um painel (real ou sintético): semanas, braços, dois limites, inferência, veredito."""

from __future__ import annotations

import datetime as dt

import numpy as np
from engine import MIN_N, TOP, listed, simulate, targets, week
from panel import Panel
from stats84 import MIN_WEEKS, bound_verdicts, holm_verdict, mbb_indices, summarize

MRE = 0.0025
SPLIT_DAY = (dt.date(2022, 1, 1) - dt.date(1970, 1, 1)).days
BOUNDS = ("opt", "pes")


def mondays(p: Panel, last_t_epoch: int) -> list[int]:
    """Colunas das segundas-feiras desde a 1.ª com ≥ 20 listados (só datas) até `last_t_epoch`."""
    first_mon = p.day0 + ((4 - p.day0) % 7)  # 1970-01-01 foi quinta; segunda ⇔ (dia − 4) % 7 == 0
    cols = range(first_mon - p.day0, last_t_epoch - p.day0 + 1, 7)
    out = [t for t in cols if t >= 45]
    start = next(k for k, t in enumerate(out) if int(listed(p, t).sum()) >= TOP)
    return out[start:]


def _dd(r: np.ndarray) -> float:
    eq = np.cumprod(1 + r)
    return float(np.min(eq / np.maximum.accumulate(eq)) - 1)


def _desc(r: np.ndarray) -> dict[str, float]:
    sd = float(np.std(r, ddof=1))
    return {"mean": float(np.mean(r)), "sharpe": float(np.mean(r) / sd * np.sqrt(52)) if sd > 0 else float("nan"), "maxdd": _dd(r)}


def run(p: Panel, ts: list[int], cost: float = 0.0015, reps: int = 10_000) -> dict:
    res: dict = {"weeks_total": len(ts)}
    wks = {lb: [week(p, t, lb) for t in ts] for lb in (7, 14, 28)}
    ev = {lb: np.array([w.n >= MIN_N for w in wks[lb]]) for lb in wks}
    ev_t = np.array(ts)[ev[14]]
    res["n_eval"] = int(ev[14].sum())
    res["calendar_holes"] = int(np.sum(np.diff(ev_t) != 7)) if ev_t.size > 1 else 0
    res["first_t"], res["last_t"] = p.day0 + ts[0], p.day0 + ts[-1]
    res["mean_n"] = float(np.mean([w.n for w in wks[14]]))
    r: dict = {}
    info: dict = {}
    for lb in wks:
        for arm in ("ew", "ts", "cs"):
            plan = [targets(w, arm) for w in wks[lb]]
            for b in BOUNDS:
                r[(arm, lb, b)], info[(arm, lb, b)] = simulate(p, ts, plan, b, cost)
    res["info"] = {f"{a}{lb}_{b}": v for (a, lb, b), v in info.items() if lb == 14}
    res["ts_cash_weeks"] = int(sum(1 for w, e in zip(wks[14], ev[14], strict=True) if e and not np.any(w.m > 0)))
    res["ts_mean_exposure"] = float(np.mean([np.mean(w.m > 0) for w, e in zip(wks[14], ev[14], strict=True) if e]))
    n = res["n_eval"]
    if n < max(MIN_WEEKS, 16):
        res["verdict"] = "LIMITE DE DADO"
        return res
    idx = mbb_indices(n, 8, reps)
    pre = (np.array(ts)[ev[14]] + p.day0) < SPLIT_DAY
    arms: dict = {}
    for arm in ("ts", "cs"):
        per_b = []
        for b in BOUNDS:
            d = (r[(arm, 14, b)] - r[("ew", 14, b)])[ev[14]]
            s = summarize(d, idx)
            s["level"] = float(np.mean(r[(arm, 14, b)][ev[14]]))
            s["ew_level"] = float(np.mean(r[("ew", 14, b)][ev[14]]))
            s["d7"], s["d28"] = (float(np.mean((r[(arm, lb, b)] - r[("ew", lb, b)])[ev[lb]])) for lb in (7, 28))
            s["plateau"] = s["d7"] > 0 and s["d28"] > 0
            s["d_pre"], s["d_post"] = float(np.mean(d[pre])), float(np.mean(d[~pre]))
            s["n_pre"], s["n_post"] = int(pre.sum()), int((~pre).sum())
            s["split"] = s["d_pre"] > 0 and s["d_post"] > 0
            for blk in (4, 16):
                lo, hi = np.percentile(d[mbb_indices(n, blk, reps)].mean(axis=1), [2.5, 97.5])
                s[f"ci_b{blk}"] = (float(lo), float(hi))
            s["desc"] = _desc(r[(arm, 14, b)][ev[14]])
            per_b.append(s)
        arms[arm] = per_b
    res["arms"] = arms
    res["holm"] = bound_verdicts(arms["ts"], arms["cs"], MRE)
    res["verdict"] = holm_verdict(arms["ts"], arms["cs"], MRE)
    res["verdict_cs"] = holm_verdict(arms["cs"], arms["ts"], MRE)
    res["ew_desc"] = _desc(r[("ew", 14, "opt")][ev[14]])
    res["_r"], res["_ev"], res["_ts"], res["_wks"] = r, ev, ts, wks
    return res


def report(res: dict) -> str:
    pp = 100.0
    day = lambda e: (dt.date(1970, 1, 1) + dt.timedelta(days=int(e))).isoformat()  # noqa: E731
    lines = [f"semanas: {res['weeks_total']} ({day(res['first_t'])} → {day(res['last_t'])}); avaliáveis (N_T ≥ 15): "
             f"{res['n_eval']}; buracos de calendário entre avaliáveis: {res['calendar_holes']}; N_T médio {res['mean_n']:.2f}",
             f"TS: semanas 100 % caixa {res['ts_cash_weeks']}; exposição média {res['ts_mean_exposure']:.3f}",
             f"VEREDITO primária (D_ts): {res['verdict']}"]
    if "arms" not in res:
        return "\n".join(lines)
    lines.append(f"veredito secundária (D_cs, com a mesma família): {res['verdict_cs']}")
    for arm in ("ts", "cs"):
        for b, s, h in zip(BOUNDS, res["arms"][arm], res["holm"], strict=True):
            hp = h["holm_ts"] if arm == "ts" else h["holm_cs"]
            lines.append(
                f"D_{arm} [{b}] n={s['n']}: {s['d'] * pp:+.3f} p.p./sem, IC95 [{s['lo'] * pp:+.3f}; {s['hi'] * pp:+.3f}], "
                f"p={s['p']:.4f} (Holm {hp:.4f}), dp(d_t)={s['sd'] * pp:.2f} p.p.; nível {arm} {s['level'] * pp:+.3f} "
                f"(EW {s['ew_level'] * pp:+.3f}); patamar 7d {s['d7'] * pp:+.3f} 28d {s['d28'] * pp:+.3f}; "
                f"antes-2022 {s['d_pre'] * pp:+.3f} (n={s['n_pre']}) depois {s['d_post'] * pp:+.3f} (n={s['n_post']}); "
                f"IC b4 [{s['ci_b4'][0] * pp:+.3f}; {s['ci_b4'][1] * pp:+.3f}] b16 [{s['ci_b16'][0] * pp:+.3f}; "
                f"{s['ci_b16'][1] * pp:+.3f}]; Sharpe {s['desc']['sharpe']:.2f} DD {s['desc']['maxdd'] * pp:.1f} %")
    e = res["ew_desc"]
    lines.append(f"EW [opt]: média {e['mean'] * pp:+.3f} %/sem, Sharpe {e['sharpe']:.2f}, DD {e['maxdd'] * pp:.1f} %")
    lines.append("eventos/giro (lb 14): " + "; ".join(f"{k}: fim-de-série {v['delist_events']}, congeladas {v['frozen']}, "
                                                    f"giro {v['turnover']:.1f}" for k, v in res["info"].items()))
    return "\n".join(lines)
