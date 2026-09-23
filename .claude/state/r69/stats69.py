"""R69 — Teste A (percentil vs absoluto) e Teste B (estado da coorte).

Disciplina herdada do R65/R67: contraste por metades, bootstrap em BLOCOS de 60 min
(Astra: bootstrap por mint trata moedas simultaneas como independentes), permutacao
estratificada por dia para comparabilidade, Benjamini-Hochberg e Benjamini-Yekutieli
sobre a familia congelada de 17 hipoteses, planalto-vs-pico e split temporal.
"""

from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta

import numpy as np

RNG = np.random.default_rng(20260923)
REPS = 10000
BLOCK = timedelta(minutes=60)

PCT_VARS = [
    ("p_age", "idade"),
    ("p_prog", "progresso da curva"),
    ("p_dprog", "delta de progresso 60s"),
    ("p_mcap", "market cap"),
    ("p_dmcap", "delta de mcap 60s"),
    ("p_buys", "compras 60s"),
    ("p_sells", "vendas 60s"),
    ("p_sb", "vendas/compras"),
    ("p_ub", "compradores unicos 60s"),
    ("p_flow", "fluxo liquido SOL 60s"),
    ("p_vol", "volume 60s"),
    ("p_snip", "snipers"),
    ("p_dev", "dev share"),
]
ABS_OF = {
    "p_age": "age_s", "p_prog": "curve_progress_pct", "p_dprog": "progress_delta_60s",
    "p_mcap": "mcap_sol", "p_dmcap": "mcap_delta_60s", "p_buys": "buys_60s",
    "p_sells": "sells_60s", "p_sb": "sell_buy", "p_ub": "unique_buyers_60s",
    "p_flow": "net_sol_flow_60s", "p_vol": "curve_volume_60s_sol", "p_snip": "snipers",
    "p_dev": "dev_share",
}


def load(path: str = "pct.csv") -> list[dict]:
    """Carrega as decisoes.

    CORRECAO (Astra, revisao do veredito): o `FILTER` do SQL so testava o membro da
    coorte; sujeito sem valor caia no `ELSE 0.0` e recebia percentil ZERO em vez de
    indisponivel. Aqui o percentil e anulado sempre que o valor ABSOLUTO do sujeito
    esta ausente, o que tambem alinha a amostra do contraste relativo com a do absoluto.
    """
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        r["t"] = datetime.fromisoformat(r["t"])
        r["ret"] = float(r["pnl_sol"]) / float(r["size_sol"])
        for k, _ in PCT_VARS:
            if r[ABS_OF[k]] == "":
                r[k] = ""
        rows.append(r)
    return rows


def blocks(rows: list[dict]) -> np.ndarray:
    t0 = min(r["t"] for r in rows)
    return np.array([int((r["t"] - t0) / BLOCK) for r in rows])


def diff_means(ret: np.ndarray, hi: np.ndarray) -> float:
    if hi.sum() == 0 or (~hi).sum() == 0:
        return float("nan")
    return float(ret[hi].mean() - ret[~hi].mean())


def block_bootstrap(ret: np.ndarray, hi: np.ndarray, blk: np.ndarray) -> tuple:
    uniq = np.unique(blk)
    idx_by_block = {b: np.flatnonzero(blk == b) for b in uniq}
    out = np.empty(REPS)
    for i in range(REPS):
        pick = RNG.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_block[b] for b in pick])
        d = diff_means(ret[idx], hi[idx])
        out[i] = d
    out = out[~np.isnan(out)]
    if out.size == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    lo, up = np.percentile(out, [2.5, 97.5])
    p_le0 = float((out <= 0).mean())
    p_two = 2 * min(p_le0, 1 - p_le0)
    return float(lo), float(up), p_le0, min(1.0, p_two)


def perm_p(ret: np.ndarray, hi: np.ndarray, day: np.ndarray) -> float:
    obs = abs(diff_means(ret, hi))
    cnt = 0
    for _ in range(REPS):
        perm = hi.copy()
        for d in np.unique(day):
            m = day == d
            perm[m] = RNG.permutation(hi[m])
        if abs(diff_means(ret, perm)) >= obs - 1e-15:
            cnt += 1
    return (cnt + 1) / (REPS + 1)


def bh(ps: list[float], q: float = 0.10) -> list[bool]:
    n = len(ps)
    order = np.argsort(ps)
    thr = [(i + 1) / n * q for i in range(n)]
    keep = [False] * n
    kmax = -1
    for i, j in enumerate(order):
        if ps[j] <= thr[i]:
            kmax = i
    for i, j in enumerate(order):
        if i <= kmax:
            keep[j] = True
    return keep


def by(ps: list[float], q: float = 0.10) -> list[bool]:
    n = len(ps)
    c = sum(1 / (i + 1) for i in range(n))
    return bh(ps, q / c)
