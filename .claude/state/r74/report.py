"""R74 — corre a grade da H-011 nas duas populacoes e imprime o relatorio bruto.

`uv run python report.py > out.txt`

Grade PRINCIPAL = a da fila (alvos 1,08-1,30 + repiques 3/5/8 %). O 1,50 e extensao declarada
do brief (Astra, pre-corrida: acrescenta-lo muda o que e "borda"). Veredito das duas grades.
"""

from __future__ import annotations

import statistics
from decimal import Decimal

import policies  # noqa: F401  (poe o r72 no sys.path)
from load import load_all, resolvable
from policies import CONTROL_X, EntryPop, FirstPop, Target, run_exit
from sim import per_sol, simulate_cheat, simulate_current
from stats import boot_ci, holm, perm_p, verdict, wilson

TARGETS = ["1.08", "1.12", "1.15", "1.20", "1.30", "1.50"]
Q_TARGETS = TARGETS[:-1]  # grade da fila
POPS = ["pop3", "pop5", "pop8"]
CONTROL = "1.15"
COSTS = (Decimal("0.0223"), Decimal("0.025"), Decimal("0.03"))
LATS = (1.6, 5.0)
CAT = Decimal("-0.5")


def make(name):
    if name.startswith("pop"):
        return FirstPop(int(name[3:]))
    if name.startswith("r72_"):
        return EntryPop(int(name[4:]))
    return Target(name)


def pct(v):
    return "      -" if v is None else "%+7.2f%%" % (float(v) * 100)


def one_per_mint(pop):
    """Uma posicao por mint, a PRIMEIRA no tempo (regra congelada, nunca pelo resultado)."""
    seen, out = set(), []
    for P in sorted(pop, key=lambda P: P["entry_bt"]):
        if P["mint"] not in seen:
            seen.add(P["mint"])
            out.append(P)
    return out


def simulate(elig, names, cost, lat, **kw):
    return {n: {P["pid"]: run_exit(P, make(n), cost=cost, latency_s=lat, **kw) for P in elig}
            for n in names}


def cell(elig, res, ctrl):
    ok = [P for P in elig if res[P["pid"]]["ok"] and ctrl[P["pid"]]["ok"]]
    d = [res[P["pid"]]["pnl"] - ctrl[P["pid"]]["pnl"] for P in ok]
    lo, hi = boot_ci(d, [P["mint"] for P in ok])
    return dict(n=len(ok), D=float(sum(d) / len(d)), lo=lo, hi=hi, d=d, ok=ok)


def _avg(v):
    v = [x for x in v if x is not None]
    return (sum(v) / len(v)) if v else None


def describe(elig, r):
    rows = [r[P["pid"]] for P in elig if r[P["pid"]]["ok"]]
    pnl = [x["pnl"] for x in rows]
    cat = sum(1 for v in pnl if v <= CAT)
    return dict(
        n=len(rows), mean=sum(pnl) / len(pnl), win=sum(1 for v in pnl if v > 0) / len(pnl),
        hit=sum(1 for x in rows if x["reason"] == "policy") / len(rows),
        trail=sum(1 for x in rows if x["reason"] == "trailing") / len(rows),
        hold=statistics.median(x["hold_s"] for x in rows), worst=min(pnl),
        cat=cat / len(pnl), cat_ci=wilson(cat, len(pnl)), sol=sum(x["final"] for x in rows))


def left_by_reason(elig, r):
    """Na mesa, estratificado por motivo (Astra): contagem, disponiveis, restante, max e 300 s."""
    out = {}
    for why in ("policy", "trailing"):
        rows = [r[P["pid"]] for P in elig if r[P["pid"]]["ok"] and r[P["pid"]]["reason"] == why]
        av = [x for x in rows if x["left_max"] is not None]
        out[why] = dict(
            n=len(rows), av=len(av),
            rest=statistics.median(301.6 - x["hold_s"] for x in rows) if rows else None,
            lmax=_avg([x["left_max_pct"] for x in av]),
            lmax_med=statistics.median(x["left_max_pct"] for x in av) if av else None,
            lend=_avg([x["left_end_pct"] for x in av]),
            lend_med=statistics.median(x["left_end_pct"] for x in av) if av else None,
            better=(sum(1 for x in av if x["left_end"] > 0) / len(av)) if av else None,
            sol_max=sum(x["left_max"] for x in av) / 1e9, sol_end=sum(x["left_end"] for x in av) / 1e9)
    return out


