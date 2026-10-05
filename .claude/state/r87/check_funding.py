"""R87 — conferência independente do funding do A0: soma direta das taxas recebidas pelas vagas do universo, semana a
semana (sem preço: nocional da vaga = metade de 1/N_T), contra o `funding` do simulador. Por ano."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r84"))
from analyze87 import mondays  # noqa: E402
from data87 import load_market  # noqa: E402
from engine87 import ARMS, DAY_MS, RECV_TOL, universe  # noqa: E402
from run_real import FIRST_DAY, LAST_T  # noqa: E402
from sim87 import simulate_arm  # noqa: E402

E = dt.date(1970, 1, 1)


def main() -> None:
    mk, _ = load_market()
    ts = mondays(mk, FIRST_DAY, LAST_T)
    sim = simulate_arm(mk, ts, ARMS["A0"], "opt", "after")
    direct = np.zeros(len(ts))
    neg_share = np.zeros(len(ts))
    for k, t in enumerate(ts):
        u = universe(mk, t)
        lo, hi = mk.t_ms(t) + RECV_TOL, mk.t_ms(t + 7) + RECV_TOL
        sums = []
        for i in u:
            ms, r = mk.fund_ms[i], mk.fund_rate[i]
            a, b = np.searchsorted(ms, lo, "right"), np.searchsorted(ms, hi, "right")
            sums.append(float(r[a:b].sum()))
        direct[k] = 0.5 * float(np.mean(sums))
        neg_share[k] = float(np.mean(np.array(sums) < 0))
    years = np.array([(E + dt.timedelta(days=int(mk.p.day0 + t))).year for t in ts])
    for y in np.unique(years):
        m = years == y
        print(f"{y}: simulador {52 * sim.funding[m].mean() * 100:+.2f} % a.a. | soma direta (nocional/2, sem preço) "
              f"{52 * direct[m].mean() * 100:+.2f} % a.a. | fração de vagas com funding semanal < 0 {neg_share[m].mean():.0%}")
    _ = DAY_MS


if __name__ == "__main__":
    main()
