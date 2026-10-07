"""R90 / H-033 — passo cego 2 (sem desfechos): redundância, sobreposição com o R86, fatia pós-R86, datas por grupo."""

from __future__ import annotations

import csv
from collections import Counter

import numpy as np
from data90 import load_rows, units

POST_R86 = "2026-10-01T03:06:15+00:00"


def spearman(a: list[float], b: list[float]) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def main() -> None:
    rows = load_rows()
    with open("../r86/cache/eligible.csv", encoding="utf-8") as fh:
        r86 = {r["signal_id"] for r in csv.DictReader(fh)}
    for strat in ("momentum", "mean_reversion", "mean_reversion_h1"):
        rs = [dict(r, r=0.0) for r in rows if r["strategy"] == strat and r["has_r"]]  # r fictício: só p/ agrupar
        us = units(rs)
        if not us:
            continue
        x = [u["x"] for u in us]
        print(f"## {strat}: unidades {len(us)}")
        for v in ("d_low", "ret4h", "atr_pct"):
            print(f"   Spearman(oi_rel7d, {v}) = {-spearman(x, [u[v] for u in us]):+.3f}")
        ov = [r for r in rs if r["x"] is not None and r["oi_vol"] is not None]
        print(f"   Spearman(oi_rel7d, oi_vol) = {spearman([-r['x'] for r in ov], [r['oi_vol'] for r in ov]):+.3f} (sinais)")
        fav = [u for u in us if u["x"] > 0]
        bad = [u for u in us if u["x"] <= 0]
        print(f"   grupos: oi_rel7d<0 {len(fav)} unidades em {len({u['day'] for u in fav})} datas | "
              f"≥0 {len(bad)} em {len({u['day'] for u in bad})} datas")
        days = sorted({u["day"] for u in us})
        k = (len(days) + 1) // 2
        print(f"   metades: {days[0]}..{days[k-1]} ({sum(u['day'] in days[:k] for u in us)}) × "
              f"{days[k]}..{days[-1]} ({sum(u['day'] in days[k:] for u in us)})")
        sig = [r for r in rs if r["x"] is not None]
        print(f"   sinais completos que estavam na lista elegível do R86: {sum(r['signal_id'] in r86 for r in sig)} de {len(sig)}")
        post = [u for u in us if u["t"].isoformat() > POST_R86]
        print(f"   pós-R86 (emitidas depois de {POST_R86}): {len(post)} unidades, {len({u['day'] for u in post})} dias, "
              f"oi_rel7d<0 {sum(u['x'] > 0 for u in post)}")
        print(f"   verificadas no outbox: {sum(u['verified'] for u in us)}")
        print("   cortes (n com oi_rel7d < c): " + " · ".join(
            f"c={c:+.2f}: {sum(-u['x'] < c for u in us)}" for c in (-0.04, -0.02, 0.0, 0.02, 0.04)))
        print("   por mercado:", dict(Counter(r["symbol"] for r in sig).most_common(16)))


if __name__ == "__main__":
    main()
