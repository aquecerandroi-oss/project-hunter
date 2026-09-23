"""R72 — corre os 5 passos de H-009 e imprime o relatorio bruto.

1. censo de oscilacoes (passo 1, o portao barato: mediana < 2 em todas as celulas => refuta)
2. politica de giros x regra atual, na mesma moeda (passo 2) + sensibilidade
3. recompras que caem em dreno (passo 3)
4. bootstrap por mint + permutacao emparelhada + planalto x pico (passo 4)
5. tamanho de oscilacao de equilibrio e com que frequencia a fita o entrega (passo 5)
"""

from __future__ import annotations

import random
import sys
from decimal import Decimal

from load import WINDOW_S, load_all, resolvable, window
from sim import COST, LATENCY_S, per_sol, simulate_cheat, simulate_current, simulate_scalp
from swings import count_swings, quantiles, swing_events

XS = (Decimal(3), Decimal(5), Decimal(8), Decimal(12))
NS = (30.0, 60.0, 120.0)
MRE = Decimal("0.05")   # +0,05 por SOL arriscado, pre-registado
REFUT = Decimal("0.01")  # limite superior do IC abaixo disto => refuta
REPS = 10_000
SEED = 72


def pct(v):
    return "%+7.2f%%" % (float(v) * 100)


def boot_ci(diffs, mints, reps=REPS, seed=SEED):
    """Bootstrap por cluster de mint: reamostra mints inteiros, com reposicao."""
    by = {}
    for d, m in zip(diffs, mints):
        by.setdefault(m, []).append(float(d))
    keys = list(by)
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        tot, n = 0.0, 0
        for _ in range(len(keys)):
            for v in by[keys[rng.randrange(len(keys))]]:
                tot += v
                n += 1
        means.append(tot / n if n else 0.0)
    means.sort()
    return means[int(0.025 * reps)], means[int(0.975 * reps)]


def perm_p(diffs, reps=REPS, seed=SEED):
    """Permutacao emparelhada (troca de sinal): H0 = a politica e a regra sao intercambiaveis."""
    v = [float(d) for d in diffs]
    obs = sum(v) / len(v)
    rng = random.Random(seed + 1)
    hits = 0
    for _ in range(reps):
        s = sum(x if rng.random() < 0.5 else -x for x in v) / len(v)
        if abs(s) >= abs(obs):
            hits += 1
    return (hits + 1) / (reps + 1)


