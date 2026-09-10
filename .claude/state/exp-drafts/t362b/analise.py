"""T3.62b — leitura de 90 dias das coortes `mean_reversion` v10, v1 e v2.

Lê `t362b-decisoes.csv` (uma linha por desfecho terminal, 16 mercados,
2026-06-12 → 2026-09-10) e responde, nesta ordem:

  §1  pooled por versão: n, dias, bruta, ex-funding, PF, pedágio, IC por blocos de dia;
  §2  as TRÊS janelas de 30 d separadas — a pergunta central do brief;
  §3  Δ (J3 − J1J2) não pareado, com IC: agosto explica tudo, ou não?
  §4  decomposição por mercado (K6);
  §5  4 mercados originais vs 12 novos, pareado por dia;
  §6  C5: fatia acima do teto de risco de 3 %, pooled e por janela.

O eixo é `r_exf` (R sem funding), presente em 100 % da população; `r_net` (com
funding) só existe onde há `funding_rates`, isto é, de 2026-08-08 16:00 UTC em
diante — usá-lo reduziria a leitura de 90 d a agosto de novo. O arrasto medido do
funding onde ele é conhecido é −0,0011 R na v10, então os dois eixos coincidem na
prática (q10 §6). Somente leitura; NumPy, sem pandas.
"""

from __future__ import annotations

import csv
from collections import defaultdict

import numpy as np

from blocos90 import delta_nao_pareado, delta_pareado_por_dia, ic_media, profit_factor

CSV = r"C:/dev/project-hunter/.claude/state/exp-drafts/t362b-decisoes.csv"
ORIGINAIS = {"ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"}
SEED = 20260910
B = 20_000
TETO_C5 = 0.03  # `paper_v1`: banda [0,003; 0,03] em packages/risk-core/hunter_risk/limits.py
JANELAS = {"J1": "J1 jun12-jul12", "J2": "J2 jul12-ago11", "J3": "J3 ago11-set10"}


