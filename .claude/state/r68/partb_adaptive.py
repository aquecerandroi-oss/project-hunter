"""R68 parte B (secundária, E1.5) — walk-forward com limiar escolhido no TREINO.

Treino 14 d / teste 7 d, passo 7 d, com **purga** de `h` minutos no fim do treino
(E1.6a: nenhum rótulo usado no ajuste termina dentro do teste). O limiar é escolhido
maximizando o retorno líquido médio por operação no treino (custo 0,14 %), com um
mínimo de 30 operações no treino; empate -> o limiar mais conservador. As operações
das janelas de teste são empilhadas e avaliadas com o mesmo bootstrap de blocos.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from load68 import HORIZONS, bars_for, load_csv_gz
from partb import COST_DESK, COST_PROXY, MIN_TRADES, _adjust, evaluate
from signals68 import compute

TRAIN_D, TEST_D = 14, 7
# Grelha congelada no pré-registo. Todos "long se score > θ".
GRID: dict[str, list[float]] = {
    "P1_mom_prev": [0.0, 0.25, 0.5, 1.0],        # em desvios-padrão do treino
    "P2_revert_z": [1.0, 1.5, 2.0, 2.5],          # score = -z
    "P3_vol_surge": [1.5, 2.0, 3.0, 5.0],
    "P4_taker_imb": [0.50, 0.55, 0.60, 0.65],
    "P6_breakout20": [0.0],
}
SD_SCALED = {"P1_mom_prev"}


def score_panel(raw: dict, h: int) -> dict:
    bars = bars_for(raw, h)
    cols: dict[str, list] = {k: [] for k in ("day", "ret", "eligible", *GRID)}
    for b in (bars[s] for s in sorted(bars)):
        n = len(b)
        if n <= 3:
            continue
        sig = compute(b)
        i = np.arange(n - 1)
        i = i[b.bucket_start[i + 1] == b.bucket_start[i] + h]
        if i.size == 0:
            continue

        # distância ao topo das 20 barras anteriores, já calculada dentro de P6
        cols["P6_breakout20"].append(np.where(sig["P6_breakout20"][i], 1.0, -1.0))
        cols["P1_mom_prev"].append(sig["_r_prev"][i])
        cols["P2_revert_z"].append(-sig["_z"][i])
        cols["P3_vol_surge"].append(sig["_surge"][i])
        cols["P4_taker_imb"].append(sig["_imb"][i])
        cols["ret"].append(b.close[i + 1] / b.close[i] - 1.0)
        cols["day"].append(b.bucket_start[i] // 1440)
        cols["eligible"].append(sig["eligible"][i])
    return {k: np.concatenate(v) for k, v in cols.items() if v}


def walk_forward(pan: dict, pred: str, h: int) -> np.ndarray:
    """Máscara de entrada só nos pontos de teste, com θ ajustado no treino anterior."""
    day, ret, elig = pan["day"], pan["ret"], pan["eligible"]
    score = pan[pred]
    base = elig & np.isfinite(ret) & np.isfinite(score)
    chosen = np.zeros(day.size, dtype=bool)
    tested = np.zeros(day.size, dtype=bool)  # população das janelas de teste (baseline comparável)
    d0, d1 = int(day.min()), int(day.max())
    purge_days = int(np.ceil(h / 1440.0))  # rótulo do treino tem de terminar antes da fronteira
    start = d0
    folds = []
    while start + TRAIN_D + TEST_D <= d1 + 1:
        tr = base & (day >= start) & (day < start + TRAIN_D - purge_days)
        te = base & (day >= start + TRAIN_D) & (day < start + TRAIN_D + TEST_D)
        if tr.sum() >= MIN_TRADES and te.sum() > 0:
            sd = float(np.std(score[tr])) if pred in SD_SCALED else 1.0
            best_t, best_v = None, -np.inf
            for t in GRID[pred]:
                thr = t * sd
                m = tr & (score > thr)
                if int(m.sum()) < MIN_TRADES:
                    continue
                v = float(ret[m].mean()) - COST_PROXY
                if v > best_v + 1e-15:  # empate -> fica o primeiro, grelha crescente
                    best_v, best_t = v, thr
            if best_t is not None:
                tested |= te
                chosen |= te & (score > best_t)
                folds.append({"inicio_dia": start, "theta": best_t, "treino_n": int(tr.sum())})
        start += TEST_D
    return chosen, tested, folds


def main() -> None:
    raw = load_csv_gz(Path(sys.argv[1]))
    label = sys.argv[2] if len(sys.argv) > 2 else "U2"
    cells = []
    for h in HORIZONS:
        pan = score_panel(raw, h)
        for pred in GRID:
            mask, tested, folds = walk_forward(pan, pred, h)
            cells.append(
                {
                    "universo": label, "h": h, "preditor": pred, "dobras": len(folds),
                    "thetas": [round(f["theta"], 6) for f in folds],
                    "proxy_014": evaluate(pan, mask, COST_PROXY, base_mask=tested),
                    "mesa_054": evaluate(pan, mask, COST_DESK, base_mask=tested),
                }
            )
        print(f"h={h} feito", flush=True)
    ok = [c for c in cells if c["proxy_014"]["status"] == "ok"]
    holm, bh = _adjust([c["proxy_014"]["p_boot"] for c in ok])
    for c, ho, b in zip(ok, holm, bh):
        pr = c["proxy_014"]
        c["holm"], c["bh"] = ho, b
        c["confirma"] = bool(pr["mean_net"] > 0 and pr["ci_lo"] > 0 and ho < 0.05 and pr["delta_lo"] > 0)
    Path(f"partb_adapt_{label}.json").write_text(json.dumps(cells, indent=1), encoding="utf-8")
    print(f"\n{'h':>4} {'preditor':<14} {'dobras':>6} {'n_teste':>8} {'liq@0.14%':>12} {'IC95 (bp)':>19} {'Holm':>6} {'long':>9} {'delta':>9} {'@0.54%':>10}")
    for c in cells:
        pr, ms = c["proxy_014"], c["mesa_054"]
        if pr["status"] != "ok":
            print(f"{c['h']:>4} {c['preditor']:<14} {c['dobras']:>6} {pr['n']:>8}   sem potencia")
            continue
        print(
            f"{c['h']:>4} {c['preditor']:<14} {c['dobras']:>6} {pr['n']:>8} "
            f"{pr['mean_net'] * 1e4:>+10.2f}bp [{pr['ci_lo'] * 1e4:>+8.2f},{pr['ci_hi'] * 1e4:>+8.2f}] "
            f"{c['holm']:>6.3f} {pr['sempre_long'] * 1e4:>+8.2f} {pr['delta'] * 1e4:>+8.2f} "
            f"{ms['mean_net'] * 1e4:>+9.2f}"
        )
    conf = [c for c in cells if c.get("confirma")]
    print(f"\nCONFIRMAM (adaptativo, Holm < 0,05): {len(conf)} -> {[(c['h'], c['preditor']) for c in conf]}")


if __name__ == "__main__":
    main()