def discord(elig, r, ctrl):
    """Perdas >= 50 % criadas / evitadas face ao controlo, na mesma posicao."""
    made = sum(1 for P in elig if r[P["pid"]]["pnl"] <= CAT < ctrl[P["pid"]]["pnl"])
    saved = sum(1 for P in elig if ctrl[P["pid"]]["pnl"] <= CAT < r[P["pid"]]["pnl"])
    return made, saved


def section_policies(elig, base, names):
    ctrl = base[CONTROL]
    print("\n  BASE: custo 2,23 % ida e volta (entrada historica + c/2 na saida), atraso 1,6 s,"
          " recuo 10 % armado na entrada, 300 s")
    print("  sai = fracao que saiu pela propria politica (alvo/repique); cri/ev = perdas >= 50 %"
          " criadas/evitadas face ao 1,15x")
    print("  %-6s %9s %6s %6s %6s %6s %9s %16s %7s %9s" % (
        "polit.", "PnL/SOL", "ganho", "sai", "recuo", "hold", "pior", ">=-50% [Wilson]",
        "cri/ev", "SOL fim"))
    for n in names:
        s = describe(elig, base[n])
        mk, sv = discord(elig, base[n], ctrl)
        print("  %-6s %9s %5.0f%% %5.0f%% %5.0f%% %5.0fs %9s %5.1f%% [%4.1f-%4.1f] %7s %9.4f" % (
            n, pct(s["mean"]), s["win"] * 100, s["hit"] * 100, s["trail"] * 100, s["hold"],
            pct(s["worst"]), s["cat"] * 100, s["cat_ci"][0] * 100, s["cat_ci"][1] * 100,
            "%d/%d" % (mk, sv), s["sol"] / 1e9))
    print("\n  NA MESA (ex post, teto oraculo; nao entra no veredito). Por motivo de saida:")
    print("  %-6s %-8s %4s %4s %6s %9s %9s %9s %9s %6s %8s %8s" % (
        "polit.", "motivo", "n", "disp", "resta", "mesaMAX", "(med)", "seg.300", "(med)",
        "300>", "SOLmax", "SOL300"))
    for n in names:
        for why, v in left_by_reason(elig, base[n]).items():
            if not v["n"]:
                continue
            print("  %-6s %-8s %4d %4d %5.0fs %9s %9s %9s %9s %5s %8.4f %+8.4f" % (
                n, why, v["n"], v["av"], v["rest"], pct(v["lmax"]), pct(v["lmax_med"]),
                pct(v["lend"]), pct(v["lend_med"]),
                "-" if v["better"] is None else "%.0f%%" % (v["better"] * 100),
                v["sol_max"], v["sol_end"]))


def section_contrast(elig, base, names):
    ctrl = base[CONTROL]
    print("\n  CONTRASTE EMPARELHADO D = politica - alvo 1,15x (mesma posicao); bootstrap por mint"
          " 10 000; permutacao por troca de sinal por mint 10 000; Holm na familia de %d" % (len(names) - 1))
    print("  %-6s %5s %9s %9s %9s %8s %8s %7s %7s" % (
        "polit.", "n", "D", "IC inf", "IC sup", "p", "Holm", "D>0", "D<0"))
    cells = {}
    for n in names:
        c = cells[n] = cell(elig, base[n], ctrl)
        c["p"] = perm_p(c["d"], [P["mint"] for P in c["ok"]]) if n != CONTROL else 1.0
    hp = holm({n: cells[n]["p"] for n in names if n != CONTROL})
    for n in names:
        c = cells[n]
        print("  %-6s %5d %9s %9s %9s %8.4f %8.4f %6.0f%% %6.0f%%" % (
            n, c["n"], pct(c["D"]), pct(c["lo"]), pct(c["hi"]), c["p"], hp.get(n, 1.0),
            100 * sum(1 for v in c["d"] if v > 0) / len(c["d"]),
            100 * sum(1 for v in c["d"] if v < 0) / len(c["d"])))
    print("\n  ESTRATOS DE COBERTURA (heterogeneidade, nao causa) — D medio por maior buraco na janela")
    for lab, keep in (("buraco <= 30 s", lambda P: P["max_gap_s"] <= 30),
                      ("buraco  > 30 s", lambda P: P["max_gap_s"] > 30)):
        sub = [P for P in elig if keep(P)]
        if not sub:
            continue
        print("    %s (n=%3d): " % (lab, len(sub)) + " | ".join(
            "%s %s" % (n, pct(sum(base[n][P["pid"]]["pnl"] - ctrl[P["pid"]]["pnl"] for P in sub)
                              / len(sub)).strip()) for n in names if n != CONTROL))
    return cells


