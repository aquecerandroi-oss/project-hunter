"""R74 / H-012 — o segundo eixo: tempo maximo de permanencia `max_hold in {30, 60, 120, 300} s`.

Pre-registo escrito na fila ANTES de correr este modulo (bloco `## H-012`). Linha principal =
alvo 1,15x; linha secundaria (descritiva) = o melhor alvo da grade da fila da H-011 nesta
populacao, escolhido pelo D medio do eixo do alvo a 300 s (nunca olhando o eixo do tempo).
Controlo sempre = regra atual 1,15x / 10 % / 300 s. `uv run python hold.py > hold.txt`
"""

from __future__ import annotations

import statistics
from decimal import Decimal

import policies  # noqa: F401  (poe o r72 no sys.path)
from load import load_all, resolvable
from policies import Target, run_exit
from report import CAT, COSTS, LATS, Q_TARGETS, cell, one_per_mint, pct
from stats import holm, perm_p, verdict, wilson

HOLDS = [30, 60, 120, 300]
H_NAMES = [str(h) for h in HOLDS]


def run(elig, tx, cost, lat):
    return {str(h): {P["pid"]: run_exit(P, Target(tx), cost=cost, latency_s=lat, seconds=h)
                     for P in elig} for h in HOLDS}


def best_target(elig):
    """Melhor alvo da grade da fila pelo D medio a 300 s, empate -> interior. So eixo do alvo."""
    ctrl = {P["pid"]: run_exit(P, Target("1.15"))["pnl"] for P in elig}
    edge = (Q_TARGETS[0], Q_TARGETS[-1])
    score = {}
    for tx in Q_TARGETS:
        if tx == "1.15":
            continue
        d = [run_exit(P, Target(tx))["pnl"] - ctrl[P["pid"]] for P in elig]
        score[tx] = sum(d) / len(d)
    return max(score, key=lambda t: (score[t], t not in edge))


def table(elig, res, ctrl, label):
    print("\n  %s — contra a regra atual (1,15x / 300 s), mesma posicao" % label)
    print("  %-5s %9s %6s %6s %6s %16s %9s %9s %9s %9s %8s %8s %11s %9s" % (
        "hold", "PnL/SOL", "ganho", "alvo", "recuo", ">=-50% [Wilson]", "pior", "D", "IC inf",
        "IC sup", "p", "Holm", "vit.cortad", "SOL cort"))
    cells = {}
    for h in H_NAMES:
        c = cells[h] = cell(elig, res[h], ctrl)
        c["p"] = perm_p(c["d"], [P["mint"] for P in c["ok"]])
    hp = holm({h: cells[h]["p"] for h in H_NAMES if h != "300"})
    for h in H_NAMES:
        r, c = res[h], cells[h]
        pnl = [r[P["pid"]]["pnl"] for P in elig]
        k = sum(1 for v in pnl if v <= CAT)
        lo_w, hi_w = wilson(k, len(pnl))
        # vitorias cortadas: a regra atual saiu pelo alvo, esta celula saiu por tempo antes dele
        cut = [P for P in elig if ctrl[P["pid"]]["reason"] == "policy" and r[P["pid"]]["reason"] == "time_stop"]
        sol_cut = sum(r[P["pid"]]["final"] - ctrl[P["pid"]]["final"] for P in cut) / 1e9
        n_rows = len(pnl)
        print("  %-5s %9s %5.0f%% %5.0f%% %5.0f%% %5.1f%% [%4.1f-%4.1f] %9s %9s %9s %9s %8.4f %8.4f %5d de %3d %+9.4f" % (
            h, pct(sum(pnl) / n_rows), 100 * sum(1 for v in pnl if v > 0) / n_rows,
            100 * sum(1 for P in elig if r[P["pid"]]["reason"] == "policy") / n_rows,
            100 * sum(1 for P in elig if r[P["pid"]]["reason"] == "trailing") / n_rows,
            100 * k / n_rows, lo_w * 100, hi_w * 100, pct(min(pnl)), pct(c["D"]), pct(c["lo"]),
            pct(c["hi"]), c["p"], hp.get(h, 1.0), len(cut),
            sum(1 for P in elig if ctrl[P["pid"]]["reason"] == "policy"), sol_cut))
    return cells


def when_target(elig, ctrl):
    """Quando a regra atual bate o alvo: distribuicao do tempo ate ao pouso."""
    t = sorted(ctrl[P["pid"]]["hold_s"] for P in elig if ctrl[P["pid"]]["reason"] == "policy")
    if not t:
        return
    q = statistics.quantiles(t, n=4) if len(t) > 3 else t
    print("  a regra atual bate o alvo em %d posicoes; pouso aos: <=31,6 s %d | <=61,6 s %d | <=121,6 s %d"
          " | quartis %s s" % (len(t), sum(1 for x in t if x <= 31.6), sum(1 for x in t if x <= 61.6),
                               sum(1 for x in t if x <= 121.6), ", ".join("%.0f" % x for x in q)))
    losers = [ctrl[P["pid"]] for P in elig if ctrl[P["pid"]]["pnl"] <= CAT]
    print("  perdas >= 50 %% da regra atual: %d; pouso aos %s s" % (
        len(losers), ", ".join("%.0f" % x["hold_s"] for x in sorted(losers, key=lambda x: x["hold_s"]))))


def main():
    real, paper = load_all()
    for label, pop in (("REAIS", real), ("PAPEL", paper)):
        elig = one_per_mint([P for P in pop if resolvable(P)])
        print("\n" + "=" * 118)
        print("H-012 POPULACAO %s: n=%d (a mesma da H-011, uma por mint)" % (label, len(elig)))
        bt = best_target(elig)
        print("  melhor alvo da grade da fila (eixo do alvo, 300 s): %s" % bt)
        sens = {}
        for c in COSTS:
            for lt in LATS:
                ctrl_c = {P["pid"]: run_exit(P, Target("1.15"), cost=c, latency_s=lt) for P in elig}
                main_c = run(elig, "1.15", c, lt)
                if (c, lt) == (COSTS[0], LATS[0]):
                    when_target(elig, ctrl_c)
                    cells = table(elig, main_c, ctrl_c, "LINHA PRINCIPAL alvo 1,15x (base 2,23 % / 1,6 s)")
                    table(elig, run(elig, bt, c, lt), ctrl_c, "LINHA SECUNDARIA alvo %sx (descritiva)" % bt)
                sens[(c, lt)] = {h: cell(elig, main_c[h], ctrl_c) for h in H_NAMES}
        print("\n  SENSIBILIDADE da linha principal — D [IC95]")
        for h in H_NAMES:
            print("  %-5s" % h + "".join("  c=%.2f%%/%.1fs %s [%s,%s]" % (
                float(k[0]) * 100, k[1], pct(sens[k][h]["D"]).strip(), pct(sens[k][h]["lo"]).strip(),
                pct(sens[k][h]["hi"]).strip()) for k in sens))
        v, why = verdict(cells, sens[(COSTS[0], 5.0)], H_NAMES, [], "300")
        print("\n  VEREDITO H-012 %s pela regra congelada: %s" % (label, v))
        for w in why:
            print("    - " + w)


if __name__ == "__main__":
    assert Decimal("1.15") and CAT == Decimal("-0.5")
    main()
