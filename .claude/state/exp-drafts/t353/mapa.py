"""T3.53 - roda o mapa sobre `populacao.csv` e imprime as tabelas da nota.

Uso:  uv run python .claude/state/exp-drafts/t353/mapa.py \
          .claude/state/exp-drafts/t353/populacao.csv

Sai em stdout (para colar na nota) e grava `celulas.csv` com TODAS as celulas,
julgaveis ou nao - inclusive as que nao sobreviveram a Holm, porque esconder as
que falharam e como nao ter corrigido por multiplicidade.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import celulas as C  # noqa: E402

N_MIN_POP = 100


def fmt(x: float, casas: int = 4) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x))):
        return "-"
    if isinstance(x, float) and np.isinf(x):
        return "inf"
    return f"{x:+.{casas}f}" if casas and x < 0 else f"{x:.{casas}f}"


def _eixos(grupo: list[dict], campo: str) -> tuple[np.ndarray, int, np.ndarray]:
    dias_rotulo = sorted({l["dia_br"] for l in grupo})
    idx = {d: i for i, d in enumerate(dias_rotulo)}
    return (
        np.array([idx[l["dia_br"]] for l in grupo], dtype=int),
        len(dias_rotulo),
        np.array([float(l[campo]) for l in grupo]),
    )


def _mascara(grupo: list[dict], c: C.Celula) -> np.ndarray:
    """Recupera a mascara da celula pelo rotulo (mesma construcao de `analisar`)."""
    cand = [(d, r, m) for d, r, m in C.dimensoes(grupo) if m.any()]
    grandes = [(d, r, m) for d, r, m in cand if int(m.sum()) >= C.N_MIN]
    grandes, _ = C.deduplicar(grandes)
    for dim, rotulo, m in grandes:
        if (dim, rotulo) == (c.dimensao, c.rotulo):
            return m
    raise KeyError(f"celula nao encontrada: {c.dimensao}/{c.rotulo}")


def resumo_pop(linhas: list[dict]) -> dict:
    r = np.array([float(l["r_net"]) for l in linhas])
    bruto = np.array([float(l["r_gross"]) for l in linhas])
    custo = np.array([float(l["custo_id"]) for l in linhas])
    alvo = np.array([l["motivo"] == "target" for l in linhas])
    return {
        "n": len(linhas),
        "dias": len({l["dia_br"] for l in linhas}),
        "mercados": len({l["symbol"] for l in linhas}),
        "exp": C.media(r),
        "bruta": C.media(bruto),
        "custo": C.media(custo),
        "soma": float(r.sum()),
        "pf": C.pf(r),
        "acerto": 100.0 * float(alvo.mean()),
    }


def main(caminho: str) -> None:
    linhas = C.carregar(caminho)
    print(f"linhas lidas: {len(linhas)}")

    pops: dict[tuple[str, str], list[dict]] = defaultdict(list)
    fams: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for l in linhas:
        pops[(l["versao"], l["coorte"])].append(l)
        fams[(l["familia"] + " (familia)", l["coorte"])].append(l)

    alvos = [(k, v) for k, v in pops.items() if len(v) >= N_MIN_POP]
    alvos += [(k, v) for k, v in fams.items() if len(v) >= N_MIN_POP]
    alvos.sort(key=lambda kv: -len(kv[1]))

    print()
    print("== A. populacoes analisadas (n >= 100) ==")
    print(f"{'versao':<28}{'coorte':<13}{'n':>6}{'dias':>6}{'merc':>6}"
          f"{'exp_liq':>10}{'exp_bruta':>11}{'pedagio':>9}{'somaR':>10}{'PF':>7}{'acerto%':>9}")
    for (versao, coorte), grupo in alvos:
        s = resumo_pop(grupo)
        print(f"{versao:<28}{coorte:<13}{s['n']:>6}{s['dias']:>6}{s['mercados']:>6}"
              f"{s['exp']:>+10.4f}{s['bruta']:>+11.4f}{s['custo']:>9.4f}"
              f"{s['soma']:>+10.2f}{s['pf']:>7.3f}{s['acerto']:>9.1f}")

    todas: list[tuple[C.Celula, bool]] = []
    sobreviventes: list[tuple[C.Celula, list[dict], np.ndarray]] = []
    print()
    for (versao, coorte), grupo in alvos:
        fusoes: list[str] = []
        cels = C.analisar(grupo, versao, coorte, fusoes=fusoes)
        julgaveis = [c for c in cels if c.julgavel]
        ps = [c.p for c in julgaveis]
        selos = C.holm(ps) if ps else []
        selo_por_id = {id(c): s for c, s in zip(julgaveis, selos)}
        for c in cels:
            todas.append((c, selo_por_id.get(id(c), False)))

        n_sobrev = sum(selos)
        print(f"== B. {versao} / {coorte} - {len(cels)} celulas, "
              f"{len(julgaveis)} julgaveis (n>={C.N_MIN} e >={C.DIAS_MIN} dias), "
              f"{n_sobrev} sobrevivem a Holm 5% ==")
        if not julgaveis:
            print("   nenhuma celula julgavel nesta populacao "
                  f"(a populacao tem {len({l['dia_br'] for l in grupo})} dias distintos)")
            print()
            continue
        print(f"   {'dim':<12}{'celula':<26}{'n':>5}{'dias':>5}{'exp':>9}{'resto':>9}"
              f"{'delta':>9}{'IC95':>21}{'p':>8}{'Holm':>6}{'PF':>7}{'acerto':>7}{'pedag':>7}")
        for c in sorted(julgaveis, key=lambda c: -c.delta):
            selo = "sim" if selo_por_id[id(c)] else "-"
            ic = f"[{c.ic95[0]:+.3f}; {c.ic95[1]:+.3f}]"
            print(f"   {c.dimensao:<12}{c.rotulo:<26}{c.n:>5}{c.dias:>5}{c.exp:>+9.4f}"
                  f"{c.exp_resto:>+9.4f}{c.delta:>+9.4f}{ic:>21}{c.p:>8.4f}{selo:>6}"
                  f"{c.pf:>7.3f}{c.acerto:>7.1f}{c.custo:>7.3f}")
        nao = [c for c in cels if not c.julgavel]
        if nao:
            piores = sorted(nao, key=lambda c: -c.n)[:4]
            desc = ", ".join(f"{c.rotulo} (n={c.n}, {c.dias}d)" for c in piores)
            print(f"   nao julgaveis: {len(nao)} celulas - maiores: {desc}")
        if fusoes:
            print(f"   celulas fundidas (mesma hipotese, 1 teste so): {'; '.join(fusoes)}")
        for c in julgaveis:
            if selo_por_id[id(c)]:
                sobreviventes.append((c, grupo, _mascara(grupo, c)))
        print()

    saida = Path(caminho).with_name("celulas.csv")
    with open(saida, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["versao", "coorte", "dimensao", "celula", "n", "dias", "exp_liq",
                    "exp_resto", "delta", "ic_lo", "ic_hi", "p", "holm", "julgavel",
                    "pf", "acerto_pct", "pedagio_medio", "exp_bruta", "soma_r",
                    "n_resto", "dias_resto"])
        for c, selo in todas:
            w.writerow([c.versao, c.coorte, c.dimensao, c.rotulo, c.n, c.dias,
                        f"{c.exp:.6f}", f"{c.exp_resto:.6f}", f"{c.delta:.6f}",
                        f"{c.ic95[0]:.6f}", f"{c.ic95[1]:.6f}", f"{c.p:.6f}",
                        int(selo), int(c.julgavel), f"{c.pf:.6f}", f"{c.acerto:.2f}",
                        f"{c.custo:.6f}", f"{c.exp_bruta:.6f}", f"{c.soma_r:.4f}",
                        c.n_resto, c.dias_resto])
    print(f"celulas.csv: {len(todas)} linhas em {saida}")

    print()
    print("== C. placar de multiplicidade ==")
    por_pop: dict[tuple[str, str], list[tuple[C.Celula, bool]]] = defaultdict(list)
    for c, selo in todas:
        por_pop[(c.versao, c.coorte)].append((c, selo))
    print(f"{'versao':<28}{'coorte':<13}{'celulas':>9}{'julgaveis':>11}{'sobrevivem':>12}")
    tot_j = tot_s = 0
    for (versao, coorte), itens in sorted(por_pop.items(), key=lambda kv: kv[0]):
        j = sum(1 for c, _ in itens if c.julgavel)
        s = sum(1 for _, selo in itens if selo)
        tot_j += j
        tot_s += s
        print(f"{versao:<28}{coorte:<13}{len(itens):>9}{j:>11}{s:>12}")
    print(f"{'TOTAL':<41}{len(todas):>9}{tot_j:>11}{tot_s:>12}")

    print()
    print("== D. as celulas que sobreviveram, sob suspeita (confundidores obvios) ==")
    if not sobreviventes:
        print("   nenhuma")
    for c, grupo, m in sobreviventes:
        dias = sorted({l["dia_br"] for i, l in enumerate(grupo) if m[i]})
        dias_fora = sorted({l["dia_br"] for i, l in enumerate(grupo) if not m[i]})
        custo_in = np.array([float(l["custo_id"]) for i, l in enumerate(grupo) if m[i]])
        custo_out = np.array([float(l["custo_id"]) for i, l in enumerate(grupo) if not m[i]])
        bruto_in = np.array([float(l["r_gross"]) for i, l in enumerate(grupo) if m[i]])
        bruto_out = np.array([float(l["r_gross"]) for i, l in enumerate(grupo) if not m[i]])
        # o mesmo bootstrap, agora sobre o R BRUTO: se o efeito some quando o
        # pedagio sai, a celula nao achou mercado, achou o custo do proprio stop.
        dias_idx, n_dias, r_bruto = _eixos(grupo, "r_gross")
        db, icb, pb, _ = C.bootstrap_celula(dias_idx, n_dias, r_bruto, m)
        print(f"   {c.versao} / {c.coorte} :: {c.dimensao} = {c.rotulo}")
        print(f"      delta liquido {c.delta:+.4f} R  IC95 [{c.ic95[0]:+.3f}; {c.ic95[1]:+.3f}] p={c.p:.4f}")
        print(f"      delta BRUTO   {db:+.4f} R  IC95 [{icb[0]:+.3f}; {icb[1]:+.3f}] p={pb:.4f}")
        print(f"      delta pedagio {C.media(custo_in) - C.media(custo_out):+.4f} R "
              f"(dentro {C.media(custo_in):.3f} / fora {C.media(custo_out):.3f})")
        print(f"      calendario dentro: {dias[0]} .. {dias[-1]} ({len(dias)} dias)")
        print(f"      calendario fora  : {dias_fora[0]} .. {dias_fora[-1]} ({len(dias_fora)} dias)")
        print(f"      sobreposicao de dias: {len(set(dias) & set(dias_fora))} dias em comum")

    print()
    print("== E. coerencia dos dois rotulos de regime entre versoes (NAO sao replicacoes "
          "independentes: v2/v6/v7/v8 decidem as MESMAS barras com geometria diferente) ==")
    print(f"   {'versao':<26}{'coorte':<12}{'rotulo':<14}{'n':>5}{'dias':>5}"
          f"{'exp':>9}{'delta_liq':>11}{'p_liq':>8}{'delta_bruto':>13}{'p_bruto':>9}")
    for rotulo, chave in (("flat/normal", "trend_x_vol"), ("up/high", "trend_x_vol")):
        for (versao, coorte), grupo in alvos:
            dentro = np.array(
                [f"{l['trend']}/{l['vol']}" == rotulo for l in grupo], dtype=bool
            )
            if not dentro.any() or dentro.all():
                continue
            d_idx, n_dias, r_liq = _eixos(grupo, "r_net")
            _, _, r_bru = _eixos(grupo, "r_gross")
            dl, _, pl, _ = C.bootstrap_celula(d_idx, n_dias, r_liq, dentro)
            db, _, pb, _ = C.bootstrap_celula(d_idx, n_dias, r_bru, dentro)
            n_dias_cel = len({l["dia_br"] for i, l in enumerate(grupo) if dentro[i]})
            print(f"   {versao:<26}{coorte:<12}{rotulo:<14}{int(dentro.sum()):>5}"
                  f"{n_dias_cel:>5}{C.media(r_liq[dentro]):>+9.4f}{dl:>+11.4f}{pl:>8.4f}"
                  f"{db:>+13.4f}{pb:>9.4f}")


if __name__ == "__main__":
    main(sys.argv[1])
