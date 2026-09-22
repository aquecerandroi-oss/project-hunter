"""R65 - robustez do corte `buys_1m <= 25`: bootstrap por CLUSTER (mint e dia), nao por operacao.

Motivo: 10 dos 76 mints tem 2-3 entradas quase simultaneas (as mesmas features, o mesmo destino de
mercado) - reamostrar operacoes independentes subestima o erro. PnL ja ajustado pelo rent devolvido.
"""
import random
from decimal import Decimal
from pathlib import Path

from costs import load_costs, sol
from load import load_positions
from stats import enrich, mean, rows

HERE = Path(__file__).resolve().parent
random.seed(651)
B = 10_000
CUT = 25.0


def prep():
    rs = enrich(rows())
    C = load_costs()
    rent = {p["tag"]: float(sol(C[p["proposal_id"]]["ata_rent"])) for p in load_positions()}
    for r in rs:
        r["adj"] = float(r["pnl_sol"]) + rent[r["tag"]]
    return rs


def split(rs):
    return ([r for r in rs if float(r["buys_1m"]) <= CUT],
            [r for r in rs if float(r["buys_1m"]) > CUT])


def cluster_boot(rs, key):
    groups = {}
    for r in rs:
        groups.setdefault(r[key], []).append(r)
    ks = list(groups)
    diffs, totals = [], []
    for _ in range(B):
        samp = []
        for _ in range(len(ks)):
            samp += groups[ks[random.randrange(len(ks))]]
        a, b = split(samp)
        totals.append(sum(x["adj"] for x in a))
        if a and b:
            diffs.append(mean([x["adj"] for x in a]) - mean([x["adj"] for x in b]))
    diffs.sort()
    totals.sort()
    return diffs, totals, len(ks)


def main():
    rs = prep()
    a, b = split(rs)
    out = []
    out.append("corte buys_1m <= %.0f (mediana da amostra), PnL ajustado pelo rent devolvido" % CUT)
    out.append("  <=%.0f : n=%d  media=%+.5f  soma=%s SOL" % (
        CUT, len(a), mean([x["adj"] for x in a]),
        sum((Decimal(x["pnl_sol"]) for x in a), Decimal(0)).quantize(Decimal("0.0001"))))
    out.append("  > %.0f : n=%d  media=%+.5f  soma=%s SOL" % (
        CUT, len(b), mean([x["adj"] for x in b]),
        sum((Decimal(x["pnl_sol"]) for x in b), Decimal(0)).quantize(Decimal("0.0001"))))
    out.append("  dif observada = %+.5f SOL/op" % (mean([x["adj"] for x in a]) - mean([x["adj"] for x in b])))
    for key, lab in (("mint", "mint"), ("day_brt", "dia")):
        d, t, nk = cluster_boot(rs, key)
        out.append("  bootstrap por %s (%d clusters): dif IC95 = [%+.5f, %+.5f]  P(dif<=0) = %.3f" % (
            lab, nk, d[int(0.025 * len(d))], d[int(0.975 * len(d))],
            sum(1 for x in d if x <= 0) / len(d)))
        out.append("  bootstrap por %s: soma do braco <=%.0f  IC95 = [%+.4f, %+.4f] SOL (ponto %+.4f)" % (
            lab, CUT, t[int(0.025 * B)], t[int(0.975 * B)], sum(x["adj"] for x in a)))
    out.append("  mints com mais de uma entrada: %d de %d" % (
        sum(1 for k in {r["mint"] for r in rs} if sum(1 for r in rs if r["mint"] == k) > 1),
        len({r["mint"] for r in rs})))
    txt = "\n".join(out)
    (HERE / "cluster.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
