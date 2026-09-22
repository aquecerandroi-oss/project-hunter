"""R65 - Q2: quais variaveis DA DECISAO separam os 23 alvos dos 46 trailing?

Estatistica honesta para n = 87: por variavel, terços (ou mediana), n por balde, taxa de alvo,
PnL medio, IC 95 % por bootstrap (10 000 reamostragens) e p de permutacao (10 000) para a diferenca
topo-vs-base. Nenhum ajuste multivariado. Correcao de multiplas comparacoes: Benjamini-Hochberg.
Dinheiro somado em Decimal; a estatistica roda em float (valores ~1e-2 SOL, precisao sobra).
"""
import csv
import random
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
random.seed(65)
B = 10_000
OUT = []


def p(s=""):
    OUT.append(s)


def rows():
    return list(csv.DictReader(open(HERE / "anat.csv", newline="", encoding="utf-8")))


def f(r, k):
    v = r.get(k, "")
    if v in ("", None):
        return None
    if v in ("True", "False"):
        return 1.0 if v == "True" else 0.0
    try:
        return float(v)
    except ValueError:
        return None


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def boot_ci(xs, n=B):
    if len(xs) < 2:
        return (float("nan"), float("nan"))
    k = len(xs)
    ms = sorted(mean([xs[random.randrange(k)] for _ in range(k)]) for _ in range(n))
    return (ms[int(0.025 * n)], ms[int(0.975 * n)])


def perm_p(a, b, n=B):
    """p bilateral para a diferenca de medias, por permutacao dos rotulos."""
    obs = abs(mean(a) - mean(b))
    pool = a + b
    ka = len(a)
    hits = 0
    for _ in range(n):
        random.shuffle(pool)
        if abs(mean(pool[:ka]) - mean(pool[ka:])) >= obs - 1e-15:
            hits += 1
    return (hits + 1) / (n + 1)


def spearman(xy):
    """rho de Spearman + p de permutacao."""
    xs = [a for a, _ in xy]
    ys = [b for _, b in xy]
    rx = _ranks(xs)
    ry = _ranks(ys)
    rho = _pearson(rx, ry)
    hits = 0
    ry2 = list(ry)
    for _ in range(2000):
        random.shuffle(ry2)
        if abs(_pearson(rx, ry2)) >= abs(rho) - 1e-15:
            hits += 1
    return rho, (hits + 1) / 2001


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _pearson(a, b):
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


VARS = [
    ("age_s", "idade na entrada (s)"),
    ("progress_pct", "progresso da curva (%)"),
    ("real_sol", "SOL real na curva"),
    ("buys_1m", "compras 1 min"),
    ("sells_1m", "vendas 1 min"),
    ("sells_to_buys", "vendas/compras 1 min"),
    ("unique_buyers_1m", "compradores unicos 1 min"),
    ("snipers", "snipers"),
    ("net_sol_flow_1m", "fluxo liquido SOL 1 min"),
    ("mcap_delta_60s", "delta mcap 60 s (SOL)"),
    ("dev_share", "fatia do dev"),
    ("flow_per_buyer", "fluxo liq / comprador unico"),
    ("hour_brt", "hora BRT da entrada"),
]


def enrich(rs):
    for r in rs:
        b, s = f(r, "buys_1m"), f(r, "sells_1m")
        r["sells_to_buys"] = str(s / b) if b else ""
        nf, u = f(r, "net_sol_flow_1m"), f(r, "unique_buyers_1m")
        r["flow_per_buyer"] = str(nf / u) if u else ""
    return rs


