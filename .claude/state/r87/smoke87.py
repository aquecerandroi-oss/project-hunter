"""R87 — fumaça sintética do protocolo inteiro: controle positivo (funding alto constante), nulo e negativo.

    uv run --no-sync python .claude/state/r87/smoke87.py  → smoke_synth.txt
Nenhum dado real. Os rótulos esperados: positivo → A0 e A1 CONFIRMA; nulo → nenhum confirma; negativo → nenhum confirma.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r84"))
from analyze87 import mondays, run  # noqa: E402
from engine87 import DAY_MS, Market  # noqa: E402
from panel import build_panel  # noqa: E402

D0, N_DAYS, N_COINS = 18_048, 2_700, 22  # 2019-06-01 → 2026-10


def synth(level: float, seed: int) -> Market:
    rng = np.random.default_rng(seed)
    syms = [f"S{k:02d}USDT" for k in range(N_COINS)]
    spot = 50 * np.exp(np.cumsum(rng.normal(0, 0.04, (N_COINS, N_DAYS)), axis=1))
    basis = np.zeros((N_COINS, N_DAYS))
    for d in range(1, N_DAYS):
        basis[:, d] = 0.8 * basis[:, d - 1] + rng.normal(0, 0.0007, N_COINS)
    rows = [(s, D0 + d, spot[k, d], spot[k, d], 1e7 * (N_COINS - k)) for k, s in enumerate(syms) for d in range(N_DAYS)]
    p = build_panel(rows, set(syms), set(), D0 + N_DAYS, day0=D0, day_end=D0 + N_DAYS - 1)
    order = [syms.index(i) for i in p.ids]
    f = (spot * (1 + basis))[order]
    ms = np.arange(D0 * DAY_MS, (D0 + N_DAYS) * DAY_MS, 8 * 3_600_000, dtype=np.int64) + 3
    rates = []
    for _ in p.ids:
        e = np.zeros(ms.size)
        for k in range(1, ms.size):
            e[k] = 0.97 * e[k - 1] + rng.normal(0, 0.00003)
        rates.append(level + e)
    return Market(p=p, f_open=f.copy(), f_high=f * 1.03, f_close=f.copy(), mult=np.ones(N_COINS),
                  perp_segs=[[(0, N_DAYS - 1, False)] for _ in p.ids], fund_ms=[ms.copy() for _ in p.ids],
                  fund_rate=rates, m_open=f.copy(), m_high=f * 1.03, m_low=f * 0.97)


def main() -> None:
    lines = []
    for name, level in (("positivo 0,03 %/8 h", 0.0003), ("nulo 0", 0.0), ("negativo −0,02 %/8 h", -0.0002)):
        mk = synth(level, 87)
        ts = mondays(mk, D0 + 40, D0 + N_DAYS - 10)
        out = run(mk, ts, reps=2000)
        lines.append(f"## {name}: {out['n_weeks']} semanas")
        for a, (v, why) in out["verdicts"].items():
            s = out["cells"][("pes", "after")][a]
            lines.append(f"{a}: {v} ({why}); pes/after anual {s['ann']:+.4f} IC [{s['lo']:+.4f}; {s['hi']:+.4f}] "
                         f"Holm {s.get('holm', float('nan')):.4f} episódios {s['eps']}")
    text = "\n".join(lines) + "\n"
    (HERE / "smoke_synth.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
