"""R72 — porque e que um ciclo que ganha fichas nao vira lucro: o abandono."""
from decimal import Decimal
from load import load_all, resolvable
from run import pct
from sim import per_sol, simulate_current, simulate_scalp

real, paper = load_all()
for name, pop in (("REAIS", real), ("PAPEL", paper)):
    elig = [P for P in pop if resolvable(P)]
    for x in (Decimal(3), Decimal(8), Decimal(12)):
        for n in (30.0, 120.0):
            ab, nv, cyc = [], [], []
            for P in elig:
                a = simulate_scalp(P, x, n)
                pa, pb = per_sol(a, P), per_sol(simulate_current(P), P)
                if pa is None or pb is None:
                    continue
                (ab if a["abandoned"] else (cyc if a["cycles"] else nv)).append((pa, pa - pb))
            tot = len(ab) + len(nv) + len(cyc)
            f = lambda g: (pct(sum(v[0] for v in g) / len(g)), pct(sum(v[1] for v in g) / len(g))) if g else ("-", "-")
            print("%-6s X=%-3s N=%-4.0f | abandonou %3d (%2.0f %%) braco %s D %s | girou %3d braco %s D %s"
                  " | nunca vendeu %3d braco %s D %s"
                  % (name, x, n, len(ab), 100 * len(ab) / tot, *f(ab), len(cyc), *f(cyc), len(nv), *f(nv)))
