# R89 — roda a H-032 exatamente como registrada (prereg_frozen.md + emenda1.md) e imprime o relatório.
import os
from collections import Counter
from decimal import Decimal

import numpy as np

import h032 as h

HERE = os.path.dirname(os.path.abspath(__file__))
rows_all = h.load(os.path.join(HERE, "cache", "pop.csv"))
print(f"linhas extraídas: {len(rows_all)}")
print("estrato × p:", Counter((r.stratum, str(r.p)) for r in rows_all))
pop = [r for r in rows_all if r.stratum == "B"]
print(f"fora (estrato ≠ B): {len(rows_all) - len(pop)} | mayhem_unknown: {sum(r.mayhem is None for r in pop)}")
assert len({str(r.p) for r in pop}) == 1, "probabilidades distintas: usar Hájek"
pop = [r for r in pop if r.mayhem is not None]
M = [r for r in pop if r.mayhem]
N = [r for r in pop if not r.mayhem]

# ---------- portões de instrumento ----------
print("\n== I1 concordância do bit (denominador: todas as apostas; nulo = discordância)")
disc = [r for r in pop if not (r.mayhem == r.tok_flag == r.snap_flag)]
print(f"registros sem concordância (inclui bit nulo e a proposta sem aposta) {len(disc)} de {len(pop)} = {len(disc) / len(pop):.4%}; tok nulo {sum(r.tok_flag is None for r in pop)}, foto nula {sum(r.snap_flag is None for r in pop)}")
i1 = len(disc) / len(pop) <= 0.01

print("\n== ausentes por grupo (aberta, unfilled, pnl nulo, indeterminate, proposta sem aposta)")
miss = {}
for name, g in (("Mayhem", M), ("não-Mayhem", N)):
    m = [r for r in g if not r.resolved]
    miss[name] = len(m) / len(g)
    print(f"{name}: n={len(g)} resolvidas={len(g) - len(m)} ausentes={len(m)} ({len(m) / len(g):.2%})")
i_miss = max(miss.values()) <= 0.20

print("\n== I2 teto de SOL real")
for name, g in (("Mayhem", M), ("não-Mayhem", N)):
    rs = np.array([float(r.snap["real_sol_reserves"]) for r in g if r.snap and r.snap.get("real_sol_reserves") is not None])
    capped = [r for r in g if r.resolved and r.cap_applied]
    res = [r for r in g if r.resolved]
    print(f"{name}: SOL real na foto de entrada p10/p50/p90 = {np.quantile(rs, [.1, .5, .9]).round(4)}; < 0,7 SOL: {np.mean(rs < 0.7):.1%}; "
          f"saídas com teto {len(capped)} de {len(res)} = {len(capped) / len(res):.2%}")
cap_m = sum(1 for r in M if r.resolved and r.cap_applied) / sum(1 for r in M if r.resolved)
i2 = cap_m <= 0.10

print("\n== I3 ida e volta sem movimento externo (recomputada da foto de entrada)")
i3_ok = True
for name, g in (("Mayhem", M), ("não-Mayhem", N)):
    errs, free, capd = [], [], []
    for r in g:
        if r.snap is None or r.entry_tokens is None:
            continue
        tok, rf, rc = h.round_trip(r.snap, r.size, r.fee_pct, r.prio, mayhem=bool(r.mayhem))
        errs.append(abs(float(tok / r.entry_tokens) - 1))
        free.append(rf)
        capd.append(rc)
    errs, free, capd = np.array(errs), np.array(capd) * 0 + np.array(free), np.array(capd)
    share = float(np.mean(errs <= 0.005))
    i3_ok &= share >= 0.99
    print(f"{name}: avaliáveis n={errs.size} (só compra; não valida a venda Mayhem) |tokens/entry−1| ≤ 0,5 % em {share:.2%} (máx {errs.max():.2e}); ida e volta sem teto mediana {np.median(free):+.4f}; "
          f"com teto no SOL real observado mediana {np.median(capd):+.4f}, < −10 % em {np.mean(capd < -0.10):.1%}")
instrument_ok = i1 and i2 and i3_ok and i_miss
print(f"\nI1 {i1} · I2 {i2} (teto Mayhem {cap_m:.2%}) · I3 {i3_ok} · ausentes ≤ 20 % {i_miss} → instrumento ok = {instrument_ok}")

