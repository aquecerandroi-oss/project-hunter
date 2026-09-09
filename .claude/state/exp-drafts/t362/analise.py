"""T3.62 - leitura das quatro coortes de 16 mercados da familia mean_reversion.

Le o dump `t362-decisoes.csv` (uma linha por desfecho terminal com R conhecido) e
produz: decomposicao por mercado (regra dos 60 %/K6), o contraste
4-mercados-originais vs 12-novos (a vista de replicacao), as metades da janela e
o IC por bootstrap de blocos de dia. NumPy so; nada de pandas. Somente leitura.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict

import numpy as np

CSV = r"C:/dev/project-hunter/.claude/state/exp-drafts/t362-decisoes.csv"
ORIGINAIS = {"ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"}
SEED = 20260909
B = 20000
CORTE_METADE = "2026-08-23"  # a fatia a termina aqui; metade por calendario


def carregar():
    linhas = []
    with open(CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            entry = float(row["p_entry"])
            risk = float(row["risk"])
            exit_base = float(row["exit_base"])
            r_net = float(row["r_net"])
            r_exf = float(row["r_exf"])
            r_bruto = (exit_base - entry / 1.0006) / risk
            linhas.append(
                {
                    "versao": row["versao"],
                    "mercado": row["mercado"],
                    "dia": row["dia"],
                    "hora": int(row["hora_utc"]),
                    "resultado": row["resultado"],
                    "r_net": r_net,
                    "r_bruto": r_bruto,
                    "custo_r": r_bruto - r_exf,
                    "risco_pct": risk / entry,
                    "atr_pct": float(row["atr_pct"]),
                    "novo": row["mercado"] not in ORIGINAIS,
                }
            )
    return linhas


def pf(r):
    r = np.asarray(r, dtype=float)
    ganho = r[r > 0].sum()
    perda = -r[r < 0].sum()
    return float(ganho / perda) if perda > 0 else float("inf")


def resumo(r):
    r = np.asarray(r, dtype=float)
    if r.size == 0:
        return "n=0"
    return "n={:4d}  media={:+.4f}  PF={:.3f}  acerto={:4.1f}%  soma={:+7.2f}".format(
        r.size, r.mean(), pf(r), 100.0 * (r > 0).mean(), r.sum()
    )


def ic_blocos_dia(regs, chave="r_net", b=B, seed=SEED):
    """IC 95 % por bootstrap de blocos: o bloco e o dia inteiro (todas as
    decisoes daquele dia andam juntas), que e como a dependencia intradiaria
    entre mercados aparece."""
    por_dia = defaultdict(list)
    for reg in regs:
        por_dia[reg["dia"]].append(reg[chave])
    dias = sorted(por_dia)
    if not dias:
        return None
    blocos = [np.asarray(por_dia[d], dtype=float) for d in dias]
    somas = np.array([bl.sum() for bl in blocos])
    tam = np.array([bl.size for bl in blocos], dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(blocos), size=(b, len(blocos)))
    med = somas[idx].sum(axis=1) / tam[idx].sum(axis=1)
    lo, hi = np.percentile(med, [2.5, 97.5])
    return len(dias), float(lo), float(hi)


def ic_diferenca(regs, b=B, seed=SEED):
    """IC 95 % da diferenca (novos - originais) reamostrando os MESMOS dias para
    os dois grupos: e um contraste pareado por dia, nao duas amostras soltas."""
    por_dia_novo = defaultdict(list)
    por_dia_orig = defaultdict(list)
    for reg in regs:
        alvo = por_dia_novo if reg["novo"] else por_dia_orig
        alvo[reg["dia"]].append(reg["r_net"])
    dias = sorted(set(por_dia_novo) | set(por_dia_orig))
    sn = np.array([sum(por_dia_novo.get(d, [])) for d in dias])
    cn = np.array([len(por_dia_novo.get(d, [])) for d in dias], dtype=float)
    so = np.array([sum(por_dia_orig.get(d, [])) for d in dias])
    co = np.array([len(por_dia_orig.get(d, [])) for d in dias], dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(dias), size=(b, len(dias)))
    with np.errstate(invalid="ignore", divide="ignore"):
        mn = sn[idx].sum(axis=1) / cn[idx].sum(axis=1)
        mo = so[idx].sum(axis=1) / co[idx].sum(axis=1)
    dif = mn - mo
    dif = dif[np.isfinite(dif)]
    lo, hi = np.percentile(dif, [2.5, 97.5])
    return float(dif.mean()), float(lo), float(hi)


def main():
    linhas = carregar()
    versoes = [
        "mean_reversion v6",
        "mean_reversion v10",
        "mean_reversion v8",
        "mean_reversion v2",
    ]
    por_versao = defaultdict(list)
    for reg in linhas:
        por_versao[reg["versao"]].append(reg)

    for v in versoes:
        regs = por_versao[v]
        r_net = [x["r_net"] for x in regs]
        r_br = [x["r_bruto"] for x in regs]
        print("=" * 100)
        print("### {}   ({} decisoes)".format(v, len(regs)))
        print("  liquido : " + resumo(r_net))
        print("  bruto   : " + resumo(r_br))
        custos = [x["custo_r"] for x in regs]
        print(
            "  pedagio : media={:+.4f} R  p50={:+.4f} R".format(
                float(np.mean(custos)), float(np.median(custos))
            )
        )
        ic = ic_blocos_dia(regs)
        print(
            "  IC95 blocos-dia (liquido): [{:+.4f}; {:+.4f}]  sobre {} dias distintos".format(
                ic[1], ic[2], ic[0]
            )
        )

        # --- decomposicao por mercado / K6
        print("  -- por mercado --")
        por_mkt = defaultdict(list)
        for x in regs:
            por_mkt[x["mercado"]].append(x["r_net"])
        tot = len(regs)
        linhas_mkt = sorted(por_mkt.items(), key=lambda kv: -len(kv[1]))
        for mkt, rs in linhas_mkt:
            rs_a = np.asarray(rs)
            tag = "orig" if mkt in ORIGINAIS else "novo"
            print(
                "     {:<11}{}  n={:3d} ({:4.1f}%)  media={:+.4f}  PF={:6.3f}  soma={:+7.2f}".format(
                    mkt, tag, len(rs), 100.0 * len(rs) / tot, rs_a.mean(), pf(rs_a), rs_a.sum()
                )
            )
        maior = linhas_mkt[0]
        share = 100.0 * len(maior[1]) / tot
        print(
            "     K6: maior mercado = {} com {:.1f}% (dispara em >= 60 %) -> {}".format(
                maior[0], share, "DISPARA" if share >= 60 else "nao dispara"
            )
        )

        # --- leave-one-market-out
        piores = []
        for mkt in por_mkt:
            resto = [x["r_net"] for x in regs if x["mercado"] != mkt]
            piores.append((float(np.mean(resto)), mkt, pf(resto), len(resto)))
        piores.sort()
        print("  -- deixa-um-mercado-de-fora (os 3 piores) --")
        for media, mkt, p, n in piores[:3]:
            print("     sem {:<11} n={:3d}  media={:+.4f}  PF={:.3f}".format(mkt, n, media, p))

        # --- replicacao: 4 originais vs 12 novos
        orig = [x["r_net"] for x in regs if not x["novo"]]
        novo = [x["r_net"] for x in regs if x["novo"]]
        print("  -- replicacao --")
        print("     4 originais (ETH/SOL/XRP/DOGE): " + resumo(orig))
        print("     12 novos                      : " + resumo(novo))
        ico = ic_blocos_dia([x for x in regs if not x["novo"]])
        icn = ic_blocos_dia([x for x in regs if x["novo"]])
        if ico:
            print("     IC95 originais: [{:+.4f}; {:+.4f}] ({} dias)".format(ico[1], ico[2], ico[0]))
        if icn:
            print("     IC95 novos    : [{:+.4f}; {:+.4f}] ({} dias)".format(icn[1], icn[2], icn[0]))
        d, dlo, dhi = ic_diferenca(regs)
        print(
            "     diferenca (novos - originais) = {:+.4f} R  IC95 [{:+.4f}; {:+.4f}]".format(
                d, dlo, dhi
            )
        )

        # --- metades da janela
        m1 = [x for x in regs if x["dia"] < CORTE_METADE]
        m2 = [x for x in regs if x["dia"] >= CORTE_METADE]
        print("  -- metades (corte 2026-08-23) --")
        print("     1a metade: " + resumo([x["r_net"] for x in m1]))
        print("     2a metade: " + resumo([x["r_net"] for x in m2]))

        # --- C5: banda de risco paper_v1 [0,003; 0,03]
        risco = np.array([x["risco_pct"] for x in regs])
        print(
            "  -- C5 banda [0,003; 0,03]: abaixo do piso {}, acima do teto {} ({:.1f}%), "
            "risco%p50={:.5f}".format(
                int((risco < 0.003).sum()),
                int((risco > 0.03).sum()),
                100.0 * (risco > 0.03).mean(),
                float(np.median(risco)),
            )
        )
    print("=" * 100)


if __name__ == "__main__":
    sys.exit(main())
