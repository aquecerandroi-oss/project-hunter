"""R67 - o teste fora de amostra do achado `buys_1m <= 25` do R65. Desenho em `preregistro.md`."""
import csv
from pathlib import Path

from load67 import load_paper, load_real
from stats67 import (bucket_table, cluster_boot_diff, mean, median, pct,
                     perm_p_strat, rolling_pct_cut, terciles)

HERE = Path(__file__).resolve().parent
CUT = 25.0
OUT = []


def p(s=""):
    OUT.append(s)


def r65_mints():
    return set((HERE / "r65_mints.txt").read_text(encoding="utf-8").split())


def dedup(rows):
    """Uma aposta por mint (a mais antiga): varios bracos propoem a mesma moeda no mesmo tique."""
    best = {}
    for r in sorted(rows, key=lambda x: x["entry_at"]):
        best.setdefault(r["mint"], r)
    return list(best.values())


def lo(r):
    return r["buys_1m"] is not None and r["buys_1m"] <= CUT


def contrast(rows, val="ret", label="", perm=True):
    a = [r for r in rows if lo(r)]
    b = [r for r in rows if not lo(r)]
    if not a or not b:
        p("  %-28s n insuficiente (%d/%d)" % (label, len(a), len(b)))
        return None
    d = mean([r[val] for r in a]) - mean([r[val] for r in b])
    ci_lo, ci_hi, pneg, nk = cluster_boot_diff(rows, "mint", lo, val)
    pv = perm_p_strat(rows, lo, val) if perm else float("nan")
    p("  %-28s n=%4d/%4d  media %+.4f / %+.4f  D=%+.4f  IC95[%+.4f,%+.4f] P(D<=0)=%.3f  p=%s"
      % (label, len(a), len(b), mean([r[val] for r in a]), mean([r[val] for r in b]),
         d, ci_lo, ci_hi, pneg, ("%.4f" % pv) if pv == pv else "-"))
    return dict(d=d, ci=(ci_lo, ci_hi), p=pv, na=len(a), nb=len(b), nk=nk)


def describe(rows, label):
    hs = [r["hit15"] for r in rows if r["hit15"] is not None]
    p("%s: n=%d mints=%d dias=%d  ret medio %+.4f  mediano %+.4f  hit15 %.1f%%  hold med %.0fs"
      % (label, len(rows), len({r["mint"] for r in rows}), len({r["day"] for r in rows}),
         mean([r["ret"] for r in rows]), median([r["ret"] for r in rows]),
         100 * mean(hs) if hs else float("nan"),
         median([r["hold_s"] for r in rows if r["hold_s"] is not None])))


def buckets(rows, var="buys_1m"):
    t = terciles(rows, var)
    if not t:
        return
    p("  baldes de %s (tercis %.0f / %.0f):" % (var, t[0], t[1]))
    for b in bucket_table(rows, var, list(t)):
        p("    %-12s n=%4d  hit15 %5.1f%%  ret medio %+.4f  mediano %+.4f  hold med %.0fs"
          % (b["lab"], b["n"], b["hit"], b["m"], b["med"], b["hold"]))


def scan(rows):
    p("  varredura de limiares fixos (D = media<=X menos media>X, ret liquido por SOL):")
    global CUT
    keep = CUT
    for x in (10, 15, 20, 25, 30, 40, 60, 80):
        CUT = float(x)
        a = [r["ret"] for r in rows if lo(r)]
        b = [r["ret"] for r in rows if not lo(r)]
        if len(a) < 20 or len(b) < 20:
            p("    <=%-3d  n=%4d/%4d  (amostra insuficiente)" % (x, len(a), len(b)))
            continue
        ci_lo, ci_hi, pneg, _ = cluster_boot_diff(rows, "mint", lo, "ret")
        p("    <=%-3d  n=%4d/%4d  D=%+.4f  IC95[%+.4f,%+.4f]  P(D<=0)=%.3f"
          % (x, len(a), len(b), mean(a) - mean(b), ci_lo, ci_hi, pneg))
    CUT = keep