def main():
    real, paper = load_all()
    pops = [("REAIS", real), ("PAPEL", paper)]
    for name, pop in pops:
        elig = [P for P in pop if resolvable(P)]
        only_photos = [P for P in pop if P["source"] == "photos"]
        nosrc = [P for P in pop if P["source"] == "none"]
        gaps30 = sum(1 for P in elig if P["max_gap_s"] > 30)
        regs = sum(P.get("clock_regressions", 0) for P in elig)
        print("\n" + "=" * 96)
        print("POPULACAO %s: n=%d | so fotos (excluidas)=%d | sem reservas=%d | resolviveis=%d"
              % (name, len(pop), len(only_photos), len(nosrc), len(elig)))
        q = quantiles([P["max_gap_s"] for P in elig])
        print("  maior buraco entre pontos na janela de 300 s: p25=%.0f s mediana=%.0f s p75=%.0f s"
              " | com buraco > 30 s: %d de %d" % (q[0], q[1], q[2], gaps30, len(elig)))
        print("  regressoes de relogio corrigidas pelo carimbo monotono: %d" % regs)

        # ---------- PASSO 1: censo de oscilacoes ----------
        print("\n  PASSO 1 — oscilacoes completas na janela de 5 min (queda >= X % da maxima")
        print("  corrente, seguida de recuperacao >= X % em N s). Uma linha por (X, N).")
        print("  %-5s %-6s %6s %6s %6s %7s %7s %8s" %
              ("X%", "N s", "p25", "med", "p75", ">=1", ">=2", "media"))
        census = {}
        for x in XS:
            for n in NS:
                counts = [count_swings(window(P), x, n) for P in elig]
                census[(x, n)] = counts
                p25, med, p75 = quantiles(counts)
                ge1 = sum(1 for c in counts if c >= 1) / len(counts) * 100
                ge2 = sum(1 for c in counts if c >= 2) / len(counts) * 100
                print("  %-5s %-6.0f %6.1f %6.1f %6.1f %6.1f%% %6.1f%% %8.2f" %
                      (x, n, p25, med, p75, ge1, ge2, sum(counts) / len(counts)))
        med_max = max(quantiles(c)[1] for c in census.values())
        print("  ==> maior mediana de giros em qualquer celula: %.1f  (regra de refutacao da"
              " fila: < 2 em TODAS as celulas)" % med_max)
        if name == "REAIS":
            globals()["_MEDMAX_REAL"] = med_max

        if "--census-only" in sys.argv:
            continue

        # ---------- PASSOS 2/3/4 ----------
        print("\n  PASSOS 2-4 — politica de giros x regra atual (alvo 1,15x / trailing 10 %%"
              " / 300 s), mesma moeda, custo %.2f %% por ida e volta, %.1f s de atraso por perna"
              % (float(COST) * 100, LATENCY_S))
        print("  %-5s %-6s %5s %7s %8s %9s %10s %10s %7s %7s %7s" %
              ("X%", "N s", "n", "giros", "recomp", "drenos", "D/SOL", "IC95 inf", "IC sup",
               "p perm", "media"))
        cells = {}
        for x in XS:
            for n in NS:
                rows = []
                for P in elig:
                    a = simulate_scalp(P, x, n)
                    b = simulate_current(P)
                    pa, pb = per_sol(a, P), per_sol(b, P)
                    if pa is None or pb is None:
                        continue
                    rows.append((P["mint"], pa - pb, pa, pb, a))
                if len(rows) < 20:
                    print("  %-5s %-6.0f  amostra insuficiente (%d)" % (x, n, len(rows)))
                    continue
                diffs = [r[1] for r in rows]
                mints = [r[0] for r in rows]
                D = sum(diffs) / len(diffs)
                lo, hi = boot_ci(diffs, mints)
                p = perm_p(diffs)
                cyc = sum(r[4]["cycles"] for r in rows)
                reb = sum(r[4]["rebuys"] for r in rows)
                dr = sum(r[4]["drains"] for r in rows)
                cells[(x, n)] = dict(D=D, lo=lo, hi=hi, p=p, n=len(rows), cycles=cyc,
                                     rebuys=reb, drains=dr,
                                     scalp=sum(r[2] for r in rows) / len(rows),
                                     cur=sum(r[3] for r in rows) / len(rows))
                print("  %-5s %-6.0f %5d %7d %8d %9d %10s %10s %7s %7.4f %7s" %
                      (x, n, len(rows), cyc, reb, dr, pct(D), pct(lo), pct(hi), p,
                       pct(sum(r[2] for r in rows) / len(rows))))
        if cells:
            print("\n  regra atual, media por SOL nesta populacao: %s"
                  % pct(list(cells.values())[0]["cur"]))
            hi_max = max(c["hi"] for c in cells.values())
            print("  ==> maior limite SUPERIOR do IC em qualquer celula: %s"
                  " (refuta se < %s em todas)" % (pct(hi_max), pct(REFUT)))
            conf = [(k, c) for k, c in cells.items()
                    if c["D"] >= float(MRE) and c["lo"] > 0 and c["p"] < 0.05]
            print("  ==> celulas que CONFIRMAM (D >= MRE, IC inf > 0, p < 0,05): %d de %d"
                  % (len(conf), len(cells)))
            print("\n  planalto x pico (D por X, media sobre N):")
            for x in XS:
                vs = [cells[(x, n)]["D"] for n in NS if (x, n) in cells]
                if vs:
                    print("    X=%-4s D medio = %s" % (x, pct(sum(vs) / len(vs))))

        # ---------- CONTROLO DE FUGA ----------
        ch = [per_sol(simulate_cheat(P), P) for P in elig]
        ch = [c for c in ch if c is not None]
        cur = [per_sol(simulate_current(P), P) for P in elig]
        cur = [c for c in cur if c is not None]
        print("\n  CONTROLO DE FUGA: braco batoteiro (vende no maximo da janela, olhando o"
              " futuro) = %s por SOL; regra atual = %s. A distancia e o que a guarda protege."
              % (pct(sum(ch) / len(ch)), pct(sum(cur) / len(cur))))

        # ---------- PASSO 5: equilibrio ----------
        c = COST
        x_be = c - c * c / 4
        print("\n  PASSO 5 — oscilacao de equilibrio: multiplicador de tokens por ciclo ="
              " (1-c/2)^2/(1-X); equilibrio em X = c - c^2/4 = %.4f %%" % (float(x_be) * 100))
        for cc in (Decimal("0.0223"), Decimal("0.025"), Decimal("0.03")):
            xb = cc - cc * cc / 4
            cnt = [count_swings(window(P), xb * 100, 60.0) for P in elig]
            p25, med, p75 = quantiles(cnt)
            print("    c=%.2f %% -> X equilibrio %.3f %% | giros desse tamanho em N=60 s:"
                  " mediana %.1f, p75 %.1f, >=2 em %.0f %% das posicoes"
                  % (float(cc) * 100, float(xb) * 100, med, p75,
                     sum(1 for k in cnt if k >= 2) / len(cnt) * 100))

    # ---------- SENSIBILIDADE (so nas reais, celula mais favoravel) ----------
    if "--census-only" not in sys.argv:
        elig = [P for P in real if resolvable(P)]
        print("\n" + "=" * 96)
        print("SENSIBILIDADE (populacao REAIS, X=3 %, N=120 s - a celula com mais giros)")
        for cc, lat in ((COST, LATENCY_S), (COST, 5.0), (Decimal("0.025"), LATENCY_S),
                        (Decimal("0.03"), LATENCY_S), (Decimal("0.03"), 5.0)):
            rows = []
            for P in elig:
                a = simulate_scalp(P, Decimal(3), 120.0, cost=cc, latency_s=lat)
                b = simulate_current(P, cost=cc, latency_s=lat)
                pa, pb = per_sol(a, P), per_sol(b, P)
                if pa is not None and pb is not None:
                    rows.append((P["mint"], pa - pb))
            diffs = [r[1] for r in rows]
            lo, hi = boot_ci(diffs, [r[0] for r in rows])
            print("  custo %.2f %% | atraso %.1f s -> D = %s  IC95 [%s, %s]  n=%d"
                  % (float(cc) * 100, lat, pct(sum(diffs) / len(diffs)), pct(lo), pct(hi),
                     len(rows)))


if __name__ == "__main__":
    main()
