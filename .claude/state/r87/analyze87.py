"""R87 — protocolo da H-028 (pré-registro + emenda de 05/10 15:40Z): braços, limites, fronteira, inferência, veredito."""

from __future__ import annotations

import dataclasses
import datetime as dt
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "r84"))
from engine87 import ARMS, C_PERP, C_SPOT, MIN_N, PLATEAU, Market, universe  # noqa: E402
from sim87 import simulate_arm  # noqa: E402
from stats84 import ci, mbb_indices, p_centered  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from infra.research.stats import adjust_family  # noqa: E402

SEED = 20261005
REPS = 10_000
BLOCK = 13
MRE_ANN = 0.05
MIN_WEEKS = 200
SPLIT_DAY = (dt.date(2023, 1, 1) - dt.date(1970, 1, 1)).days
BOUNDS, CONVS = ("opt", "pes"), ("after", "before")
NAMES = ("A0", "A1", "A2")


def mondays(mk: Market, first_day: int, last_day: int) -> list[int]:
    """Colunas de toda segunda desde a 1.ª ≥ first_day com N_T ≥ 15 (só universo) até last_day — calendário inteiro."""
    p = mk.p
    start = first_day + ((4 - first_day) % 7)
    cols = list(range(start - p.day0, last_day - p.day0 + 1, 7))
    k0 = next(k for k, t in enumerate(cols) if len(universe(mk, t)) >= MIN_N)
    return cols[k0:]


def _cover(expo: np.ndarray, pre: np.ndarray) -> tuple[int, int, int]:
    """Blocos NÃO sobrepostos de 13 semanas (ancorados no início) com exposição > 0: total, antes, depois do corte."""
    tot = pre_n = post_n = 0
    for a in range(0, expo.size - BLOCK + 1, BLOCK):
        if np.any(expo[a: a + BLOCK] > 0):
            tot += 1
            mid_pre = bool(np.mean(pre[a: a + BLOCK]) >= 0.5)
            pre_n += mid_pre
            post_n += not mid_pre
    return tot, pre_n, post_n


def _episodes_ok(res) -> tuple[int, int]:
    eps = res.episodes
    return len(eps), len({e["k0"] for e in eps})


def run(mk: Market, ts: list[int], reps: int = REPS, cost_mult: float = 1.0) -> dict:
    n = len(ts)
    days = np.array(ts) + mk.p.day0
    pre = days < SPLIT_DAY
    idx = mbb_indices(n, BLOCK, reps, SEED) if n >= BLOCK else None
    cs, cp = C_SPOT * cost_mult, C_PERP * cost_mult
    sims = {(a, b, c): simulate_arm(mk, ts, ARMS[a], b, c, cs, cp) for a in NAMES for b in BOUNDS for c in CONVS}
    plats = {(a, j, b, c): simulate_arm(mk, ts, PLATEAU[a][j], b, c, cs, cp)
             for a in ("A1", "A2") for j in (0, 1) for b in BOUNDS for c in CONVS}
    out: dict = {"n_weeks": n, "first": int(days[0]), "last": int(days[-1]), "n_pre": int(pre.sum()),
                 "mean_n": float(np.mean(sims[("A0", "opt", "after")].n_t)),
                 "low_n_weeks": int(np.sum(sims[("A0", "opt", "after")].n_t < MIN_N)), "sims": sims, "plats": plats,
                 "cells": {}}
    for b in BOUNDS:
        for c in CONVS:
            stats = {}
            for a in NAMES:
                r = sims[(a, b, c)].weekly
                s = {"mean": float(np.mean(r)), "ann": 52 * float(np.mean(r)), "sd": float(np.std(r, ddof=1))}
                if idx is not None:
                    lo, hi = ci(r, idx)
                    s.update(lo=52 * lo, hi=52 * hi, p=p_centered(r, idx))
                s["pre"], s["post"] = 52 * float(np.mean(r[pre])), 52 * float(np.mean(r[~pre]))
                s["split"] = s["pre"] > 0 and s["post"] > 0
                if a in PLATEAU:
                    s["plat"] = tuple(52 * float(np.mean(plats[(a, j, b, c)].weekly)) for j in (0, 1))
                    s["plateau"] = all(v > 0 for v in s["plat"])
                else:
                    s["plat"], s["plateau"] = (), True
                s["cover"] = _cover(sims[(a, b, c)].exposure, pre)
                s["eps"], s["ep_weeks"] = _episodes_ok(sims[(a, b, c)])
                res = sims[(a, b, c)]
                s["miss_frac"] = res.funding_missing / max(res.slot_weeks, 1)
                stats[a] = s
            if idx is not None:
                fam = adjust_family([stats[a]["p"] for a in NAMES])
                for a, ph in zip(NAMES, fam.holm_adjusted, strict=True):
                    stats[a]["holm"] = float(ph)
            out["cells"][(b, c)] = stats
    out["verdicts"] = {a: verdict(out, a) for a in NAMES}
    return out


