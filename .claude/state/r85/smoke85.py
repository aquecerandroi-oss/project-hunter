"""R85 — fumaça sintética do encanamento inteiro ANTES do dado real (rótulo: SINTÉTICO, não é resultado).

Nulo: 40 moedas em passeio aleatório com OHLC → nenhum braço deve dar CONFIRMA. Controle positivo: os mesmos eventos
com +3 p.p. somados ao retorno de 10 d do braço (só o evento, não o controle) → a primária e o braço A devem confirmar
se houver amostra; o que falhar diz qual cláusula o encanamento não consegue satisfazer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from analyze85 import report
from collect85 import MAIN, collect
from data85 import build_hl_panel


def synth_rows(n_coins: int = 40, n_days: int = 2900, day0: int = 17000, seed: int = 85) -> list[tuple]:
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_coins):
        sym = f"S{k:02d}USDT"
        c = 10 * np.exp(np.cumsum(rng.normal(0.0005, 0.04, n_days)))
        o = np.concatenate([[c[0]], c[:-1]]) * np.exp(rng.normal(0, 0.003, n_days))
        h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.02, n_days)))
        lo = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.02, n_days)))
        v = np.exp(rng.normal(15 + k * 0.01, 0.5, n_days))
        rows += [(sym, day0 + t, o[t], h[t], lo[t], c[t], v[t]) for t in range(n_days)]
    return rows


def main() -> None:
    rows = synth_rows()
    day0, n_days = 17000, 2900
    hp = build_hl_panel(rows, {r[0] for r in rows}, set(), day0 + n_days, day0=day0)
    col = collect(hp, d_first=day0 + 60, d_last=day0 + n_days - 25, d_struct_last=day0 + n_days - 70)
    text, verdicts = report(col)
    print("# NULO SINTÉTICO\n" + text)
    for arm in (col.fib[MAIN], col.lta[0.25]["A"], col.lta[0.25]["B"]):
        for h in arm.events:
            arm.events[h] = [(dd, o + 0.03, p + 0.03) for dd, o, p in arm.events[h]]
    col.struct = [(dd, o + 0.03, p + 0.03, m, c) for dd, o, p, m, c in col.struct]
    for b in (1, 3):  # vizinhas também deslocadas: o controle positivo é de patamar, não de pico
        for h in col.fib[b].events:
            col.fib[b].events[h] = [(dd, o + 0.03, p + 0.03) for dd, o, p in col.fib[b].events[h]]
    for t in (0.15, 0.35):
        for key in ("A", "B"):
            for h in col.lta[t][key].events:
                col.lta[t][key].events[h] = [(dd, o + 0.03, p + 0.03) for dd, o, p in col.lta[t][key].events[h]]
    text2, v2 = report(col)
    print("\n# CONTROLE POSITIVO SINTÉTICO (+3 p.p. no evento)\n" + text2)
    print("\nRESUMO nulo:", verdicts, "\nRESUMO positivo:", v2)


if __name__ == "__main__":
    main()