def rolling(rows):
    p("  percentil movel de 3 dias (corte do dia = percentil das decisoes dos 3 dias ANTERIORES):")
    for q, lab in ((0.30, "P30"), (0.40, "P40"), (0.50, "P50"), (0.60, "P60")):
        cuts = rolling_pct_cut(rows, q)
        sel = [r for r in rows if cuts.get(r["day"]) is not None]
        if len(sel) < 60:
            p("    %s  amostra insuficiente (%d)" % (lab, len(sel)))
            continue
        a = [r["ret"] for r in sel if r["buys_1m"] <= cuts[r["day"]]]
        b = [r["ret"] for r in sel if r["buys_1m"] > cuts[r["day"]]]
        if len(a) < 20 or len(b) < 20:
            p("    %s  amostra insuficiente (%d/%d)" % (lab, len(a), len(b)))
            continue
        vals = sorted({round(cuts[d]) for d in {r["day"] for r in sel}})
        p("    %s  cortes %s  n=%4d/%4d  D=%+.4f" % (lab, vals, len(a), len(b), mean(a) - mean(b)))


def stratified(rows, var, label):
    t = terciles(rows, var)
    if not t:
        p("    %-16s sem suporte" % label)
        return
    bounds = [(-1e18, t[0]), (t[0], t[1]), (t[1], 1e18)]
    ds, ws = [], []
    for lob, hib in bounds:
        sel = [r for r in rows if r[var] is not None and lob < r[var] <= hib]
        a = [r["ret"] for r in sel if lo(r)]
        b = [r["ret"] for r in sel if not lo(r)]
        if len(a) < 10 or len(b) < 10:
            p("    %-16s estrato (%s, %s]  n=%d/%d insuficiente"
              % (label, "-inf" if lob < -1e17 else "%.4g" % lob,
                 "inf" if hib > 1e17 else "%.4g" % hib, len(a), len(b)))
            continue
        d = mean(a) - mean(b)
        ds.append(d)
        ws.append(len(sel))
        p("    %-16s estrato (%s, %s]  n=%3d/%3d  D=%+.4f"
          % (label, "-inf" if lob < -1e17 else "%.4g" % lob, "inf" if hib > 1e17 else "%.4g" % hib,
             len(a), len(b), d))
    if ds:
        p("    %-16s D ponderado dentro de estratos = %+.4f"
          % (label, sum(d * w for d, w in zip(ds, ws)) / sum(ws)))


def split_temporal(main_pop):
    global CUT
    keep = CUT
    fit = [r for r in main_pop if r["day"] in ("2026-09-19", "2026-09-20")]
    test = [r for r in main_pop if r["day"] == "2026-09-21"]
    if not fit or not test:
        p("  sem suporte para o split temporal")
        return
    cuts, best, bestd = {}, None, -1e18
    for x in (10, 15, 20, 25, 30, 40, 60):
        CUT = float(x)
        a = [r["ret"] for r in fit if lo(r)]
        b = [r["ret"] for r in fit if not lo(r)]
        if len(a) < 10 or len(b) < 10:
            continue
        cuts[x] = mean(a) - mean(b)
        if cuts[x] > bestd:
            best, bestd = x, cuts[x]
    p("  ajuste (19-20/09, n=%d): D por limiar = %s" % (len(fit), {k: round(v, 4) for k, v in cuts.items()}))
    if best is None:
        p("  ajuste sem suporte")
        CUT = keep
        return
    p("  melhor limiar no ajuste: %s (D=%+.4f)" % (best, bestd))
    for x, lab in ((float(best), "melhor do ajuste"), (25.0, "corte congelado 25")):
        CUT = x
        a = [r["ret"] for r in test if lo(r)]
        b = [r["ret"] for r in test if not lo(r)]
        p("  teste (21/09, n=%d) %s <=%.0f: n=%d/%d  D=%+.4f"
          % (len(test), lab, x, len(a), len(b), (mean(a) - mean(b)) if a and b else float("nan")))
    CUT = keep


