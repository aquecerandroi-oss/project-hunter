"""R87 — diagnóstico das divergências de trajetória do A0 (dado cortado × completo): qual semana e qual vaga."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r84"))
from analyze87 import mondays  # noqa: E402
from data87 import load_market  # noqa: E402
from engine87 import ARMS, DAY_MS, H_MS  # noqa: E402
from run_real import FIRST_DAY, LAST_T, iso  # noqa: E402
from sim87 import simulate_arm  # noqa: E402


def main() -> None:
    mk, _ = load_market()
    ts = mondays(mk, FIRST_DAY, LAST_T)
    for d in ("2022-12-19", "2023-06-26"):
        t = next(x for x in ts if iso(mk.p.day0 + x) == d)
        k = ts.index(t)
        t_day = mk.p.day0 + t
        cut, _ = load_market(cut_day=t_day, cut_funding_ms=t_day * DAY_MS - H_MS)
        fa = simulate_arm(mk, ts[: k - 1], ARMS["A0"], "pes", "after")
        fb = simulate_arm(cut, ts[: k - 1], ARMS["A0"], "pes", "after")
        diff = np.flatnonzero(~np.isclose(fa.weekly, fb.weekly, rtol=0, atol=1e-15))
        print(f"T {d}: abertas completo−cortado {sorted(set(fa.open_at_end) - set(fb.open_at_end))} "
              f"cortado−completo {sorted(set(fb.open_at_end) - set(fa.open_at_end))}; semanas com P&L diferente "
              f"{[iso(mk.p.day0 + ts[j]) for j in diff[:5]]} (de {diff.size}); diferença total "
              f"{float(np.nansum(fa.weekly - fb.weekly)):+.6f}; NaN no cortado {int(np.isnan(fb.weekly).sum())}")
        i_full = mk.p.ids.index("FTTUSDT") if "FTTUSDT" in mk.p.ids else None
        i_cut = cut.p.ids.index("FTTUSDT") if "FTTUSDT" in cut.p.ids else None
        if i_full is not None and i_cut is not None:
            print(f"   FTT completo: última vela à vista {iso(mk.p.day0 + int(mk.p.last[i_full]))}, encerrada={bool(mk.p.ended[i_full])}; "
                  f"cortado: última {iso(cut.p.day0 + int(cut.p.last[i_cut]))}, encerrada={bool(cut.p.ended[i_cut])}")


if __name__ == "__main__":
    main()
