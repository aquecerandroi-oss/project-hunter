"""R90 réplica — caminho INDEPENDENTE da manchete da H-033 (não importa nada de data90/analysis90/stats90).

- oi_rel7d recalculado de `cache/oi_raw.csv` (SELECT cru de open_interest_history) com busca binária em NumPy;
- unidades montadas de novo a partir de feat2_15.csv (só obs, emitted, mercado, ATR, velas) + out.csv;
- OLS por equações normais (np.linalg.solve), escala robusta recalculada;
- bootstrap de clusters de dia com gerador e laço próprios (semente diferente: o IC deve concordar, não coincidir).

cd .claude/state/r90/replica && uv run --no-sync --project C:/dev/project-hunter python replica90.py > out_replica.txt
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
UP = HERE.parent / "cache"
SLACK_S = 15 * 60
STALE_S = 10 * 60
WEEK_S = 7 * 86400
MIN_N = 1815
FROZEN = "e597cabf49f9a8e7beee21535dd218e2c3d9065b34264f70a4c086af658dd4dd"


def epoch(text: str) -> float:
    t = text.strip().replace(" ", "T")
    if t.endswith("+00"):
        t += ":00"
    d = datetime.fromisoformat(t)
    if d.tzinfo is None:
        raise ValueError("instante ingênuo")
    return d.timestamp()


def load_oi(path: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    acc: dict[str, list[tuple[float, float]]] = defaultdict(list)
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            acc[r["market_id"]].append((epoch(r["ts"]), float(r["open_interest"])))
    out = {}
    for m, v in acc.items():
        v.sort()
        out[m] = (np.array([a for a, _ in v]), np.array([b for _, b in v]))
    return out


def oi_rel(tsa: np.ndarray, oia: np.ndarray, obs: float) -> float | None:
    """Leitura = último bucket com ts ≤ obs − 15 min; janela (cur − 7 d, cur]; mediana de ln OI (OI > 0)."""
    j = int(np.searchsorted(tsa, obs - SLACK_S, side="right")) - 1
    if j < 0 or oia[j] <= 0 or tsa[j] < obs - SLACK_S - STALE_S:
        return None
    cur = tsa[j]
    i = int(np.searchsorted(tsa, cur - WEEK_S, side="right"))
    w = oia[i:j + 1]
    w = w[w > 0]
    if w.size < MIN_N:
        return None
    return float(math.log(oia[j]) - np.median(np.log(w)))


def rz(v: np.ndarray) -> np.ndarray:
    med = np.median(v)
    return (v - med) / (1.4826 * np.median(np.abs(v - med)))


def ols(y: np.ndarray, cols: list[np.ndarray]) -> np.ndarray:
    a = np.column_stack([np.ones(len(y)), *cols])
    return np.linalg.solve(a.T @ a, a.T @ y)


def main() -> None:
    assert hashlib.sha256((UP / "eligible.csv").read_bytes()).hexdigest() == FROZEN
    elig = {r["signal_id"] for r in csv.DictReader((UP / "eligible.csv").open(encoding="utf-8"))
            if r["strategy"] == "momentum"}
    rn = {r["signal_id"]: r["r_multiple"] for r in csv.DictReader((UP / "out.csv").open(encoding="utf-8"))}
    oi = load_oi(HERE / "cache" / "oi_raw.csv")
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    miss = 0
    for r in csv.DictReader((UP / "feat2_15.csv").open(encoding="utf-8")):
        if r["signal_id"] not in elig or not rn.get(r["signal_id"]):
            continue
        obs = epoch(r["obs"])
        v = oi_rel(*oi[r["market_id"]], obs) if r["market_id"] in oi else None
        if v is None:
            miss += 1
            continue
        c, lo, c240 = float(r["close_last"]), float(r["lo24"]), float(r["close_m240"])
        groups[(r["market_id"], r["obs"])].append({
            "r": float(rn[r["signal_id"]]), "atr": float(r["env_atr_pct"]), "rel": v,
            "dlow": c / lo - 1, "r4": c / c240 - 1,
            "day": datetime.fromtimestamp(obs, tz=timezone.utc).date().isoformat(),
        })
    us = [{**g[0], "r": float(np.mean([x["r"] for x in g])), "atr": float(np.mean([x["atr"] for x in g]))}
          for g in groups.values()]
    y = np.array([u["r"] for u in us])
    cols = [rz(-np.array([u["rel"] for u in us])), *[rz(np.array([u[k] for u in us])) for k in ("dlow", "atr", "r4")]]
    beta = ols(y, cols)
    days = sorted({u["day"] for u in us})
    di = {d: np.array([i for i, u in enumerate(us) if u["day"] == d]) for d in days}
    rng = np.random.default_rng(90)
    draws = []
    for _ in range(10_000):
        idx = np.concatenate([di[days[k]] for k in rng.integers(0, len(days), len(days))])
        draws.append(ols(y[idx], [c[idx] for c in cols])[1])
    lo95, hi95 = np.percentile(draws, [2.5, 97.5])
    fav = y[np.array([u["rel"] < 0 for u in us])]
    print("# R90 réplica independente (oi_rel7d do OI cru; OLS por equações normais; bootstrap de dia próprio, semente 90)")
    print(f"unidades {len(us)} | dias {len(days)} | mercados {len({k[0] for k in groups})} | sinais sem variável na réplica {miss}")
    print(f"β_x = {beta[1]:+.4f} R/desvio | IC dia [{lo95:+.4f}, {hi95:+.4f}] | nível oi_rel7d<0 {fav.mean():+.4f} (n {fav.size})"
          f" | ≥0 {y[np.array([u['rel'] >= 0 for u in us])].mean():+.4f} | todos {y.mean():+.4f}")
    print("coeficientes [b0, x, d_low, ATR%, ret4h]:", " ".join(f"{b:+.4f}" for b in beta))


if __name__ == "__main__":
    main()