def carregar() -> list[dict]:
    linhas = []
    with open(CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            linhas.append(
                {
                    "versao": row["versao"],
                    "dia": row["dia"],
                    "mercado": row["mercado"],
                    "original": row["mercado"] in ORIGINAIS,
                    "janela": row["janela"],
                    "r_exf": float(row["r_exf"]),
                    "r_net": float(row["r_net"]) if row["r_net"] else None,
                    "r_bruto": float(row["r_bruto"]),
                    "risco_pct": float(row["risco_pct"]),
                }
            )
    return linhas


def _arrays(linhas: list[dict], campo: str = "r_exf"):
    return [x["dia"] for x in linhas], np.array([x[campo] for x in linhas], dtype=float)


def _fmt_ic(ic: tuple[float, float]) -> str:
    return f"[{ic[0]:+.4f}; {ic[1]:+.4f}]"


def main() -> None:
    linhas = carregar()
    por_versao: dict[str, list[dict]] = defaultdict(list)
    for x in linhas:
        por_versao[x["versao"]].append(x)
    versoes = ["v10", "v1", "v2"]

    print("=" * 108)
    print("§1 POOLED, 90 dias (2026-06-12 -> 2026-09-10), 16 mercados, eixo r_ex_funding")
    print("=" * 108)
    print(f"{'versao':<6}{'n':>5}{'dias':>6}{'bruta':>9}{'pedagio50':>11}"
          f"{'ex-funding':>12}{'PF':>8}{'acerto%':>9}  IC95 da ex-funding (blocos de dia)")
    for v in versoes:
        L = por_versao[v]
        dias, r = _arrays(L)
        bruto = np.array([x["r_bruto"] for x in L])
        pedagio = bruto - r
        ic = ic_media(dias, r, reamostragens=B, seed=SEED)
        acerto = 100.0 * (r > 0).sum() / r.size
        print(f"{v:<6}{r.size:>5}{ic.dias:>6}{bruto.mean():>+9.4f}"
              f"{np.percentile(pedagio, 50):>11.4f}{r.mean():>+12.4f}"
              f"{profit_factor(r):>8.3f}{acerto:>9.1f}  {_fmt_ic(ic.ic95)}")

    print()
    print("=" * 108)
    print("§2 AS TRES JANELAS DE 30 DIAS, SEPARADAS")
    print("=" * 108)
    print(f"{'versao':<6}{'janela':<18}{'n':>5}{'dias':>6}{'bruta':>9}{'pedagio50':>11}"
          f"{'ex-funding':>12}{'PF':>8}{'acerto%':>9}  IC95")
    for v in versoes:
        for jk in ("J1", "J2", "J3"):
            L = [x for x in por_versao[v] if x["janela"] == jk]
            if not L:
                continue
            dias, r = _arrays(L)
            bruto = np.array([x["r_bruto"] for x in L])
            ic = ic_media(dias, r, reamostragens=B, seed=SEED)
            acerto = 100.0 * (r > 0).sum() / r.size
            print(f"{v:<6}{JANELAS[jk]:<18}{r.size:>5}{ic.dias:>6}{bruto.mean():>+9.4f}"
                  f"{np.percentile(bruto - r, 50):>11.4f}{r.mean():>+12.4f}"
                  f"{profit_factor(r):>8.3f}{acerto:>9.1f}  {_fmt_ic(ic.ic95)}")
        print()

    print("=" * 108)
    print("§3 AGOSTO EXPLICA TUDO?  D = J3 - (J1+J2), nao pareado (janelas disjuntas)")
    print("=" * 108)
    print(f"{'versao':<6}{'n(J3)':>7}{'n(J1J2)':>9}{'media J3':>11}{'media J1J2':>13}"
          f"{'D':>10}  IC95 do D")
    for v in versoes:
        j3 = [x for x in por_versao[v] if x["janela"] == "J3"]
        j12 = [x for x in por_versao[v] if x["janela"] in ("J1", "J2")]
        d3, r3 = _arrays(j3)
        d12, r12 = _arrays(j12)
        d = delta_nao_pareado(d3, r3, d12, r12, reamostragens=B, seed=SEED)
        print(f"{v:<6}{d.n_a:>7}{d.n_b:>9}{d.media_a:>+11.4f}{d.media_b:>+13.4f}"
              f"{d.delta:>+10.4f}  {_fmt_ic(d.ic95)}")

    print()
    print("=" * 108)
    print("§4 DECOMPOSICAO POR MERCADO (K6 dispara com >= 60 % num mercado)")
    print("=" * 108)
    for v in versoes:
        L = por_versao[v]
        por_mkt: dict[str, list[float]] = defaultdict(list)
        for x in L:
            por_mkt[x["mercado"]].append(x["r_exf"])
        maior = max(len(a) for a in por_mkt.values())
        print(f"-- {v}: {len(L)} decisoes, {len(por_mkt)} mercados, "
              f"maior fatia {100.0*maior/len(L):.1f} %  (K6 {'DISPARA' if maior/len(L) >= 0.6 else 'ok'})")
        for mkt, vals in sorted(por_mkt.items(), key=lambda kv: -np.mean(kv[1])):
            a = np.array(vals)
            flag = "orig" if mkt in ORIGINAIS else "novo"
            print(f"     {mkt:<12}{flag:<6}{a.size:>4}{a.mean():>+10.4f}"
                  f"{a.sum():>+9.2f}{profit_factor(a):>8.3f}")
        print()

    print("=" * 108)
    print("§5 REPLICACAO: 4 originais vs 12 novos, D pareado por dia")
    print("=" * 108)
    print(f"{'versao':<6}{'n orig':>8}{'n novos':>9}{'orig':>10}{'novos':>10}"
          f"{'D(orig-novos)':>15}  IC95           reamostragens validas")
    for v in versoes:
        L = por_versao[v]
        dias = [x["dia"] for x in L]
        r = np.array([x["r_exf"] for x in L])
        g = np.array([x["original"] for x in L])
        d = delta_pareado_por_dia(dias, r, g, reamostragens=B, seed=SEED)
        print(f"{v:<6}{d.n_a:>8}{d.n_b:>9}{d.media_a:>+10.4f}{d.media_b:>+10.4f}"
              f"{d.delta:>+15.4f}  {_fmt_ic(d.ic95)}  {d.reamostragens_validas}")

    print()
    print("=" * 108)
    print(f"§6 C5 -- fatia das decisoes com risco% acima do teto de {TETO_C5:.0%}")
    print("=" * 108)
    print(f"{'versao':<6}{'janela':<18}{'n':>5}{'acima do teto':>15}{'%':>8}{'risco% p50':>13}")
    for v in versoes:
        for rotulo, L in [("(todas)", por_versao[v])] + [
            (JANELAS[jk], [x for x in por_versao[v] if x["janela"] == jk]) for jk in ("J1", "J2", "J3")
        ]:
            if not L:
                continue
            rp = np.array([x["risco_pct"] for x in L])
            acima = int((rp > TETO_C5).sum())
            print(f"{v:<6}{rotulo:<18}{rp.size:>5}{acima:>15}"
                  f"{100.0*acima/rp.size:>8.1f}{np.percentile(rp, 50):>13.5f}")
        print()

    print("=" * 108)
    print("§7 CUSTO DOBRADO sobre os 90 dias (estimativa de primeira ordem)")
    print("=" * 108)
    print("A passada de --stress do motor so consegue reprecificar as decisoes com funding")
    print("conhecido (>= 2026-08-08 16:00 UTC), isto e, so J3. Para ter o custo x2 sobre os")
    print("90 dias inteiros a conta aqui e de primeira ordem: r_exf_x2 = r_exf - pedagio,")
    print("com pedagio = r_bruto - r_exf. Ela SUBESTIMA o estrago, porque assume que o")
    print("caminho ate a saida nao muda quando o custo dobra -- e um custo maior faz mais")
    print("operacao morrer no stop. Serve para a ordem de grandeza, nao para o digito.")
    print()
    print(f"{'versao':<6}{'n':>5}{'ex-funding':>12}{'pedagio med':>13}{'custo x2 (1a ordem)':>21}{'PF x2':>9}")
    for v in versoes:
        L = por_versao[v]
        r = np.array([x["r_exf"] for x in L])
        bruto = np.array([x["r_bruto"] for x in L])
        x2 = 2 * r - bruto
        print(f"{v:<6}{r.size:>5}{r.mean():>+12.4f}{(bruto - r).mean():>13.4f}"
              f"{x2.mean():>+21.4f}{profit_factor(x2):>9.3f}")

    print()
    print("=" * 108)
    print("§8 O FUNIL K1-K6 sobre os 90 dias")
    print("   K3 = >= 100 desfechos E >= 30 dias distintos E expectancy bruta (r_ex_funding) < 0")
    print("        (docs/plans/SHADOW-LAB.md linha 157). E um criterio de MORTE: ele DISPARA")
    print("        quando as tres clausulas valem ao mesmo tempo. Com 31 dias ele nunca chegava")
    print("        a ser mensuravel; com 90 dias, chega.")
    print("=" * 108)
    print(f"{'versao':<6}{'n':>5}{'dias':>6}{'r_ex_funding':>14}{'K1':>5}{'K2':>5}{'K3':>10}"
          f"{'K6 maior%':>11}")
    for v in versoes:
        L = por_versao[v]
        r = np.array([x["r_exf"] for x in L])
        dias = len({x["dia"] for x in L})
        por_mkt: dict[str, int] = defaultdict(int)
        for x in L:
            por_mkt[x["mercado"]] += 1
        maior = 100.0 * max(por_mkt.values()) / len(L)
        k1 = "DISPARA" if r.size < 20 else "ok"
        k2 = "DISPARA" if r.size > 1500 else "ok"
        k3 = "DISPARA" if (r.size >= 100 and dias >= 30 and r.mean() < 0) else "ok"
        k6 = "DISPARA" if maior >= 60 else "ok"
        print(f"{v:<6}{r.size:>5}{dias:>6}{r.mean():>+14.4f}{k1:>5}{k2:>5}{k3:>10}"
              f"{maior:>10.1f} {k6}")


if __name__ == "__main__":  # pragma: no cover - manivela manual
    main()
