"""T3.89 / EXP-0027 — os dois bracos de `breadth_v2` contra o pai `v10`.

Le `t389-decisoes.csv` (uma linha por desfecho terminal; pai `v10` cortado em
2026-06-14 -- o inicio da serie `breadth_v2` -- e os dois bracos `v18`/`v19`,
16 mercados, 2026-06-14 -> 2026-09-10) e responde, na ordem da regra de sucesso
congelada em `obsidian/05-EXPERIMENTS/EXP-0027-amplitude.md`:

  S1  populacao e expectativa de cada versao, com IC por blocos de dia;
  S2  condicao 1 -- delta = media(braco) - media(pai), NAO PAREADO (as duas
      populacoes nao compartilham barras), bootstrap de blocos de dia INTEIRO
      NAO PAREADO, `delta_nao_pareado`, 20000 reamostragens, semente 20260912
      (a semente que o pre-registro fixa -- note que difere de 20260910, a
      semente-padrao de blocos90.py usada nas EXPs 0025/0026);
  S3  condicao 2 -- n >= 100 avaliaveis e >= 30 dias distintos;
  S4  condicao 3 -- media por janela de 30 d (positivo em >= 2 de 3);
  S5  condicao 4 -- leave-one-market-out (16 reajustes, nunca negativo);
  S6  condicao 5 -- delta pareado por (mercado, barra) contra o pai: prova de
      que o portao e so um portao (|delta| <= 0,02 R);
  S7  clausula de falsificacao (controle de identidade) -- a mesma leitura
      (condicao 1) repetida cortando as decisoes do PAI por `regime_hourly_v1`
      em vez de `breadth_v2` (blocos permitidos = rotulos que dominam cada
      braco, medido no S8/rotulos); se o corte por regime der delta igual ou
      maior, breadth_v2 nao acrescenta nada;
  S8  rotulo de regime das decisoes de cada braco (para calibrar S7 e checar
      autocorrelacao com o regime horario);
  S9  K1-K6, C5 e pedagio medido nas decisoes (custo_R = 0,0020/(stop_atr*ATR%),
      stop_atr=1.5 -- os parametros de v10/v18/v19).

Eixo `r_exf` (R sem funding), presente em 100% da populacao (K5 do pai
declarado a parte, ver notas). NumPy sobre janelas em memoria; nada de pandas;
nada aqui e `Decimal` (fronteira fica no banco, PIPELINE Sec9). Somente leitura.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "t362b"))

from blocos90 import (  # noqa: E402
    delta_nao_pareado,
    delta_pareado_por_dia,
    ic_media,
    profit_factor,
)

CSV = Path(__file__).resolve().parent.parent / "t389-decisoes.csv"
SEED = 20260912  # semente do pre-registro EXP-0027, NAO a semente-padrao 20260910
B = 20_000
TETO_C5 = 0.03  # paper_v1: banda [0,003; 0,03] sobre risco/entrada
PAI = "mean_reversion v10"
BRACOS = ("mean_reversion v18", "mean_reversion v19")
STOP_ATR = 1.5  # v10/v18/v19, byte a byte

# Janelas de 30 d da janela do replay (2026-06-14 -> 2026-09-10, 88 d):
# J1 06-14/07-14 (30d), J2 07-14/08-13 (30d), J3 08-13/09-10 (28d) -- ja
# gravadas no dump SQL (q11) e reaproveitadas aqui, nao recalculadas.


def carregar() -> list[dict]:
    linhas: list[dict] = []
    with open(CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            linhas.append(
                {
                    "versao": row["versao"],
                    "dia": row["dia"],
                    "mercado": row["mercado"],
                    "janela": row["janela"],
                    "barra": row["barra"],
                    "rotulo": row["rotulo"],
                    "r_exf": float(row["r_exf"]),
                    "r_net": float(row["r_net"]) if row["r_net"] else None,
                    "atr_pct": float(row["atr_pct"]) if row["atr_pct"] else float("nan"),
                    "risco_pct": float(row["risco_pct"]) if row["risco_pct"] else float("nan"),
                }
            )
    return linhas


def por_versao(linhas: list[dict], versao: str) -> list[dict]:
    return [linha for linha in linhas if linha["versao"] == versao]


def vetores(pop: list[dict]) -> tuple[list[str], np.ndarray]:
    return [p["dia"] for p in pop], np.array([p["r_exf"] for p in pop], dtype=float)


def secao1(linhas: list[dict]) -> None:
    print("\n== 1. populacao e expectativa (eixo r_exf, IC por blocos de dia, semente %d) ==" % SEED)
    print(f"{'versao':<22}{'n':>6}{'dias':>6}{'media':>10}{'soma':>9}{'PF':>7}  IC95")
    for versao in (PAI, *BRACOS):
        pop = por_versao(linhas, versao)
        dias, v = vetores(pop)
        it = ic_media(dias, v, reamostragens=B, seed=SEED)
        print(
            f"{versao:<22}{it.n:>6}{it.dias:>6}{it.media:>+10.4f}{v.sum():>+9.2f}"
            f"{profit_factor(v):>7.3f}  [{it.ic95[0]:+.4f}; {it.ic95[1]:+.4f}]"
        )


def secao2(linhas: list[dict]) -> dict[str, object]:
    pai = por_versao(linhas, PAI)
    dias_pai, v_pai = vetores(pai)
    print("\n== 2. condicao 1: delta NAO PAREADO = media(braco) - media(pai), blocos de dia ==")
    print(f"{'braco':<22}{'n_braco':>8}{'media_br':>10}{'media_pai':>11}{'delta':>9}  IC95   veredito")
    resultados: dict[str, object] = {}
    for braco in BRACOS:
        pop = por_versao(linhas, braco)
        dias_b, v_b = vetores(pop)
        d = delta_nao_pareado(dias_b, v_b, dias_pai, v_pai, reamostragens=B, seed=SEED)
        ok = d.delta >= 0.05 and d.ic95[0] > 0
        print(
            f"{braco:<22}{d.n_a:>8}{d.media_a:>+10.4f}{d.media_b:>+11.4f}{d.delta:>+9.4f}"
            f"  [{d.ic95[0]:+.4f}; {d.ic95[1]:+.4f}]  {'PASSA' if ok else 'FALHA'}"
        )
        resultados[braco] = {"delta": d.delta, "ic": d.ic95, "cond1": ok}
    return resultados


def secao3(linhas: list[dict]) -> dict[str, bool]:
    print("\n== 3. condicao 2: n >= 100 avaliaveis e >= 30 dias distintos ==")
    resultados: dict[str, bool] = {}
    for braco in BRACOS:
        pop = por_versao(linhas, braco)
        dias = len({p["dia"] for p in pop})
        ok = len(pop) >= 100 and dias >= 30
        print(f"{braco:<22} n={len(pop):>4}  dias={dias:>3}  {'PASSA' if ok else 'FALHA (descartar por populacao)'}")
        resultados[braco] = ok
    return resultados


def secao4(linhas: list[dict]) -> dict[str, bool]:
    print("\n== 4. condicao 3: media por janela de 30 d (positivo em >= 2 de 3) ==")
    janelas = ("J1", "J2", "J3")
    resultados: dict[str, bool] = {}
    for versao in (PAI, *BRACOS):
        pop = por_versao(linhas, versao)
        celulas, positivas = [], 0
        for j in janelas:
            sub = [p for p in pop if p["janela"] == j]
            if not sub:
                celulas.append(f"{'sem amostra':>22}")
                continue
            v = np.array([p["r_exf"] for p in sub], dtype=float)
            positivas += v.mean() > 0
            celulas.append(f"{v.mean():>+12.4f} (n={len(sub):>3}) ")
        ok = positivas >= 2
        print(f"{versao:<22}" + "".join(celulas) + f"  {positivas}/3 {'PASSA' if ok else 'FALHA'}")
        resultados[versao] = ok
    return resultados


def secao5(linhas: list[dict]) -> dict[str, bool]:
    print("\n== 5. condicao 4: leave-one-market-out (16 reajustes, nunca negativo) ==")
    resultados: dict[str, bool] = {}
    for versao in (PAI, *BRACOS):
        pop = por_versao(linhas, versao)
        mercados = sorted({p["mercado"] for p in pop})
        piores: list[tuple[str, float, int]] = []
        for m in mercados:
            v = np.array([p["r_exf"] for p in pop if p["mercado"] != m], dtype=float)
            piores.append((m, float(v.mean()), int(v.size)))
        piores.sort(key=lambda t: t[1])
        negativos = [t for t in piores if t[1] < 0]
        ok = not negativos
        pior = piores[0]
        print(
            f"{versao:<22} mercados={len(mercados):>2}  pior LOO: sem {pior[0]:<11}"
            f"{pior[1]:>+9.4f} (n={pior[2]})  negativos={len(negativos):>2}  {'PASSA' if ok else 'FALHA'}"
        )
        resultados[versao] = ok
    return resultados


def secao6(linhas: list[dict]) -> dict[str, float]:
    print("\n== 6. condicao 5: delta pareado por (mercado, barra) contra o pai ==")
    pai = {(p["mercado"], p["barra"]): p["r_exf"] for p in por_versao(linhas, PAI)}
    print(f"{'braco':<22}{'n_braco':>8}{'compart':>9}{'so_do_braco':>12}{'delta':>9}  veredito")
    resultados: dict[str, float] = {}
    for braco in BRACOS:
        pop = por_versao(linhas, braco)
        pares = [(p["r_exf"], pai[(p["mercado"], p["barra"])]) for p in pop if (p["mercado"], p["barra"]) in pai]
        so_braco = len(pop) - len(pares)
        if not pares:
            print(f"{braco:<22}{len(pop):>8}{0:>9}{so_braco:>12}{'-':>9}  SEM PAR")
            resultados[braco] = float("nan")
            continue
        d = np.array([a - b for a, b in pares], dtype=float)
        ok = abs(d.mean()) <= 0.02
        print(f"{braco:<22}{len(pop):>8}{len(pares):>9}{so_braco:>12}{d.mean():>+9.4f}  {'PASSA' if ok else 'FALHA'}")
        resultados[braco] = float(d.mean())
    return resultados


# rotulos que dominam cada braco (medido em S8 / t389-decisoes.csv; ver notas)
ROTULOS_DOMINANTES = {
    "mean_reversion v18": None,  # preenchido em tempo de execucao pela secao8
    "mean_reversion v19": None,
}


def secao7(linhas: list[dict], rotulos_por_braco: dict[str, set[str]], deltas_breadth: dict[str, object]) -> None:
    print("\n== 7. clausula de falsificacao: cortar o PAI por regime_hourly_v1 em vez de breadth_v2 ==")
    print(
        "mesmo metodo do T3.76 S2b (particao DENTRO do pai, permitido-proibido, pareado por dia) "
        "contra o delta NAO PAREADO braco-vs-pai da condicao 1 (S2) -- os rotulos permitidos sao "
        "os que dominam (>=50% das decisoes) o braco correspondente (S8)."
    )
    pai = por_versao(linhas, PAI)
    print(f"{'braco':<22}{'rotulos_permitidos':<38}{'n_perm':>7}{'media_perm':>11}{'delta_regime':>13}{'delta_breadth':>14}  veredito")
    for braco, rotulos in rotulos_por_braco.items():
        dias_pai = [p["dia"] for p in pai]
        v_pai = np.array([p["r_exf"] for p in pai], dtype=float)
        mascara = np.array([p["rotulo"] in rotulos for p in pai], dtype=bool)
        if not mascara.any() or mascara.all():
            print(f"{braco:<22} (um lado vazio, sem leitura)")
            continue
        d = delta_pareado_por_dia(dias_pai, v_pai, mascara, reamostragens=B, seed=SEED)
        delta_breadth = deltas_breadth[braco]["delta"]
        falsificado = d.delta >= delta_breadth
        print(
            f"{braco:<22}{','.join(sorted(rotulos)):<38}{d.n_a:>7}{d.media_a:>+11.4f}"
            f"{d.delta:>+13.4f}{delta_breadth:>+14.4f}  "
            f"{'FALSIFICADO (regime >= breadth)' if falsificado else 'breadth > regime, clausula nao dispara'}"
        )


def secao8(linhas: list[dict]) -> dict[str, set[str]]:
    print("\n== 8. rotulo de regime das decisoes de cada braco ==")
    dominantes: dict[str, set[str]] = {}
    for versao in (PAI, *BRACOS):
        pop = por_versao(linhas, versao)
        contagem: dict[str, int] = {}
        for p in pop:
            contagem[p["rotulo"]] = contagem.get(p["rotulo"], 0) + 1
        ordenado = sorted(contagem.items(), key=lambda t: -t[1])
        print(f"{versao:<22} " + ", ".join(f"{k}={v}" for k, v in ordenado))
        if versao in BRACOS:
            total = sum(contagem.values())
            acumulado, escolhidos = 0, set()
            for k, v in ordenado:
                escolhidos.add(k)
                acumulado += v
                if acumulado >= 0.5 * total:
                    break
            dominantes[versao] = escolhidos
    return dominantes


def secao9(linhas: list[dict]) -> None:
    print("\n== 9. K1-K6, C5 e pedagio medido nas decisoes ==")
    print(f"{'versao':<22}{'n':>6}{'dias':>6}{'k1':>5}{'k2':>5}{'k3':>5}{'k6_pct':>8}{'c5_pct':>8}{'pedagio_p50':>12}")
    for versao in (PAI, *BRACOS):
        pop = por_versao(linhas, versao)
        n = len(pop)
        dias = len({p["dia"] for p in pop})
        v = np.array([p["r_exf"] for p in pop], dtype=float)
        k1 = n < 20
        k2 = n > 1500
        k3 = n >= 100 and dias >= 30 and float(v.mean()) < 0
        por_mercado: dict[str, int] = {}
        for p in pop:
            por_mercado[p["mercado"]] = por_mercado.get(p["mercado"], 0) + 1
        maior_mercado_pct = 100.0 * max(por_mercado.values()) / n if n else float("nan")
        k6 = maior_mercado_pct >= 60.0
        risco = np.array([p["risco_pct"] for p in pop], dtype=float)
        c5 = 100.0 * float(np.nansum(risco > TETO_C5)) / n if n else float("nan")
        atr = np.array([p["atr_pct"] for p in pop], dtype=float)
        atr = atr[~np.isnan(atr)]
        pedagio_p50 = 0.0020 / (STOP_ATR * float(np.percentile(atr, 50))) if atr.size else float("nan")
        flags = []
        if k1:
            flags.append("K1")
        if k2:
            flags.append("K2")
        if k3:
            flags.append("K3")
        if k6:
            flags.append(f"K6({maior_mercado_pct:.1f}%)")
        print(
            f"{versao:<22}{n:>6}{dias:>6}{'S' if k1 else '.':>5}{'S' if k2 else '.':>5}"
            f"{'S' if k3 else '.':>5}{maior_mercado_pct:>7.1f}%{c5:>7.1f}%{pedagio_p50:>+12.4f}"
            f"  flags={','.join(flags) if flags else 'nenhuma'}"
        )


def main() -> None:
    linhas = carregar()
    print(f"linhas: {len(linhas)}  arquivo: {CSV}")
    secao1(linhas)
    deltas_breadth = secao2(linhas)
    secao3(linhas)
    secao4(linhas)
    secao5(linhas)
    secao6(linhas)
    dominantes = secao8(linhas)
    secao7(linhas, dominantes, deltas_breadth)
    secao9(linhas)


if __name__ == "__main__":
    main()
