"""T3.76 / EXP-0026 — os três braços com portão de regime contra o pai `v10`.

Lê `t376-decisoes.csv` (uma linha por desfecho terminal; 16 mercados,
2026-06-12 → 2026-09-10) e responde, na ordem da regra de sucesso congelada em
`obsidian/05-EXPERIMENTS/EXP-0026-regime-como-estrategia.md`:

  §1  população e expectativa de cada braço e do pai, com IC por blocos de dia;
  §2  **condição 1** — Δ = média(braço) − média(pai na janela inteira), IC 95 %
      por blocos de dia com **os mesmos dias dos dois lados**
      (`delta_pareado_por_dia` sobre a concatenação, máscara = "é o braço").
      Ressalva declarada: as decisões do braço aparecem *também* na população do
      pai (o braço é quase um subconjunto dele), o que correlaciona os dois lados
      positivamente e **estreita** o IC — o viés é a favor de aprovar, não
      contra, e é por isso que o §2b existe;
  §2b Δ de **partição dentro do pai**: média(pai nas horas permitidas) −
      média(pai nas horas proibidas), pareado por dia. Sem sobreposição nenhuma
      entre os dois lados. É a evidência de apoio, não o critério;
  §3  **condição 3** — média por janela de 30 d (positivo em ≥ 2 de 3);
  §4  **condição 4** — leave-one-market-out (16 reajustes, nunca negativo);
  §5  **condição 5** — Δ pareado por (mercado, barra) sobre as barras
      compartilhadas com o pai: prova de que o portão é só um portão
      (|Δ| ≤ 0,02 R). Um Δ grande aqui seria divergência de slot ou bug;
  §6  C5 (fatia com risco/entrada acima do teto de 3 % do `paper_v1`) e o corte
      4 mercados originais × 12 novos (regra de replicação da T3.62);
  §7  `momentum v11` — descritivo. **Sem veredito**: o controle pré-declarado
      (`momentum v8`) está `deprecated` e o replay recusa versão não-executável
      (`is not one runnable version`), então o Δ de 90 d não existe.

Eixo `r_exf` (R sem funding), presente em 100 % da população. NumPy sobre
janelas em memória; nada de pandas; nada aqui é dinheiro persistido, então nada
aqui é `Decimal`. Somente leitura.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "t362b"))

from blocos90 import delta_pareado_por_dia, ic_media, profit_factor  # noqa: E402

CSV = Path(__file__).resolve().parent.parent / "t376-decisoes.csv"
ORIGINAIS = {"ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"}
SEED = 20260910
B = 20_000
TETO_C5 = 0.03
PAI = "mean_reversion v10"
BRACOS = {
    "mean_reversion v15": ("SIDEWAYS", "LOW_VOLATILITY"),
    "mean_reversion v16": ("SIDEWAYS",),
    "mean_reversion v17": ("HIGH_VOLATILITY",),
}
JANELAS = ("J1", "J2", "J3")


def carregar() -> list[dict]:
    linhas: list[dict] = []
    with open(CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            linhas.append(
                {
                    "versao": row["versao"],
                    "dia": row["dia"],
                    "mercado": row["mercado"],
                    "original": row["mercado"] in ORIGINAIS,
                    "janela": row["janela"],
                    "barra": row["barra"],
                    "rotulo": row["rotulo"],
                    "r_exf": float(row["r_exf"]),
                    "risco_pct": float(row["risco_pct"]) if row["risco_pct"] else float("nan"),
                }
            )
    return linhas


def por_versao(linhas: list[dict], versao: str) -> list[dict]:
    return [linha for linha in linhas if linha["versao"] == versao]


def vetores(pop: list[dict]) -> tuple[list[str], np.ndarray]:
    return [p["dia"] for p in pop], np.array([p["r_exf"] for p in pop], dtype=float)


def secao1(linhas: list[dict]) -> None:
    print("\n== 1. populacao e expectativa (eixo r_exf, IC por blocos de dia) ==")
    print(f"{'versao':<22}{'n':>6}{'dias':>6}{'media':>10}{'soma':>9}{'PF':>7}  IC95")
    for versao in (PAI, *BRACOS, "momentum v11"):
        pop = por_versao(linhas, versao)
        if not pop:
            continue
        dias, v = vetores(pop)
        it = ic_media(dias, v, reamostragens=B, seed=SEED)
        print(
            f"{versao:<22}{it.n:>6}{it.dias:>6}{it.media:>+10.4f}{v.sum():>+9.2f}"
            f"{profit_factor(v):>7.3f}  [{it.ic95[0]:+.4f}; {it.ic95[1]:+.4f}]"
        )


def secao2(linhas: list[dict]) -> None:
    pai = por_versao(linhas, PAI)
    dias_pai, v_pai = vetores(pai)
    print("\n== 2. condicao 1: delta = braco - pai (janela inteira), mesmos dias ==")
    print(f"{'braco':<22}{'n_braco':>8}{'media_br':>10}{'media_pai':>11}{'delta':>9}  IC95   veredito")
    for braco in BRACOS:
        pop = por_versao(linhas, braco)
        dias_b, v_b = vetores(pop)
        dias = dias_b + dias_pai
        valores = np.concatenate([v_b, v_pai])
        mascara = np.concatenate([np.ones(v_b.size, bool), np.zeros(v_pai.size, bool)])
        d = delta_pareado_por_dia(dias, valores, mascara, reamostragens=B, seed=SEED)
        ok = "PASSA" if d.delta >= 0.05 and d.ic95[0] > 0 else "FALHA"
        print(
            f"{braco:<22}{d.n_a:>8}{d.media_a:>+10.4f}{d.media_b:>+11.4f}{d.delta:>+9.4f}"
            f"  [{d.ic95[0]:+.4f}; {d.ic95[1]:+.4f}]  {ok}"
        )

    print("\n== 2b. apoio: particao DENTRO do pai (permitido - proibido), pareado por dia ==")
    print(f"{'conjunto':<22}{'n_perm':>8}{'n_proib':>8}{'media_p':>10}{'media_x':>10}{'delta':>9}  IC95")
    for braco, allow in BRACOS.items():
        dias = [p["dia"] for p in pai]
        valores = np.array([p["r_exf"] for p in pai], dtype=float)
        mascara = np.array([p["rotulo"] in allow for p in pai], dtype=bool)
        d = delta_pareado_por_dia(dias, valores, mascara, reamostragens=B, seed=SEED)
        print(
            f"{braco:<22}{d.n_a:>8}{d.n_b:>8}{d.media_a:>+10.4f}{d.media_b:>+10.4f}"
            f"{d.delta:>+9.4f}  [{d.ic95[0]:+.4f}; {d.ic95[1]:+.4f}]"
        )


def secao3(linhas: list[dict]) -> None:
    print("\n== 3. condicao 3: media por janela de 30 d (positivo em >= 2 de 3) ==")
    print(f"{'versao':<22}" + "".join(f"{j:>22}" for j in JANELAS) + "  veredito")
    for versao in (PAI, *BRACOS, "momentum v11"):
        pop = por_versao(linhas, versao)
        if not pop:
            continue
        celulas, positivas = [], 0
        for j in JANELAS:
            sub = [p for p in pop if p["janela"] == j]
            if not sub:
                celulas.append(f"{'sem amostra':>22}")
                continue
            v = np.array([p["r_exf"] for p in sub], dtype=float)
            positivas += v.mean() > 0
            celulas.append(f"{v.mean():>+12.4f} (n={len(sub):>3}) ")
        ok = "PASSA" if positivas >= 2 else "FALHA"
        print(f"{versao:<22}" + "".join(celulas) + f"  {positivas}/3 {ok}")


def secao4(linhas: list[dict]) -> None:
    print("\n== 4. condicao 4: leave-one-market-out (16 reajustes, nunca negativo) ==")
    for versao in (PAI, *BRACOS, "momentum v11"):
        pop = por_versao(linhas, versao)
        if not pop:
            continue
        mercados = sorted({p["mercado"] for p in pop})
        piores: list[tuple[str, float, int]] = []
        for m in mercados:
            v = np.array([p["r_exf"] for p in pop if p["mercado"] != m], dtype=float)
            piores.append((m, float(v.mean()), int(v.size)))
        piores.sort(key=lambda t: t[1])
        negativos = [t for t in piores if t[1] < 0]
        ok = "PASSA" if not negativos else "FALHA"
        pior = piores[0]
        print(
            f"{versao:<22} mercados={len(mercados):>2}  pior LOO: sem {pior[0]:<11}"
            f"{pior[1]:>+9.4f} (n={pior[2]})  negativos={len(negativos):>2}  {ok}"
        )


def secao5(linhas: list[dict]) -> None:
    print("\n== 5. condicao 5: delta pareado por (mercado, barra) contra o pai ==")
    pai = {(p["mercado"], p["barra"]): p["r_exf"] for p in por_versao(linhas, PAI)}
    print(f"{'braco':<22}{'n_braco':>8}{'compart':>9}{'so_do_braco':>12}{'delta':>9}  veredito")
    for braco in BRACOS:
        pop = por_versao(linhas, braco)
        pares = [(p["r_exf"], pai[(p["mercado"], p["barra"])]) for p in pop
                 if (p["mercado"], p["barra"]) in pai]
        so_braco = len(pop) - len(pares)
        if not pares:
            print(f"{braco:<22}{len(pop):>8}{0:>9}{so_braco:>12}{'-':>9}  SEM PAR")
            continue
        d = np.array([a - b for a, b in pares], dtype=float)
        ok = "PASSA" if abs(d.mean()) <= 0.02 else "FALHA"
        print(
            f"{braco:<22}{len(pop):>8}{len(pares):>9}{so_braco:>12}{d.mean():>+9.4f}  {ok}"
        )


def secao6(linhas: list[dict]) -> None:
    print("\n== 6. C5 (risco/entrada > 3 %) e 4 originais x 12 novos ==")
    print(f"{'versao':<22}{'C5 %':>8}{'orig n':>8}{'orig media':>12}{'novos n':>9}{'novos media':>13}{'delta':>9}  IC95")
    for versao in (PAI, *BRACOS, "momentum v11"):
        pop = por_versao(linhas, versao)
        if not pop:
            continue
        risco = np.array([p["risco_pct"] for p in pop], dtype=float)
        c5 = 100.0 * float(np.nansum(risco > TETO_C5)) / len(pop)
        dias = [p["dia"] for p in pop]
        valores = np.array([p["r_exf"] for p in pop], dtype=float)
        mascara = np.array([p["original"] for p in pop], dtype=bool)
        if mascara.all() or not mascara.any():
            print(f"{versao:<22}{c5:>7.1f}%  (um lado vazio)")
            continue
        d = delta_pareado_por_dia(dias, valores, mascara, reamostragens=B, seed=SEED)
        print(
            f"{versao:<22}{c5:>7.1f}%{d.n_a:>8}{d.media_a:>+12.4f}{d.n_b:>9}{d.media_b:>+13.4f}"
            f"{d.delta:>+9.4f}  [{d.ic95[0]:+.4f}; {d.ic95[1]:+.4f}]"
        )


def secao7(linhas: list[dict]) -> None:
    print("\n== 7. rotulo das decisoes de cada braco (prova de que o portao pegou) ==")
    for versao in (PAI, *BRACOS, "momentum v11"):
        pop = por_versao(linhas, versao)
        if not pop:
            continue
        contagem: dict[str, int] = {}
        for p in pop:
            contagem[p["rotulo"]] = contagem.get(p["rotulo"], 0) + 1
        ordenado = ", ".join(f"{k}={v}" for k, v in sorted(contagem.items(), key=lambda t: -t[1]))
        print(f"{versao:<22} {ordenado}")


def main() -> None:
    linhas = carregar()
    print(f"linhas: {len(linhas)}  arquivo: {CSV}")
    secao1(linhas)
    secao2(linhas)
    secao3(linhas)
    secao4(linhas)
    secao5(linhas)
    secao6(linhas)
    secao7(linhas)


if __name__ == "__main__":
    main()
