"""R87 — auditoria: (1) liquidações da perna vendida (A0, opt/after) com preços; (2) as divergências do teste de
antecipação no dado real, por motivo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r84"))
from data87 import load_market  # noqa: E402
from engine87 import ARMS, DAY_MS, H_MS, s7, universe  # noqa: E402
from run_real import FIRST_DAY, LAST_T, iso  # noqa: E402
from sim87 import simulate_arm  # noqa: E402
from analyze87 import mondays  # noqa: E402


def main() -> None:
    mk, _ = load_market()
    ts = mondays(mk, FIRST_DAY, LAST_T)
    r = simulate_arm(mk, ts, ARMS["A0"], "opt", "after")
    print(f"liquidações A0 opt/after: {len(r.liq_events)}")
    for e in r.liq_events:
        i = mk.p.ids.index(e["sym"])
        sp_hi = np.nanmax(mk.p.close[i, e["t"]: e["day"] + 1])
        print(f"{e['sym']:>14} T {iso(mk.p.day0 + e['t'])} dia {iso(mk.p.day0 + e['day'])} f0 {e['f0']:.6g} f_ref "
              f"{e['f_ref']:.6g} marca_max {e['mark_hi']:.6g} ({e['mark_hi'] / e['f0']:.2f}x) negociado_max "
              f"{e['last_hi']:.6g} ({e['last_hi'] / e['f0']:.2f}x) à vista fecho máx até o dia {sp_hi / e['s0']:.2f}x "
              f"s1/s0 {e['s1'] / e['s0']:.2f} resultado da vaga {e['net'] / (e['q'] * (e['s0'] + e['f0'] / e['m'])):+.3f}")
    rng = np.random.default_rng(20261005)
    sample = sorted(rng.choice(ts, size=25, replace=False).tolist())
    for t in sample:
        t_day = mk.p.day0 + t
        cut, _ = load_market(cut_day=t_day, cut_funding_ms=t_day * DAY_MS - H_MS)
        tc = t_day - cut.p.day0
        ua = [mk.p.ids[i] for i in universe(mk, t)]
        ub = [cut.p.ids[i] for i in universe(cut, tc)]
        if ua != ub:
            base_a = [x.split("#")[0] for x in ua]
            base_b = [x.split("#")[0] for x in ub]
            sa = {x.split("#")[0]: s7(mk, mk.p.ids.index(x), t) for x in ua}
            sb = {x.split("#")[0]: s7(cut, cut.p.ids.index(x), tc) for x in ub}
            print(f"{iso(t_day)}: ids iguais sem sufixo? {base_a == base_b}; só no completo {sorted(set(ua) - set(ub))}; "
                  f"só no cortado {sorted(set(ub) - set(ua))}; S7 iguais por base? {sa == sb}")


if __name__ == "__main__":
    main()