def section_sensitivity(elig, base, names):
    print("\n  SENSIBILIDADE — D [IC95] da MESMA politica contra o 1,15x recalculado nas mesmas"
          " condicoes (a entrada fica historica; c muda so o c/2 da saida)")
    sens = {}
    for c in COSTS:
        for lt in LATS:
            res = base if (c, lt) == (COSTS[0], LATS[0]) else simulate(elig, names, c, lt)
            sens[(c, lt)] = {n: cell(elig, res[n], res[CONTROL]) for n in names}
    print("  %-6s" % "polit." + "".join("  %-24s" % ("c=%.2f%% lat=%.1fs" % (float(c) * 100, lt))
                                         for (c, lt) in sens))
    for n in names:
        print("  %-6s" % n + "".join("  %-24s" % ("%s [%s,%s]" % (
            pct(sens[k][n]["D"]).strip(), pct(sens[k][n]["lo"]).strip(), pct(sens[k][n]["hi"]).strip()))
            for k in sens))
    return sens


def section_diag(elig, base):
    ctrl = base[CONTROL]
    print("\n  DIAGNOSTICO (nao decisorio): a regra que o R72 mediu (+X % da marca de entrada, sem queda)"
          " e o repique sem recuo")
    rows = list(simulate(elig, ["r72_3", "r72_5", "r72_8"], COSTS[0], LATS[0]).items())
    rows += [("%s sem recuo" % k, v) for k, v in
             simulate(elig, POPS, COSTS[0], LATS[0], trailing=None).items()]
    for n, r in rows:
        c, s = cell(elig, r, ctrl), describe(elig, r)
        print("  %-15s PnL %s | D %s [%s, %s] | >=-50 %4.1f%% | pior %s | hold %3.0fs" % (
            n, pct(s["mean"]), pct(c["D"]), pct(c["lo"]), pct(c["hi"]), s["cat"] * 100,
            pct(s["worst"]), s["hold"]))


def main():
    real, paper = load_all()
    names = TARGETS + POPS
    for label, pop in (("REAIS", real), ("PAPEL", paper)):
        res_ = [P for P in pop if resolvable(P)]
        elig = one_per_mint(res_)
        print("\n" + "=" * 118)
        print("POPULACAO %s: exportadas=%d -> mints unicos=%d -> resolviveis=%d -> uma por mint=%d"
              % (label, len(pop), len({P["mint"] for P in pop}), len(res_), len(elig)))
        base = simulate(elig, names, COSTS[0], LATS[0])
        eq = sum(1 for P in elig if base[CONTROL][P["pid"]]["final"] == simulate_current(P)["final"])
        print("  equivalencia do controlo 1,15x com r72.sim.simulate_current: %d de %d" % (eq, len(elig)))
        cheat = [c for c in (per_sol(simulate_cheat(P), P) for P in elig) if c is not None]
        print("  oraculo (vende no maximo da janela olhando o futuro, controlo de fuga): %s por SOL"
              % pct(sum(cheat) / len(cheat)))
        section_policies(elig, base, names)
        cells = section_contrast(elig, base, names)
        sens = section_sensitivity(elig, base, names)
        lat5 = sens[(COSTS[0], 5.0)]
        for tg, lab in ((Q_TARGETS, "PRINCIPAL, grade da fila 1,08-1,30"),
                        (TARGETS, "extensao do brief 1,08-1,50")):
            v, why = verdict(cells, lat5, tg, POPS, CONTROL)
            print("\n  VEREDITO %s (%s): %s" % (label, lab, v))
            for w in why:
                print("    - " + w)
        section_diag(elig, base)
        pol = [base[CONTROL][P["pid"]] for P in elig if base[CONTROL][P["pid"]]["reason"] == "policy"]
        print("\n  REGRA ATUAL: PnL realizado nas %d saidas por alvo (o preco passou do alvo ate ao pouso?):"
              " mediana %s; as 10 maiores: %s" % (
                  len(pol), pct(statistics.median(x["pnl"] for x in pol)),
                  ", ".join(pct(x["pnl"]).strip() for x in sorted(pol, key=lambda x: -x["pnl"])[:10])))


if __name__ == "__main__":
    assert Decimal(CONTROL) == CONTROL_X
    main()
