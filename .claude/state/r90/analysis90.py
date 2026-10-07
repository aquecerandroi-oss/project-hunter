"""R90 / H-033 — análise de uma estratégia sobre as unidades (adaptado do R86): primária, patamar, metades,
secundária, diagnósticos, e as robustezes pré-registradas pela emenda (FE dia, FE mercado+dia, blocos de calendário).

x = −oi_rel7d (favorável = alto). Grupo favorável = x > 0 ⇔ oi_rel7d < 0. Corte c: 1[x > c] ⇔ oi_rel7d < −c.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from stats90 import (CUTS, MIN_DAYS, MIN_GROUP, MIN_UNITS, REPS, SEED, Unidentified, cluster_boot, fit, fit_checked,
                     robust_z, sign_plateau, verdict)

COV = ("d_low", "atr_pct", "ret4h")
VARS = ("x", *COV)


def scales(us: list[dict]) -> dict[str, tuple[float, float]]:
    out = {}
    for v in VARS:
        x = np.array([u[v] for u in us], float)
        robust_z(x)  # levanta se MAD = 0
        med = float(np.median(x))
        out[v] = (med, float(np.median(np.abs(x - med))) * 1.4826)
    return out


def design(us: list[dict], sc: dict[str, tuple[float, float]]) -> np.ndarray:
    return np.column_stack([(np.array([u[v] for u in us], float) - sc[v][0]) / sc[v][1] for v in VARS])


def beta_or_nan(y: np.ndarray, x: np.ndarray, col: int = 1) -> float:
    try:
        return float(fit_checked(y, x)[col])
    except Unidentified:
        return float("nan")


def dummies(keys: list[str]) -> np.ndarray:
    lv = sorted(set(keys))[1:]
    return np.column_stack([[1.0 if k == v else 0.0 for k in keys] for v in lv])


def calendar_block_ci(y: np.ndarray, x: np.ndarray, days: list[str], length: int, col: int = 1,
                      reps: int = 2000, fe: tuple[list[str], ...] = ()) -> tuple[float, float, int]:
    """Blocos móveis de `length` dias de calendário (todos os mercados do dia juntos); FE refeitos por réplica."""
    d0 = date.fromisoformat(min(days))
    cal = [(d0 + timedelta(days=i)).isoformat() for i in range((date.fromisoformat(max(days)) - d0).days + 1)]
    arr = np.array(days)
    members = {d: np.flatnonzero(arr == d) for d in cal}
    k, rng, draws, bad = len(cal), np.random.default_rng(SEED), [], 0
    for _ in range(reps):
        picked: list[str] = []
        while len(picked) < k:
            s = int(rng.integers(0, k - length + 1))
            picked += cal[s:s + length]
        idx = np.concatenate([members[d] for d in picked[:k]])
        xi = x[idx]
        for keys in fe:
            sub = [keys[j] for j in idx]
            if len(set(sub)) > 1:
                xi = np.column_stack([xi, dummies(sub)])
        a = np.column_stack([np.ones(idx.size), xi])
        if idx.size == 0 or np.linalg.matrix_rank(a) < a.shape[1]:
            bad += 1
            continue
        draws.append(fit(y[idx], xi)[col])
    if not draws:
        return float("nan"), float("nan"), bad
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(lo), float(hi), bad


def boot_mean(y: np.ndarray, days: list[str], reps: int = REPS) -> tuple[float, float]:
    _, lo, hi, _, _ = cluster_boot(y, np.zeros((len(y), 0)), days, col=0, reps=reps)
    return lo, hi


def analyze(us: list[dict], reps: int = REPS, robust: bool = True) -> dict:
    n, days = len(us), sorted({u["day"] for u in us})
    pos = [u for u in us if u["x"] > 0]
    neg = [u for u in us if u["x"] <= 0]
    res: dict = {"n": n, "days": len(days), "n_pos": len(pos), "n_neg": len(neg),
                 "markets": len({u["market"] for u in us})}
    if n < MIN_UNITS or len(days) < MIN_DAYS or min(len(pos), len(neg)) < MIN_GROUP:
        res["below_floor"] = True
        res["p_raw"] = 1.0
        return res
    y = np.array([u["r"] for u in us], float)
    try:
        sc = scales(us)
        x = design(us, sc)
        coef = fit_checked(y, x)
    except (Unidentified, ValueError) as exc:
        res["erro_instrumento"] = str(exc)
        res["p_raw"] = 1.0
        return res
    dlist, mlist = [u["day"] for u in us], [u["market"] for u in us]
    b, lo, hi, p_d, bad_d = cluster_boot(y, x, dlist, reps=reps)
    _, lo_m, hi_m, p_m, bad_m = cluster_boot(y, x, mlist, reps=reps)
    res.update(coef=coef.tolist(), beta=b, lo=lo, hi=hi, p_day=p_d, lo_m=lo_m, hi_m=hi_m, p_mkt=p_m,
               invalid_frac=max(bad_d, bad_m) / reps, p_raw=max(p_d, p_m), scale=sc)
    cut_b, parts = [], []
    for c in CUTS:
        xi = x.copy()
        xi[:, 0] = np.array([1.0 if u["x"] > c else 0.0 for u in us])
        cut_b.append(beta_or_nan(y, xi))
        parts.append(int(xi[:, 0].sum()))
    res["cuts"] = list(zip(CUTS, cut_b, parts, strict=True))
    res["cuts_invalid"] = sum(1 for v in cut_b if not np.isfinite(v))
    res["plateau_run"], res["plateau"] = sign_plateau(cut_b, parts)
    k = math.ceil(len(days) / 2)
    first = set(days[:k])
    h = []
    for inside in (True, False):
        idx = np.array([(u["day"] in first) == inside for u in us])
        half = [u for u, k in zip(us, idx, strict=True) if k]
        try:
            for v in VARS:  # escala global mantida; a metade só precisa ter dispersão própria (falha fechada)
                robust_z(np.array([u[v] for u in half], float))
        except ValueError:
            h.append(math.nan)
            continue
        h.append(beta_or_nan(y[idx], x[idx]) if idx.sum() > 5 else math.nan)
    res["halves"] = tuple(h)
    res["half_sizes"] = (int(sum(u["day"] in first for u in us)), int(sum(u["day"] not in first for u in us)))
    ypos = np.array([u["r"] for u in pos], float)
    res["level_pos"], res["level_neg"] = float(ypos.mean()), float(np.mean([u["r"] for u in neg]))
    res["level_pos_ci"] = boot_mean(ypos, [u["day"] for u in pos], reps=reps)
    res["level_all"] = float(y.mean())
    xs = x.copy()
    xs[:, 0] = np.array([1.0 if u["x"] > 0 else 0.0 for u in us])
    res["sec"] = cluster_boot(y, xs, dlist, reps=reps)[:4]
    res["cov"] = {v: cluster_boot(y, x, dlist, col=i + 2, reps=reps)[:3] for i, v in enumerate(COV)}
    a = np.column_stack([np.ones(n), x])
    res["cond"] = float(np.linalg.cond(a))
    other = np.column_stack([np.ones(n), x[:, 1:]])
    resid = x[:, 0] - other @ np.linalg.lstsq(other, x[:, 0], rcond=None)[0]
    res["resid_share"] = float(resid.std() / x[:, 0].std())
    res["concentration"] = (max(mlist.count(m) for m in set(mlist)) / n, max(dlist.count(d) for d in set(dlist)) / n)
    ma, da = np.array(mlist), np.array(dlist)
    lomo = [beta_or_nan(y[ma != m], x[ma != m]) for m in sorted(set(mlist))]
    lodo = [beta_or_nan(y[da != d], x[da != d]) for d in days]
    res["loo"] = ((float(np.nanmin(lomo)), float(np.nanmax(lomo))), (float(np.nanmin(lodo)), float(np.nanmax(lodo))))
    if robust:
        rob = {}
        for name, fe in (("FE mercado", (mlist,)), ("FE dia", (dlist,)), ("FE mercado+dia", (mlist, dlist))):
            xf = np.column_stack([x, *[dummies(kk) for kk in fe]])
            rob[name] = (beta_or_nan(y, xf), *calendar_block_ci(y, x, dlist, 3, fe=fe))
        for length in (3, 5, 7):
            rob[f"blocos {length} d"] = (b, *calendar_block_ci(y, x, dlist, length))
        res["robust"] = rob
    return res


def label(res: dict, p_holm: float, slack: tuple[float, float] | None = None) -> object:
    """Rótulo do registro + emenda. `slack` = (β_x na folga 30, β_x na folga 60): CONFIRMA exige os dois > 0."""
    lab = _label(res, p_holm)
    if lab.label == "CONFIRMA":  # type: ignore[attr-defined]
        ok = slack is not None and all(np.isfinite(b) and b > 0 for b in slack)
        lab.clauses["folgas_30_60>0"] = ok  # type: ignore[attr-defined]
        if not ok:
            return type(lab)("NÃO CONFIRMA", lab.clauses)  # type: ignore[attr-defined]
    return lab


def _label(res: dict, p_holm: float) -> object:
    nan = math.nan
    if "below_floor" in res or "erro_instrumento" in res:
        return verdict(n=res["n"], days=res["days"], n_pos=res["n_pos"], n_neg=res["n_neg"], beta=nan, lo=nan,
                       hi=nan, lo_m=nan, hi_m=nan, p_holm=1.0, level_pos=nan, plateau=False, halves=(nan, nan),
                       invalid_frac=1.0)
    bad_cut = res.get("cuts_invalid", 0) > 0  # corte não identificável bloqueia o rótulo (inclusive o REFUTA)
    return verdict(n=res["n"], days=res["days"], n_pos=res["n_pos"], n_neg=res["n_neg"], beta=res["beta"],
                   lo=res["lo"], hi=res["hi"], lo_m=res["lo_m"], hi_m=res["hi_m"], p_holm=p_holm,
                   level_pos=res["level_pos"], plateau=res["plateau"], halves=res["halves"],
                   invalid_frac=1.0 if bad_cut else res["invalid_frac"])


def render(name: str, res: dict, lab: object, p_holm: float) -> list[str]:
    out = [f"\n## {name}: n {res['n']} unidades | {res['days']} dias | {res['markets']} mercados | "
           f"oi_rel7d<0 {res['n_pos']} · ≥0 {res['n_neg']}"]
    if "beta" in res:
        b0, bx, bl, ba, b4 = res["coef"]
        out += [
            f"modelo conjunto (z robusto): b0 {b0:+.4f} | x=−oi_rel7d {bx:+.4f} | d_low {bl:+.4f} | ATR% {ba:+.4f} | ret4h {b4:+.4f}",
            f"PRIMÁRIA β_x = {res['beta']:+.4f} R/desvio (β de oi_rel7d = {-res['beta']:+.4f}) | IC dia [{res['lo']:+.4f}, {res['hi']:+.4f}]"
            f" p {res['p_day']:.4f} | IC mercado [{res['lo_m']:+.4f}, {res['hi_m']:+.4f}] p {res['p_mkt']:.4f}"
            f" | p do portão {res['p_raw']:.4f} | Holm {p_holm:.4f} | réplicas inválidas {res['invalid_frac']:.4%}",
            f"nível: oi_rel7d<0 {res['level_pos']:+.4f} R (IC dia [{res['level_pos_ci'][0]:+.4f}, {res['level_pos_ci'][1]:+.4f}])"
            f" | ≥0 {res['level_neg']:+.4f} | todos {res['level_all']:+.4f}",
            "patamar 1[oi_rel7d < c]: " + " · ".join(f"c={-c:+.2f}: β {bb:+.4f} (n {p})" for c, bb, p in res["cuts"])
            + f" → sequência {res['plateau_run']} → {'patamar' if res['plateau'] else 'sem patamar'}",
            f"metades por data (n {res['half_sizes'][0]}/{res['half_sizes'][1]}): β_x {res['halves'][0]:+.4f} / {res['halves'][1]:+.4f}",
            f"secundária 1[oi_rel7d<0] ajustada: {res['sec'][0]:+.4f} [{res['sec'][1]:+.4f}, {res['sec'][2]:+.4f}] p {res['sec'][3]:.4f}",
            "covariáveis (IC dia): " + " · ".join(f"{v} {bb:+.4f} [{lo:+.4f}, {hi:+.4f}]" for v, (bb, lo, hi) in res["cov"].items()),
            f"diagnósticos: cond {res['cond']:.2f} | fração de x não explicada {res['resid_share']:.3f}"
            f" | maior mercado {res['concentration'][0]:.1%} · maior dia {res['concentration'][1]:.1%}"
            f" | β sem cada mercado [{res['loo'][0][0]:+.4f}, {res['loo'][0][1]:+.4f}] · sem cada dia [{res['loo'][1][0]:+.4f}, {res['loo'][1][1]:+.4f}]",
        ]
        if "robust" in res:
            out.append("robustez pré-registrada (IC por blocos de calendário, 2 000): " + " · ".join(
                f"{k} β {v[0]:+.4f} [{v[1]:+.4f}, {v[2]:+.4f}] inv {v[3]}" for k, v in res["robust"].items()))
    if "erro_instrumento" in res:
        out.append(f"instrumento: {res['erro_instrumento']}")
    out.append(f"RÓTULO {name}: {lab.label}  | cláusulas {lab.clauses}")  # type: ignore[attr-defined]
    return out