def main():
    paper = load_paper()
    excl = r65_mints()
    flow = [r for r in paper if r["arm"].startswith("flow_v2")]
    flow_ex = [r for r in flow if r["mint"] not in excl]
    main_pop = dedup(flow_ex)

    p("=" * 100)
    p("R67 - `buys_1m <= 25` fora de amostra. Desfecho primario: ret = pnl_sol / size_sol (liquido de taxa).")
    p("Fatia PRINCIPAL: apostas de papel flow_v2 (0,05 SOL / 3x / 1800 s / trailing 35 %), 12-21/09,")
    p("fechadas e 'measured', sem os 76 mints do R65, UMA aposta por mint.")
    p("=" * 100)
    p("cobertura: papel elegivel %d | flow_v2 %d | apos excluir mints do R65 %d | apos dedup por mint %d"
      % (len(paper), len(flow), len(flow_ex), len(main_pop)))
    p("distribuicao de buys_1m na fatia principal: p10=%.0f p25=%.0f mediana=%.0f p75=%.0f p90=%.0f"
      % tuple(pct([r["buys_1m"] for r in main_pop], q) for q in (0.1, 0.25, 0.5, 0.75, 0.9)))
    p("fracao com buys_1m <= 25: %.1f %%" % (100 * mean([1.0 if lo(r) else 0.0 for r in main_pop])))
    p()

    p("--- 1. TESTE PRIMARIO CONGELADO (corte 25, fatia principal) ---")
    describe(main_pop, "fatia principal")
    contrast(main_pop, label="corte 25 (ret liquido)")
    p()
    p("--- 2. Baldes por tercis (descritivo; hit15 = high_water_x >= 1,15, descritivo) ---")
    buckets(main_pop)
    p()
    p("--- 3. Curva de limiares: planalto ou pico? ---")
    scan(main_pop)
    rolling(main_pop)
    p()
    p("--- 4. Confundimento: estratificar (nao ajustar) ---")
    for var, lab in (("age_s", "idade (s)"), ("progress_pct", "progresso %"),
                     ("real_sol", "SOL real curva"), ("unique_buyers_1m", "compradores unicos")):
        stratified(main_pop, var, lab)
    p()
    p("--- 5. Sensibilidades pre-definidas ---")
    p("  (a) sem dedup (todas as apostas flow_v2 fora dos mints do R65; bootstrap por mint):")
    contrast(flow_ex, label="sem dedup")
    p("  (b) com os mints do R65 dentro (dedup):")
    contrast(dedup(flow), label="com mints do R65")
    p("  (c) leave-one-day-out (fatia principal):")
    for d in sorted({r["day"] for r in main_pop}):
        sub = [r for r in main_pop if r["day"] != d]
        a = [r["ret"] for r in sub if lo(r)]
        b = [r["ret"] for r in sub if not lo(r)]
        if len(a) < 15 or len(b) < 15:
            continue
        p("      sem %s  n=%4d/%4d  D=%+.4f" % (d, len(a), len(b), mean(a) - mean(b)))
    p("  (d) por dia (fatia principal):")
    for d in sorted({r["day"] for r in main_pop}):
        sub = [r for r in main_pop if r["day"] == d]
        a = [r["ret"] for r in sub if lo(r)]
        b = [r["ret"] for r in sub if not lo(r)]
        if not a or not b:
            p("      %s  n=%d/%d (sem contraste)" % (d, len(a), len(b)))
            continue
        p("      %s  n=%3d/%3d  D=%+.4f  media<= %+.4f  media> %+.4f"
          % (d, len(a), len(b), mean(a) - mean(b), mean(a), mean(b)))
    p()
    p("--- 6. Split temporal: ajustar em 19-20/09, testar em 21/09 ---")
    split_temporal(main_pop)
    p()
    p("--- 7. Fatias secundarias (declaradas NAO-holdout ou pequenas demais) ---")
    hype = dedup([r for r in paper if r["arm"].startswith("hype_probe") and r["mint"] not in excl])
    describe(hype, "  hype_probe_v0/2 (0,01 / 3x / 600 s)")
    contrast(hype, label="hype_probe corte 25")
    op = dedup([r for r in paper if r["arm"].startswith("operator") and r["mint"] not in excl])
    describe(op, "  operator papel (sobra apos excluir as partilhadas com o real)")
    contrast(op, label="operator papel corte 25", perm=False)
    real = load_real()
    early = [r for r in real if r["day"] < "2026-09-19"]
    describe(early, "  REAIS 16-18/09 (NAO e holdout: entraram nas 87 do R65)")
    contrast(early, label="reais 16-18 corte 25", perm=False)
    p()
    p("--- 8. Exclusoes (risco de selecao apontado pela Astra) ---")
    allp = list(csv.DictReader(open(HERE / "paper.csv", newline="", encoding="utf-8")))
    ind = [r for r in allp if r["outcome_quality"] == "indeterminate" and (r["buys_1m"] or "").strip()]
    p("  apostas 'indeterminate' com buys_1m: %d" % len(ind))
    b_ind = [float(r["buys_1m"]) for r in ind]
    if b_ind:
        p("  buys_1m das indeterminadas: mediana %.0f | <=25: %.1f %%  (na fatia principal: <=25 %.1f %%)"
          % (median(b_ind), 100 * mean([1.0 if x <= CUT else 0.0 for x in b_ind]),
             100 * mean([1.0 if lo(r) else 0.0 for r in main_pop])))
    txt = "\n".join(OUT)
    (HERE / "oos.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