# ---------- dado e suporte ----------
res_m = sum(r.resolved for r in M)
res_n = sum(r.resolved for r in N)
days_both = {r.t.date() for r in M if r.resolved} & {r.t.date() for r in N if r.resolved}
data_ok = res_m >= 150 and res_n >= 300 and len(days_both) >= 10
print(f"\n== dado: Mayhem resolvidas {res_m} (≥150), não-Mayhem {res_n} (≥300), dias com os dois {len(days_both)} (≥10) → {data_ok}")

cuts = h.population_cuts(pop, h.FAMILIES_PRIMARY)
cuts_s = h.population_cuts(pop, h.FAMILIES_SENSITIVITY)
print(f"cortes n_outras_limpa (primário) c1={cuts[0]:.3f} c2={cuts[1]:.3f}; sensibilidade c1={cuts_s[0]:.3f} c2={cuts_s[1]:.3f}")
for name, g in (("Mayhem", M), ("não-Mayhem", N)):
    terc = Counter(h._tercile(h.n_outras(r.refusals, h.FAMILIES_PRIMARY), cuts) for r in g)
    print(f"  tercis {name}: {dict(sorted(terc.items()))}")
adj = h.d_adj(pop, h.FAMILIES_PRIMARY, cuts=cuts)
support_ok = adj.drop_m <= 0.20 and adj.drop_n <= 0.20
print(f"suporte: estratos usados {adj.strata}; descartados Mayhem {adj.drop_m:.2%}, não-Mayhem {adj.drop_n:.2%} → {support_ok}")

# ---------- primário ----------
b_h = h.bootstrap(pop, h.FAMILIES_PRIMARY, cuts, block="hour")
lo, hi, nf = h.ci(b_h)
p = h.centered_p(b_h, adj.d)
b_d = h.bootstrap(pop, h.FAMILIES_PRIMARY, cuts, block="day")
lo_d, hi_d, nf_d = h.ci(b_d)
raw = h.raw_d(pop)
print("\n== PRIMÁRIO D_adj = não-Mayhem − Mayhem (estratos dia × 6 h × tercil)")
print(f"D_adj = {adj.d:+.4f}  IC95 blocos 60 min [{lo:+.4f}, {hi:+.4f}] (não finitas {nf:.2%})  p centrado {p:.4f}")
print(f"IC95 blocos de dia [{lo_d:+.4f}, {hi_d:+.4f}] (não finitas {nf_d:.2%}); blocos de 60 min: {len({r.t.strftime('%Y%m%d%H') for r in pop if r.resolved})}")
print(f"bruto (descritivo) D = {raw:+.4f}; média Mayhem {np.mean([r.ret for r in M if r.resolved]):+.4f}, não-Mayhem {np.mean([r.ret for r in N if r.resolved]):+.4f}")
print(f"medianas: Mayhem {np.median([r.ret for r in M if r.resolved]):+.4f}, não-Mayhem {np.median([r.ret for r in N if r.resolved]):+.4f}")
print(f"nível com custo da mesa real (+1,27 pp, descritivo): Mayhem {np.mean([r.ret for r in M if r.resolved]) + 0.0127:+.4f}, não-Mayhem {np.mean([r.ret for r in N if r.resolved]) + 0.0127:+.4f}")

# ---------- robustez ----------
print("\n== robustez (sinal de D_adj)")
rob = {}
first = [r for r in pop if r.t < h.SPLIT]
second = [r for r in pop if r.t >= h.SPLIT]
rob["metade 1 (< 30/09)"] = h.d_adj(first, h.FAMILIES_PRIMARY, cuts=cuts).d
rob["metade 2 (≥ 30/09)"] = h.d_adj(second, h.FAMILIES_PRIMARY, cuts=cuts).d
rob["params com line_support_causal"] = h.d_adj([r for r in pop if r.causal], h.FAMILIES_PRIMARY, cuts=cuts).d
rob["params sem line_support_causal"] = h.d_adj([r for r in pop if not r.causal], h.FAMILIES_PRIMARY, cuts=cuts).d
rob["famílias de volume/fluxo fora"] = h.d_adj(pop, h.FAMILIES_SENSITIVITY, cuts=cuts_s).d
for k, v in rob.items():
    print(f"  {k}: {v:+.4f}")
