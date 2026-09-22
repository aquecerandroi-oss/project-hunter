"""R65 - Q4: contrafactuais sobre as 87 reais.

(a) regra atual com o rent da ATA devolvido; (b) regra atual restrita a baldes; (c) saidas por
creator_dump tratadas de outra forma (o que a fita mostra depois do gatilho); (d) operator/6 vs /5.
Nao re-simula a saida: usa o PnL real e soma/subtrai componentes de custo conhecidos (Decimal),
excepto em (c), onde a fita reconstruida responde "o dinheiro ficou na mesa?".
"""
from decimal import Decimal
from datetime import timedelta
from pathlib import Path

from costs import load_costs, sol
from load import BRT, load_all

HERE = Path(__file__).resolve().parent
OUT = []
RENT = Decimal("0.001513840")  # rent de uma ATA nova (lamports/1e9)


def p(s=""):
    OUT.append(s)


def by_day(ps, adj=None):
    d = {}
    for P in ps:
        v = P["pnl_sol"] + (adj(P) if adj else Decimal(0))
        d[P["day_brt"]] = d.get(P["day_brt"], Decimal(0)) + v
    return d


def line(name, ps, adj=None):
    d = by_day(ps, adj)
    tot = sum(d.values(), Decimal(0))
    pos = sum(1 for v in d.values() if v > 0)
    p("%-46s n=%3d  total=%12s  dias verdes=%d/%d  %s" % (
        name, len(ps), tot.quantize(Decimal("0.0001")), pos, len(d),
        " ".join("%s:%+.4f" % (k.strftime("%d"), v) for k, v in sorted(d.items()))))
    return tot


