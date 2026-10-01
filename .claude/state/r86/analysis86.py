"""R86 / H-027 — análise de uma estratégia sobre as unidades: primária, patamar, metades, secundária, diagnósticos.

Usada igual pela fumaça sintética (`smoke86.py`) e pela corrida real (`run86.py`).
"""

from __future__ import annotations

import math

import numpy as np
from stats86 import (CUTS, MIN_DAYS, MIN_GROUP, MIN_UNITS, REPS, Unidentified, cluster_boot, fit_checked,
                     robust_z, sign_plateau, verdict)

COV = ("d_low", "atr_pct", "ret4h")


def design(us: list[dict], scale: dict[str, tuple[float, float]] | None = None) -> np.ndarray:
    """Colunas: z(razao), z(d_low), z(ATR%), z(ret4h), com mediana/MAD congelados em `scale`."""
    cols = []
    for v in ("razao", *COV):
        x = np.array([u[v] for u in us], float)
        med, mad = scale[v] if scale else (0.0, 1.0)
        cols.append((x - med) / mad)
    return np.column_stack(cols)


def scales(us: list[dict]) -> dict[str, tuple[float, float]]:
    out = {}
    for v in ("razao", *COV):
        x = np.array([u[v] for u in us], float)
        robust_z(x)  # levanta se MAD = 0
        med = float(np.median(x))
        out[v] = (med, float(np.median(np.abs(x - med))) * 1.4826)
    return out


def beta_or_nan(y: np.ndarray, x: np.ndarray, col: int = 1) -> float:
    try:
        return float(fit_checked(y, x)[col])
    except Unidentified:
        return float("nan")


def boot_mean(y: np.ndarray, days: list[str], reps: int = REPS, seed: int = 20261001) -> tuple[float, float]:
    x = np.zeros((len(y), 0))
    _, lo, hi, _, _ = cluster_boot(y, x, days, col=0, reps=reps, seed=seed)
    return lo, hi


def analyze(us: list[dict], reps: int = REPS) -> dict:
    """Tudo o que o rótulo de uma estratégia precisa, mais diagnósticos que não decidem."""
    n, days = len(us), sorted({u["day"] for u in us})
    pos = [u for u in us if u["razao"] > 0]
    neg = [u for u in us if u["razao"] <= 0]
    res: dict = {"n": n, "days": len(days), "n_pos": len(pos), "n_neg": len(neg),
                 "markets": len({u["market"] for u in us})}
    if n < MIN_UNITS or len(days) < MIN_DAYS or min(len(pos), len(neg)) < MIN_GROUP:
        res["verdict"] = verdict(n=n, days=len(days), n_pos=len(pos), n_neg=len(neg), beta=math.nan, lo=math.nan,
                                 hi=math.nan, lo_m=math.nan, hi_m=math.nan, p_holm=1.0, level_pos=math.nan,
                                 plateau=False, halves=(math.nan, math.nan), invalid_frac=1.0)
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
    # patamar: razão trocada por 1[razao > c]
    cut_b, parts = [], []
    for c in CUTS:
        xi = x.copy()
        xi[:, 0] = np.array([1.0 if u["razao"] > c else 0.0 for u in us])
        cut_b.append(beta_or_nan(y, xi))
        parts.append(int(xi[:, 0].sum()))
    res["cuts"] = list(zip(CUTS, cut_b, parts, strict=True))
    res["cuts_invalid"] = sum(1 for v in cut_b if not np.isfinite(v))
    res["plateau_run"], res["plateau"] = sign_plateau(cut_b, parts)
    # metades por data
    k = math.ceil(len(days) / 2)
    first = set(days[:k])
    h = []
    for inside in (True, False):
        idx = np.array([(u["day"] in first) == inside for u in us])
        h.append(beta_or_nan(y[idx], x[idx]) if idx.sum() > 5 else math.nan)
    res["halves"] = tuple(h)
    res["half_sizes"] = (int(sum(u["day"] in first for u in us)), int(sum(u["day"] not in first for u in us)))
    # nível
    ypos = np.array([u["r"] for u in pos], float)
    res["level_pos"], res["level_neg"] = float(ypos.mean()), float(np.mean([u["r"] for u in neg]))
    res["level_pos_ci"] = boot_mean(ypos, [u["day"] for u in pos], reps=reps)
    res["level_all"] = float(y.mean())
    # secundária: 1[razao > 0] no modelo conjunto
    xs = x.copy()
    xs[:, 0] = np.array([1.0 if u["razao"] > 0 else 0.0 for u in us])
    res["sec"] = cluster_boot(y, xs, dlist, reps=reps)[:4]
    # covariáveis (descritivo) com IC por dia
    res["cov"] = {v: cluster_boot(y, x, dlist, col=i + 2, reps=reps)[:3] for i, v in enumerate(COV)}
    # diagnósticos
    a = np.column_stack([np.ones(n), x])
    res["cond"] = float(np.linalg.cond(a))
    zr = x[:, 0]
    other = np.column_stack([np.ones(n), x[:, 1:]])
    resid = zr - other @ np.linalg.lstsq(other, zr, rcond=None)[0]
    res["resid_share"] = float(resid.std() / zr.std())
    share_m = max(mlist.count(m) for m in set(mlist)) / n
    share_d = max(dlist.count(d) for d in set(dlist)) / n
    res["concentration"] = (share_m, share_d)
    lomo = [beta_or_nan(y[np.array(mlist) != m], x[np.array(mlist) != m]) for m in sorted(set(mlist))]
    lodo = [beta_or_nan(y[np.array(dlist) != d], x[np.array(dlist) != d]) for d in days]
    res["loo"] = ((float(np.nanmin(lomo)), float(np.nanmax(lomo))), (float(np.nanmin(lodo)), float(np.nanmax(lodo))))
    return res