robust = all(v > 0 for v in rob.values())

# ---------- censura ----------
print("\n== censura (cenários de imputação)")
sc = {}
for s in ("favor", "contra"):
    rr = h.impute(pop, s)
    a = h.d_adj(rr, h.FAMILIES_PRIMARY, cuts=cuts)
    b = h.bootstrap(rr, h.FAMILIES_PRIMARY, cuts, block="hour")
    l, u, _ = h.ci(b)
    sc[s] = (a.d, l, u)
    print(f"  {s} da exclusão: D_adj {a.d:+.4f} [{l:+.4f}, {u:+.4f}]")
missing_n = [r for r in N if not r.resolved]
if missing_n:
    for v in (-1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 5.0):
        rr = [h.replace_ret(r, v) if (r in missing_n) else r for r in pop]
        print(f"  grade de imputação (não é limiar; o rótulo não muda enquanto I1/I2 falharem): ausentes não-Mayhem = {v:+.1f} → D_adj {h.d_adj(rr, h.FAMILIES_PRIMARY, cuts=cuts).d:+.4f}")

lab, why = h.label(instrument_ok=instrument_ok, data_ok=data_ok, support_ok=support_ok, nonfinite_ok=nf <= 0.01,
                   d=adj.d, lo=lo, hi=hi, p=p, lo_day=lo_d, robust=robust, raw_same_sign=(raw > 0) == (adj.d > 0),
                   lo_fav=sc["favor"][1], lo_con=sc["contra"][1], hi_fav=sc["favor"][2], hi_con=sc["contra"][2])
print(f"\nRÓTULO: {lab} — {why}")
pista = hi < 0
print(f"pista contrária (IC inteiro abaixo de zero, Mayhem melhor): {pista}")

# ---------- secundárias (descritivas) ----------
print("\n== secundárias (descritivas, não decidem)")
for name, g in (("Mayhem", M), ("não-Mayhem", N)):
    res = [r for r in g if r.resolved]
    bt = [h.bought_top(r) for r in res]
    bt = [x for x in bt if x is not None]
    print(f"{name}: comprou_no_topo {np.mean(bt):.2%} (n {len(bt)}); ret ≤ −0,5 {np.mean([r.ret <= -0.5 for r in res]):.2%}; "
          f"ret ≥ +0,10 {np.mean([r.ret >= 0.10 for r in res]):.2%}; acerto (ret > 0) {np.mean([r.ret > 0 for r in res]):.2%}")
    print(f"   saídas: {dict(Counter(r.exit_reason for r in res).most_common())}")
btm = np.mean([h.bought_top(r) for r in M if r.resolved and h.bought_top(r) is not None])
btn = np.mean([h.bought_top(r) for r in N if r.resolved and h.bought_top(r) is not None])
print(f"comprou_no_topo Mayhem ÷ não-Mayhem = {btm / btn:.2f}× (previsão secundária ≥ 1,5×)")
clean_m = [r for r in M if not r.cap_applied and r.snap and float(r.snap["real_sol_reserves"]) >= 0.7]
sub = clean_m + N
print(f"D_adj só com Mayhem sem teto e SOL real na entrada ≥ 0,7 (descritivo): {h.d_adj(sub, h.FAMILIES_PRIMARY, cuts=cuts).d:+.4f} (Mayhem n={len(clean_m)})")
perm_rng = np.random.default_rng(h.SEED)
u = [r for r in pop if r.resolved]
days = np.array([r.t.date().toordinal() for r in u])
y = np.array([r.ret for r in u])
lab_m = np.array([bool(r.mayhem) for r in u])
obs = y[~lab_m].mean() - y[lab_m].mean()
cnt = 0
for _ in range(h.REPS):
    perm = lab_m.copy()
    for dd in np.unique(days):
        ix = np.flatnonzero(days == dd)
        perm[ix] = perm_rng.permutation(perm[ix])
    cnt += abs(y[~perm].mean() - y[perm].mean()) >= abs(obs)
print(f"permutação dentro do dia (bruto, descritiva): p = {(1 + cnt) / (h.REPS + 1):.4f}")