def main():
    positions, _t, _s = load_all()
    C = load_costs()
    for P in positions:
        P["c"] = C[P["proposal_id"]]

    p("=" * 150)
    p("Q4 - CONTRAFACTUAIS (SOL; 'dias verdes' = dias que fecham liquidos positivos, a meta do Everton)")
    p("=" * 150)
    base = line("(0) real, como aconteceu", positions)
    rent = line("(a) mesma regra, rent da ATA devolvido", positions,
                lambda P: sol(P["c"]["ata_rent"]))
    p("     efeito do rent: %s SOL (%s%% do prejuizo)" % (
        (rent - base).quantize(Decimal("0.0001")),
        ((rent - base) / -base * 100).quantize(Decimal("0.1"))))

    p("")
    p("(b) mesma regra + rent devolvido, RESTRITA a um balde (as operacoes fora do balde nao existem):")
    rules = [
        ("buys_1m <= 25", lambda P: (P["g"].get("buys_1m") or 0) <= 25),
        ("buys_1m <= 37", lambda P: (P["g"].get("buys_1m") or 0) <= 37),
        ("unique_buyers_1m <= 22", lambda P: (P["g"].get("unique_buyers_1m") or 0) <= 22),
        ("unique_buyers_1m <= 32", lambda P: (P["g"].get("unique_buyers_1m") or 0) <= 32),
        ("mcap_delta_60s <= 13 SOL", lambda P: (P["g"].get("mcap_delta_60s") or Decimal(0)) <= 13),
        ("progresso <= 70 %", lambda P: (P["g"].get("progress_pct") or Decimal(0)) <= 70),
        ("sells/buys <= 0.25", lambda P: _sb(P) is not None and _sb(P) <= Decimal("0.25")),
        ("hora 00-11h BRT", lambda P: P["hour_brt"] <= 11),
        ("buys_1m<=25 E progresso<=70", lambda P: (P["g"].get("buys_1m") or 0) <= 25
            and (P["g"].get("progress_pct") or Decimal(0)) <= 70),
        ("buys_1m<=25 E sells/buys<=0.35", lambda P: (P["g"].get("buys_1m") or 0) <= 25
            and _sb(P) is not None and _sb(P) <= Decimal("0.35")),
        ("buys_1m<=25 E dev_share=0", lambda P: (P["g"].get("buys_1m") or 0) <= 25
            and (P["g"].get("dev_share") or Decimal(0)) == 0),
    ]
    for name, fn in rules:
        line("    " + name, [P for P in positions if fn(P)], lambda P: sol(P["c"]["ata_rent"]))

    # ---------- (c) creator_dump ----------
    p("")
    p("=" * 150)
    p("(c) as %d saidas por creator_dump - o gatilho saiu cedo ou a entrada estava errada?" % (
        sum(1 for P in positions if P["reason"] == "creator_dump")))
    p("=" * 150)
    p("%-13s %-14s %7s %7s %8s %8s %9s %9s %10s %6s" % (
        "moeda", "entrada", "seg", "MFE ate", "marca", "max apos", "300 s", "PnL real", "segurar*", "dev"))
    cd = [P for P in positions if P["reason"] == "creator_dump"]
    tot_hold = Decimal(0)
    for P in cd:
        mark_exit, mx_after, t_after = _after(P)
        hold = (Decimal(P["mark300"] or 0) / 100 * P["spent"] / Decimal(10**9)) if P["mark300"] is not None else P["pnl_sol"]
        tot_hold += hold
        p("%-13s %-14s %7.0f %7s %8s %8s %9s %9s %10s %6s" % (
            P["tag"][:13], P["entry_at"].astimezone(BRT).strftime("%d/%m %H:%M:%S"), P["hold_s"],
            _pc(P["mfe_to_exit"]), _pc(mark_exit), _pc(mx_after), _pc(P["mark300"]),
            P["pnl_sol"].quantize(Decimal("0.0001")), hold.quantize(Decimal("0.0001")),
            str(P["g"].get("dev_share", "-"))))
    p("-" * 150)
    p("creator_dump: PnL real %s SOL | segurar ate os 300 s daria %s SOL" % (
        sum(P["pnl_sol"] for P in cd).quantize(Decimal("0.0001")), tot_hold.quantize(Decimal("0.0001"))))
    p("*'segurar' = marca reconstruida aos 300 s x gasto (ignora o nosso impacto na venda); "
      "moedas so com fotos = piso de 15 s")
    p("creator_net_seller na entrada: %d de %d ja marcavam 'S'; dev_share > 0 em %d" % (
        sum(1 for P in cd if P["g"].get("creator_net_seller")), len(cd),
        sum(1 for P in cd if (P["g"].get("dev_share") or Decimal(0)) > 0)))
    p("tempo entre entrada e gatilho: min %.0f s, mediana %.0f s, max %.0f s" % (
        min(P["hold_s"] for P in cd), sorted(P["hold_s"] for P in cd)[len(cd) // 2],
        max(P["hold_s"] for P in cd)))
    line("    sem creator_dump (nao entrar nelas) + rent", [P for P in positions if P["reason"] != "creator_dump"],
         lambda P: sol(P["c"]["ata_rent"]))

    # ---------- (d) conjuntos ----------
    p("")
    p("=" * 150)
    p("(d) operator/5 vs operator/6")
    p("=" * 150)
    for s in ("operator/5", "operator/6"):
        G = [P for P in positions if P["set"] == s]
        line("    " + s, G)
    p("    ver stats.txt: dif = -0.00167 SOL/op, p_perm = 0.64 -> indistinguivel de ruido com n=65/22.")
    p("    6 mints foram comprados pelos DOIS conjuntos com menos de 90 s de diferenca:")
    pares = {}
    for P in positions:
        pares.setdefault(P["mint"], []).append(P)
    flip = 0
    for v in pares.values():
        if len(v) < 2:
            continue
        reasons = {x["reason"] for x in v}
        if "target" in reasons and "trailing" in reasons:
            flip += 1
        p("      %-12s %s" % (v[0]["sym"][:12], " | ".join(
            "%s %s %s (%+.0fs)" % (x["set"], x["reason"], x["pnl_sol"].quantize(Decimal("0.0001")),
                                   (x["entry_at"] - v[0]["entry_at"]).total_seconds()) for x in v)))
    p("    em %d desses pares um lado fez ALVO e o outro TRAILING com as mesmas features de entrada." % flip)

    # ---------- resumo da meta ----------
    p("")
    p("=" * 150)
    p("META DO EVERTON: quantos dos 6 dias fecham verdes em cada cenario")
    p("=" * 150)
    for name, ps, adj in (
        ("real", positions, None),
        ("rent devolvido", positions, lambda P: sol(P["c"]["ata_rent"])),
        ("rent + buys_1m<=25", [P for P in positions if (P["g"].get("buys_1m") or 0) <= 25],
         lambda P: sol(P["c"]["ata_rent"])),
        ("rent + buys_1m<=25 + sem creator_dump",
         [P for P in positions if (P["g"].get("buys_1m") or 0) <= 25 and P["reason"] != "creator_dump"],
         lambda P: sol(P["c"]["ata_rent"])),
    ):
        line("    " + name, ps, adj)


def _sb(P):
    b = P["g"].get("buys_1m")
    s = P["g"].get("sells_1m")
    if not b:
        return None
    return Decimal(s) / Decimal(b)


def _pc(x):
    return "n/a" if x is None else "%+.1f" % x


def _after(P):
    """(marca na saida, max da marca depois da saida ate 300 s, t desse max)."""
    spent = P["spent"]
    mark_exit = None
    mx = None
    tmx = 0
    end = P["entry_bt"] + timedelta(seconds=300)
    for t, _v, _w, m, _ in P["path"]:
        pct = (Decimal(m) - spent) / spent * 100
        if t <= P["exit_bt"]:
            mark_exit = pct
        elif t <= end:
            if mx is None or pct > mx:
                mx, tmx = pct, (t - P["entry_bt"]).total_seconds()
    return mark_exit, mx, tmx


if __name__ == "__main__":
    main()
    txt = "\n".join(OUT)
    (HERE / "cf.txt").write_text(txt, encoding="utf-8")
    print(txt)
