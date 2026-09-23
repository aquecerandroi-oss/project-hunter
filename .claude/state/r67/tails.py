"""R67 - de onde vem a diferenca? Mediana identica entre baldes => o efeito esta na cauda."""
from pathlib import Path

from load67 import load_paper
from oos import dedup, lo, r65_mints
from stats67 import cluster_boot_diff, mean, median, perm_p_strat

HERE = Path(__file__).resolve().parent
OUT = []


def p(s=""):
    OUT.append(s)


def trimmed(rows, k):
    """Remove as k maiores e as k menores observacoes de ret da amostra inteira."""
    s = sorted(rows, key=lambda r: r["ret"])
    return s[k:len(s) - k] if k else s


def main():
    paper = load_paper()
    excl = r65_mints()
    pop = dedup([r for r in paper if r["arm"].startswith("flow_v2") and r["mint"] not in excl])
    a = [r for r in pop if lo(r)]
    b = [r for r in pop if not lo(r)]
    p("fatia principal n=%d (<=25: %d, >25: %d)" % (len(pop), len(a), len(b)))
    p("mediana do ret: <=25 %+.4f | >25 %+.4f  (diferenca de MEDIANAS %+.4f)"
      % (median([r["ret"] for r in a]), median([r["ret"] for r in b]),
         median([r["ret"] for r in a]) - median([r["ret"] for r in b])))
    top = sorted(pop, key=lambda r: -r["ret"])[:10]
    p("as 10 maiores observacoes da fatia (ret, buys_1m, dia):")
    for r in top:
        p("  ret %+.3f  buys_1m %3.0f  %s  %s" % (r["ret"], r["buys_1m"], r["day"], r["arm"]))
    p("  delas, %d estao no balde <=25" % sum(1 for r in top if lo(r)))
    sa = sum(r["ret"] for r in a)
    p("  soma do ret do balde <=25 = %+.3f; sem as suas 3 maiores = %+.3f"
      % (sa, sa - sum(sorted((r["ret"] for r in a), reverse=True)[:3])))
    p()
    p("D com aparagem simetrica das caudas (k de cada lado, sobre a fatia inteira):")
    for k in (0, 1, 2, 3, 5, 10):
        t = trimmed(pop, k)
        ta = [r["ret"] for r in t if lo(r)]
        tb = [r["ret"] for r in t if not lo(r)]
        ci_lo, ci_hi, pneg, _ = cluster_boot_diff(t, "mint", lo, "ret")
        p("  k=%-3d n=%4d/%4d  D=%+.4f  IC95[%+.4f,%+.4f]  P(D<=0)=%.3f  p=%.4f"
          % (k, len(ta), len(tb), mean(ta) - mean(tb), ci_lo, ci_hi, pneg,
             perm_p_strat(t, lo, "ret")))
    p()
    p("desfecho binario (descritivo): fracao de apostas com ret > 0")
    for lab, s in (("<=25", a), (">25", b)):
        p("  %-5s %5.1f %%  (n=%d)" % (lab, 100 * mean([1.0 if r["ret"] > 0 else 0.0 for r in s]), len(s)))
    p("  p de permutacao sobre 'ret>0' = %.4f"
      % perm_p_strat([dict(r, win=1.0 if r["ret"] > 0 else 0.0) for r in pop], lo, "win"))
    p("hit15 (descritivo, depende da politica de saida): <=25 %.1f %% | >25 %.1f %%"
      % (100 * mean([r["hit15"] for r in a if r["hit15"] is not None]),
         100 * mean([r["hit15"] for r in b if r["hit15"] is not None])))
    txt = "\n".join(OUT)
    (HERE / "tails.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