def floors_ok(s: dict, a: str, n_weeks: int) -> tuple[bool, str]:
    if n_weeks < MIN_WEEKS:
        return False, f"{n_weeks} semanas < {MIN_WEEKS}"
    if s["miss_frac"] > 0.01:
        return False, f"funding ausente em {s['miss_frac']:.2%} das vaga-semanas"
    tot, pre_n, post_n = s["cover"]
    if tot < 15 or pre_n < 5 or post_n < 5:
        return False, f"cobertura {tot} blocos de 13 sem. ({pre_n} antes, {post_n} depois)"
    if a != "A0" and (s["eps"] < 30 or s["ep_weeks"] < 10):
        return False, f"{s['eps']} episódios em {s['ep_weeks']} semanas de entrada"
    return True, ""


def cell_confirms(s: dict) -> bool:
    return bool(s["ann"] >= MRE_ANN and s["lo"] > 0 and s["holm"] < 0.05 and s["split"] and s["plateau"])


def verdict(out: dict, a: str) -> tuple[str, str]:
    cells = [out["cells"][(b, c)][a] for b in BOUNDS for c in CONVS]
    for s in cells:
        ok, why = floors_ok(s, a, out["n_weeks"])
        if not ok:
            return "NÃO CONFIRMA — LIMITE DE DADO", why
    if all(cell_confirms(s) for s in cells):
        return "CONFIRMA", "todas as cláusulas nos dois limites e nas duas convenções de fronteira"
    if all(s["hi"] < MRE_ANN for s in cells):
        return "REFUTA", "IC superior < 5 % a.a. nos dois limites e nas duas convenções"
    return "NÃO CONFIRMA", "nem todas as cláusulas, e o IC não exclui 5 % a.a. em todas as células"


def without_symbols(mk: Market, syms: set[str]) -> Market:
    return dataclasses.replace(mk, excluded_syms=frozenset(syms), _seg_cache={})


def by_year(r: np.ndarray, days: np.ndarray) -> dict[int, tuple[float, int]]:
    years = np.array([(dt.date(1970, 1, 1) + dt.timedelta(days=int(d))).year for d in days])
    return {int(y): (52 * float(np.mean(r[years == y])), int(np.sum(years == y))) for y in np.unique(years)}


def max_dd(r: np.ndarray) -> float:
    eq = np.concatenate(([0.0], np.cumsum(r)))
    return float(np.min(eq - np.maximum.accumulate(eq)))


def episode_stats(res, reps: int = REPS) -> dict:
    eps = [e for e in res.episodes]
    if not eps:
        return {"n": 0}
    x = np.array([e["ret"] for e in eps])
    k0 = np.array([e["k0"] for e in eps])
    groups = [x[k0 == g] for g in np.unique(k0)]
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(groups), size=(reps, len(groups)))
    sums = np.array([g.sum() for g in groups])
    cnts = np.array([g.size for g in groups])
    boot = sums[draws].sum(axis=1) / cnts[draws].sum(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"n": int(x.size), "mean": float(x.mean()), "median": float(np.median(x)), "pos": float(np.mean(x > 0)),
            "lo": float(lo), "hi": float(hi), "weeks": float(np.mean([e["k1"] - e["k0"] for e in eps])),
            "censored": int(sum(e["censored"] for e in eps))}
