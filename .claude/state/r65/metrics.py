"""R65 - Q1 (anatomia das 87), Q3 (decomposicao de custo por dia). Saida: metrics.txt + anat.csv."""
import csv
from decimal import Decimal
from pathlib import Path

from costs import load_costs, sol
from load import BRT, load_all

HERE = Path(__file__).resolve().parent
OUT = []


def p(s=""):
    OUT.append(s)


def d2(x, nd=1):
    return "n/a" if x is None else ("%+.*f" % (nd, x))


def q(P, k, nd=2):
    v = P["g"].get(k)
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "S" if v else "N"
    if isinstance(v, Decimal):
        return "%.*f" % (nd, v)
    return str(v)


def main():
    positions, _trades, _snaps = load_all()
    C = load_costs()
    for P in positions:
        P["c"] = C[P["proposal_id"]]

    # ---------- Q1: anatomia ----------
    p("=" * 150)
    p("Q1 - ANATOMIA DAS %d OPERACOES REAIS (horas BRT; valores do gate NA DECISAO; MFE/MAE em %% do gasto, ate 300 s)" % len(positions))
    p("=" * 150)
    hdr = ("%-3s %-13s %-14s %-11s %-12s %5s %6s %5s %5s %4s %5s %6s %6s %5s %8s %8s %8s %9s %7s" % (
        "#", "moeda", "entrada", "conjunto", "saida", "idade", "progr", "buy1m", "sel1m", "snp",
        "uniq", "netflow", "devshr", "realS", "MFE%", "MAE%", "300s%", "PnL SOL", "seg"))
    p(hdr)
    p("-" * 150)
    for i, P in enumerate(positions, 1):
        p("%-3d %-13s %-14s %-11s %-12s %5s %6s %5s %5s %4s %5s %6s %6s %5s %8s %8s %8s %9s %7.0f" % (
            i, P["tag"][:13], P["entry_at"].astimezone(BRT).strftime("%d/%m %H:%M:%S"), P["set"], P["reason"],
            q(P, "age_s", 0), q(P, "progress_pct", 1), q(P, "buys_1m"), q(P, "sells_1m"), q(P, "snipers"),
            q(P, "unique_buyers_1m"), q(P, "net_sol_flow_1m", 2), q(P, "dev_share", 3),
            ("%.1f" % P["quote_real_sol"]) if P["quote_real_sol"] else "-",
            d2(P["mfe"]), d2(P["mae"]), d2(P["mark300"]), P["pnl_sol"], P["hold_s"]))
    p("-" * 150)
    p("total PnL: %s SOL | fonte: fita+fotos %d, so fotos %d" % (
        sum(P["pnl_sol"] for P in positions),
        sum(1 for P in positions if P["source"] == "tape+photos"),
        sum(1 for P in positions if P["source"] == "photos")))
    p("(so-fotos = cadencia de 15 s: MFE/MAE sao PISO, nao maximo)")

    # anat.csv
    with open(HERE / "anat.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["tag", "mint", "set", "entry_brt", "hour_brt", "day_brt", "reason", "hold_s",
                "pnl_sol", "pnl_pct", "mfe", "mae", "mark300", "mfe_to_exit", "source", "n_trades",
                "age_s", "progress_pct", "buys_1m", "sells_1m", "snipers", "unique_buyers_1m",
                "net_sol_flow_1m", "mcap_delta_60s", "dev_share", "creator_net_seller",
                "holders_rising", "progress_rising", "participation_pct", "real_sol", "mcap_sol",
                "creator_prior_mints_1h", "symbol_dup_24h",
                "gross_curve_sol", "pf_fee_sol", "creator_fee_sol", "net_fee_sol", "ata_rent_sol",
                "exit_slip_sol"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for P in positions:
            c = P["c"]
            g = P["g"]
            w.writerow(dict(
                tag=P["tag"], mint=P["mint"], set=P["set"],
                entry_brt=P["entry_at"].astimezone(BRT).isoformat(), hour_brt=P["hour_brt"],
                day_brt=P["day_brt"], reason=P["reason"], hold_s=int(P["hold_s"]),
                pnl_sol=str(P["pnl_sol"]),
                pnl_pct=str((Decimal(P["received"] - P["spent"]) / P["spent"] * 100).quantize(Decimal("0.01"))),
                mfe=str(P["mfe"].quantize(Decimal("0.1"))) if P["mfe"] is not None else "",
                mae=str(P["mae"].quantize(Decimal("0.1"))) if P["mae"] is not None else "",
                mark300=str(P["mark300"].quantize(Decimal("0.1"))) if P["mark300"] is not None else "",
                mfe_to_exit=str(P["mfe_to_exit"].quantize(Decimal("0.1"))) if P["mfe_to_exit"] is not None else "",
                source=P["source"], n_trades=P["n_trades"],
                age_s=str(g.get("age_s", "")), progress_pct=str(g.get("progress_pct", "")),
                buys_1m=g.get("buys_1m", ""), sells_1m=g.get("sells_1m", ""),
                snipers=g.get("snipers", ""), unique_buyers_1m=g.get("unique_buyers_1m", ""),
                net_sol_flow_1m=str(g.get("net_sol_flow_1m", "")),
                mcap_delta_60s=str(g.get("mcap_delta_60s", "")), dev_share=str(g.get("dev_share", "")),
                creator_net_seller=g.get("creator_net_seller", ""),
                holders_rising=g.get("holders_rising", ""), progress_rising=g.get("progress_rising", ""),
                participation_pct=str(g.get("participation_pct", "")),
                real_sol=str(P["quote_real_sol"]), mcap_sol=str(P["quote_mcap_sol"]),
                creator_prior_mints_1h=g.get("creator_prior_mints_1h", ""),
                symbol_dup_24h=g.get("symbol_dup_24h", ""),
                gross_curve_sol=str(sol(c["gross_curve"])), pf_fee_sol=str(sol(c["pf_fee"])),
                creator_fee_sol=str(sol(c["creator_fee"])), net_fee_sol=str(sol(c["net_fee"])),
                ata_rent_sol=str(sol(c["ata_rent"])), exit_slip_sol=str(sol(c["exit_slip"]))))

    # ---------- Q3: decomposicao por dia ----------
    p("")
    p("=" * 118)
    p("Q3 - DECOMPOSICAO DO PnL LIQUIDO POR DIA (SOL; bruto = SOL que saiu da curva - SOL que entrou)")
    p("=" * 118)
    p("%-12s %4s %10s %10s %10s %10s %10s %10s %10s %10s" % (
        "dia BRT", "n", "bruto", "taxa pf", "taxa cri", "rede", "rent ATA", "soma cust", "liquido", "conf"))
    days = {}
    for P in positions:
        days.setdefault(P["day_brt"], []).append(P)
    tot = dict(n=0, g=0, pf=0, cf=0, nf=0, rent=0, slip=0)
    for day in sorted(days):
        G = days[day]
        g = sum(P["c"]["gross_curve"] for P in G)
        pf = sum(P["c"]["pf_fee"] for P in G)
        cf = sum(P["c"]["creator_fee"] for P in G)
        nf = sum(P["c"]["net_fee"] for P in G)
        rent = sum(P["c"]["ata_rent"] - P["c"]["ata_refund"] for P in G)
        net_ = sum(P["pnl_sol"] for P in G)
        p("%-12s %4d %10s %10s %10s %10s %10s %10s %10s %10s" % (
            day.strftime("%d/%m"), len(G), sol(g), -sol(pf), -sol(cf), -sol(nf), -sol(rent),
            -sol(pf + cf + nf + rent), net_, sol(g - pf - cf - nf - rent) - net_))
        tot["n"] += len(G); tot["g"] += g; tot["pf"] += pf; tot["cf"] += cf
        tot["nf"] += nf; tot["rent"] += rent
        tot["slip"] += sum(P["c"]["exit_slip"] for P in G)
    p("-" * 118)
    p("%-12s %4d %10s %10s %10s %10s %10s %10s %10s" % (
        "TOTAL", tot["n"], sol(tot["g"]), -sol(tot["pf"]), -sol(tot["cf"]), -sol(tot["nf"]),
        -sol(tot["rent"]), -sol(tot["pf"] + tot["cf"] + tot["nf"] + tot["rent"]),
        sum(P["pnl_sol"] for P in positions)))
    p("")
    p("derrapagem realizada na SAIDA (fill sell_net - intent.net_proceeds): %s SOL no total; "
      "mediana por op: %s" % (sol(tot["slip"]),
                              sol(sorted(P["c"]["exit_slip"] for P in positions)[len(positions) // 2])))
    p("custo por operacao (media): taxa pf %s + criador %s + rede %s + rent %s = %s SOL "
      "sobre um tamanho de 0,07 SOL" % (
          sol(tot["pf"] // tot["n"]), sol(tot["cf"] // tot["n"]), sol(tot["nf"] // tot["n"]),
          sol(tot["rent"] // tot["n"]),
          sol((tot["pf"] + tot["cf"] + tot["nf"] + tot["rent"]) // tot["n"])))

    # ---------- por motivo de saida / conjunto / hora ----------
    p("")
    p("=" * 100)
    p("Q1b - POR MOTIVO DE SAIDA, POR CONJUNTO, POR HORA")
    p("=" * 100)
    for key, label in (("reason", "motivo"), ("set", "conjunto")):
        p("")
        p("%-14s %4s %9s %9s %9s %9s %9s" % (label, "n", "PnL SOL", "media", "MFE med", "MAE med", "300s med"))
        gs = {}
        for P in positions:
            gs.setdefault(P[key], []).append(P)
        for k in sorted(gs, key=lambda k: -sum(x["pnl_sol"] for x in gs[k])):
            G = gs[k]
            p("%-14s %4d %9s %9s %9s %9s %9s" % (
                k, len(G), sum(x["pnl_sol"] for x in G),
                (sum(x["pnl_sol"] for x in G) / len(G)).quantize(Decimal("0.00001")),
                d2(_med([x["mfe"] for x in G])), d2(_med([x["mae"] for x in G])),
                d2(_med([x["mark300"] for x in G]))))
    p("")
    p("%-14s %4s %9s %6s %9s %9s" % ("hora BRT", "n", "PnL SOL", "alvos", "MFE med", "300s med"))
    gs = {}
    for P in positions:
        gs.setdefault(P["hour_brt"], []).append(P)
    for k in sorted(gs):
        G = gs[k]
        p("%-14s %4d %9s %6d %9s %9s" % (
            "%02dh" % k, len(G), sum(x["pnl_sol"] for x in G),
            sum(1 for x in G if x["reason"] == "target"),
            d2(_med([x["mfe"] for x in G])), d2(_med([x["mark300"] for x in G]))))
    for lo, hi, lab in ((0, 11, "00-11h"), (12, 23, "12-23h")):
        G = [P for P in positions if lo <= P["hour_brt"] <= hi]
        p("%-14s %4d %9s %6d %9s %9s" % (
            lab, len(G), sum(x["pnl_sol"] for x in G), sum(1 for x in G if x["reason"] == "target"),
            d2(_med([x["mfe"] for x in G])), d2(_med([x["mark300"] for x in G]))))
    return positions


def _med(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


if __name__ == "__main__":
    main()
    txt = "\n".join(OUT)
    (HERE / "metrics.txt").write_text(txt, encoding="utf-8")
    print(txt)