def buckets(vals, k):
    """Corta em k baldes por quantil; devolve lista de (rotulo, indices)."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    n = len(order)
    out = []
    for j in range(k):
        lo, hi = j * n // k, (j + 1) * n // k
        idx = order[lo:hi]
        if not idx:
            continue
        out.append(("%.4g..%.4g" % (vals[idx[0]], vals[idx[-1]]), idx))
    return out


def analyse(rs, label, k=3):
    p("")
    p("#" * 112)
    p("# %s (n = %d)" % (label, len(rs)))
    p("#" * 112)
    p("%-24s %-16s %4s %6s %11s %24s %7s" % (
        "variavel", "balde", "n", "alvo%", "PnL medio", "IC95 do PnL medio", "PnL SOL"))
    pvals = []
    for key, name in VARS:
        vals, keep = [], []
        for r in rs:
            v = f(r, key)
            if v is not None:
                vals.append(v)
                keep.append(r)
        if len(keep) < 12:
            continue
        bs = buckets(vals, k)
        groups = []
        p("-" * 112)
        for lab, idx in bs:
            G = [keep[i] for i in idx]
            pnl = [float(g["pnl_sol"]) for g in G]
            groups.append(pnl)
            wr = 100.0 * sum(1 for g in G if g["reason"] == "target") / len(G)
            lo, hi = boot_ci(pnl)
            p("%-24s %-16s %4d %5.0f%% %11.5f  [%9.5f, %9.5f] %7s" % (
                name, lab, len(G), wr, mean(pnl), lo, hi,
                sum((Decimal(g["pnl_sol"]) for g in G), Decimal(0)).quantize(Decimal("0.0001"))))
        if len(groups) >= 2:
            pv = perm_p(list(groups[-1]), list(groups[0]))
            rho, rp = spearman([(f(r, key), float(r["pnl_sol"])) for r in keep])
            pvals.append((name, pv, rho, rp,
                          mean(groups[-1]) - mean(groups[0])))
            p("%-24s %-16s dif(topo-base) = %+.5f SOL/op  p_perm = %.4f  |  rho = %+.3f (p = %.4f)" % (
                "", "", mean(groups[-1]) - mean(groups[0]), pv, rho, rp))
    p("")
    p("Benjamini-Hochberg sobre os %d p de permutacao (FDR 10 %%):" % len(pvals))
    srt = sorted(pvals, key=lambda x: x[1])
    m = len(srt)
    cut = 0
    for i, (_n, pv, _r, _rp, _d) in enumerate(srt, 1):
        if pv <= 0.10 * i / m:
            cut = i
    for i, (n_, pv, rho, rp, d) in enumerate(srt, 1):
        p("  %-28s p=%.4f  limiar BH=%.4f  %s  (dif %+.5f SOL/op, rho %+.3f)" % (
            n_, pv, 0.10 * i / m, "SOBREVIVE" if i <= cut else "indistinguivel de ruido", d, rho))
    return pvals


def main():
    rs = enrich(rows())
    analyse(rs, "TODAS as 87 operacoes", 3)
    tt = [r for r in rs if r["reason"] in ("target", "trailing")]
    analyse(tt, "SO alvo (23) vs trailing (46) - a pergunta separadora", 2)

    # baldes combinados candidatos
    p("")
    p("#" * 112)
    p("# BALDES COMBINADOS (2 variaveis, so descritivo - nao e ajuste)")
    p("#" * 112)
    p("%-52s %4s %6s %11s %24s %9s" % ("regra", "n", "alvo%", "PnL medio", "IC95", "PnL SOL"))
    tests = [
        ("sells_1m/buys_1m <= 0.25", lambda r: f(r, "sells_to_buys") is not None and f(r, "sells_to_buys") <= 0.25),
        ("sells_1m/buys_1m <= 0.35", lambda r: f(r, "sells_to_buys") is not None and f(r, "sells_to_buys") <= 0.35),
        ("sells_1m/buys_1m > 0.35", lambda r: f(r, "sells_to_buys") is not None and f(r, "sells_to_buys") > 0.35),
        ("progresso <= 40 %", lambda r: f(r, "progress_pct") <= 40),
        ("progresso 40-70 %", lambda r: 40 < f(r, "progress_pct") <= 70),
        ("progresso > 70 %", lambda r: f(r, "progress_pct") > 70),
        ("snipers <= 3", lambda r: f(r, "snipers") is not None and f(r, "snipers") <= 3),
        ("snipers > 10", lambda r: f(r, "snipers") is not None and f(r, "snipers") > 10),
        ("idade <= 90 s", lambda r: f(r, "age_s") <= 90),
        ("idade > 150 s", lambda r: f(r, "age_s") > 150),
        ("dev_share > 0", lambda r: f(r, "dev_share") is not None and f(r, "dev_share") > 0),
        ("fluxo/comprador >= 0.30 SOL", lambda r: f(r, "flow_per_buyer") is not None and f(r, "flow_per_buyer") >= 0.30),
        ("fluxo/comprador < 0.15 SOL", lambda r: f(r, "flow_per_buyer") is not None and f(r, "flow_per_buyer") < 0.15),
        ("s/b<=0.35 E progresso<=70 %", lambda r: f(r, "sells_to_buys") is not None
            and f(r, "sells_to_buys") <= 0.35 and f(r, "progress_pct") <= 70),
        ("s/b<=0.35 E progresso<=70 E idade<=150", lambda r: f(r, "sells_to_buys") is not None
            and f(r, "sells_to_buys") <= 0.35 and f(r, "progress_pct") <= 70 and f(r, "age_s") <= 150),
        ("s/b<=0.25 E progresso<=70 %", lambda r: f(r, "sells_to_buys") is not None
            and f(r, "sells_to_buys") <= 0.25 and f(r, "progress_pct") <= 70),
    ]
    for name, fn in tests:
        G = [r for r in rs if fn(r)]
        if not G:
            continue
        pnl = [float(g["pnl_sol"]) for g in G]
        lo, hi = boot_ci(pnl)
        wr = 100.0 * sum(1 for g in G if g["reason"] == "target") / len(G)
        p("%-52s %4d %5.0f%% %11.5f  [%9.5f, %9.5f] %9s" % (
            name, len(G), wr, mean(pnl), lo, hi,
            sum((Decimal(g["pnl_sol"]) for g in G), Decimal(0)).quantize(Decimal("0.0001"))))

    # operator/5 vs /6
    p("")
    p("#" * 112)
    p("# operator/5 vs operator/6")
    p("#" * 112)
    a = [float(r["pnl_sol"]) for r in rs if r["set"] == "operator/5"]
    b = [float(r["pnl_sol"]) for r in rs if r["set"] == "operator/6"]
    p("operator/5 n=%d media=%.5f IC95=%s soma=%s" % (
        len(a), mean(a), "[%.5f, %.5f]" % boot_ci(a),
        sum((Decimal(r["pnl_sol"]) for r in rs if r["set"] == "operator/5"), Decimal(0))))
    p("operator/6 n=%d media=%.5f IC95=%s soma=%s" % (
        len(b), mean(b), "[%.5f, %.5f]" % boot_ci(b),
        sum((Decimal(r["pnl_sol"]) for r in rs if r["set"] == "operator/6"), Decimal(0))))
    p("dif(6-5) = %+.5f SOL/op  p_perm = %.4f" % (mean(b) - mean(a), perm_p(list(b), list(a))))
    # pares no mesmo mint
    pares = {}
    for r in rs:
        pares.setdefault(r["mint"], []).append(r)
    both = [v for v in pares.values() if len({x["set"] for x in v}) == 2]
    p("mints com os dois conjuntos: %d" % len(both))
    for v in both:
        p("   %-12s %s" % (v[0]["tag"].split("#")[0],
                           " | ".join("%s %s %s" % (x["set"], x["reason"], x["pnl_sol"]) for x in v)))


if __name__ == "__main__":
    main()
    txt = "\n".join(OUT)
    (HERE / "stats.txt").write_text(txt, encoding="utf-8")
    print(txt)