def label(res: dict, p_holm: float) -> object:
    if "erro_instrumento" in res:
        return verdict(n=res["n"], days=res["days"], n_pos=res["n_pos"], n_neg=res["n_neg"], beta=math.nan,
                       lo=math.nan, hi=math.nan, lo_m=math.nan, hi_m=math.nan, p_holm=1.0, level_pos=math.nan,
                       plateau=False, halves=(math.nan, math.nan), invalid_frac=1.0)
    if "verdict" in res:
        return res["verdict"]
    bad_cut = res.get("cuts_invalid", 0) > 0  # emenda 03:02Z item 2: corte não identificável bloqueia o rótulo
    return verdict(n=res["n"], days=res["days"], n_pos=res["n_pos"], n_neg=res["n_neg"], beta=res["beta"],
                   lo=res["lo"], hi=res["hi"], lo_m=res["lo_m"], hi_m=res["hi_m"], p_holm=p_holm,
                   level_pos=res["level_pos"], plateau=res["plateau"], halves=res["halves"],
                   invalid_frac=1.0 if bad_cut else res["invalid_frac"])


def render(name: str, res: dict, lab: object, p_holm: float) -> list[str]:
    out = [f"\n## {name}: n {res['n']} unidades | {res['days']} dias | {res['markets']} mercados | "
           f"razão>0 {res['n_pos']} · ≤0 {res['n_neg']}"]
    if "beta" in res:
        b0, br, bl, ba, b4 = res["coef"]
        out += [
            f"modelo conjunto (z robusto): b0 {b0:+.4f} | razão {br:+.4f} | d_low {bl:+.4f} | ATR% {ba:+.4f} | ret4h {b4:+.4f}",
            f"PRIMÁRIA β_razao = {res['beta']:+.4f} R/desvio | IC dia [{res['lo']:+.4f}, {res['hi']:+.4f}] p {res['p_day']:.4f}"
            f" | IC mercado [{res['lo_m']:+.4f}, {res['hi_m']:+.4f}] p {res['p_mkt']:.4f} | p do portão {res['p_raw']:.4f}"
            f" | Holm {p_holm:.4f} | réplicas inválidas {res['invalid_frac']:.4%}",
            f"nível: razão>0 {res['level_pos']:+.4f} R (IC dia [{res['level_pos_ci'][0]:+.4f}, {res['level_pos_ci'][1]:+.4f}])"
            f" | razão≤0 {res['level_neg']:+.4f} | todos {res['level_all']:+.4f}",
            "patamar 1[razão>c]: " + " · ".join(f"c={c:+.3f}: β {b:+.4f} (n>c {p})" for c, b, p in res["cuts"])
            + f" → sequência {res['plateau_run']} → {'patamar' if res['plateau'] else 'sem patamar'}",
            f"metades por data (n {res['half_sizes'][0]}/{res['half_sizes'][1]}): β {res['halves'][0]:+.4f} / {res['halves'][1]:+.4f}",
            f"secundária 1[razão>0] ajustada: {res['sec'][0]:+.4f} [{res['sec'][1]:+.4f}, {res['sec'][2]:+.4f}] p {res['sec'][3]:.4f}",
            "covariáveis (IC dia, descritivo): " + " · ".join(f"{v} {b:+.4f} [{lo:+.4f}, {hi:+.4f}]" for v, (b, lo, hi) in res["cov"].items()),
            f"diagnósticos: cond {res['cond']:.2f} | fração da razão não explicada pelos controles {res['resid_share']:.3f}"
            f" | maior mercado {res['concentration'][0]:.1%} · maior dia {res['concentration'][1]:.1%}"
            f" | β sem cada mercado [{res['loo'][0][0]:+.4f}, {res['loo'][0][1]:+.4f}] · sem cada dia [{res['loo'][1][0]:+.4f}, {res['loo'][1][1]:+.4f}]",
        ]
    if "erro_instrumento" in res:
        out.append(f"instrumento: {res['erro_instrumento']}")
    out.append(f"RÓTULO {name}: {lab.label}  | cláusulas {lab.clauses}")  # type: ignore[attr-defined]
    return out
