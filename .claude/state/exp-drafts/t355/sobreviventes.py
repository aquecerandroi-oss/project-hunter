"""Holm conjunto sobre os dois conjuntos de definições, e a economia do que sobra.

Duas correções que a honestidade exige e que nenhum dos dois braços faz sozinho:

1. **A família é a união.** Rodei 84 rótulos-horizonte com as definições da parte
   (b) e 108 com as da KB-0080 §7 sobre a **mesma** série. Corrigir cada braço
   isolado subestima a busca: quem olhou os dois olhou 144 testes não-raros.
   Aqui o Holm roda sobre a união.
2. **O que sobra tem de passar pelo pedágio.** Um Δ em ATR não é dinheiro. O
   sobrevivente é convertido em R por duas réguas: a invalidação **natural** do
   próprio padrão e um stop **declarado** de 1,0 ATR (a distância que as versões
   do Lab usam), com o `custo_R = 0,0020 / risco%` da KB-0076 ao lado.
"""

from __future__ import annotations

import csv
import sys
from statistics import median

AQUI = "C:/dev/project-hunter/.claude/state/exp-drafts/t355"
for _p in (AQUI, "C:/dev/project-hunter/.claude/state/exp-drafts/t342-blocos"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import padroes_kb0080 as kb  # noqa: E402
from bootstrap_padroes import holm, media_por_blocos  # noqa: E402
from estatistica import (  # noqa: E402
    carregar_marcas,
    carregar_universo,
    residuo_pareado,
    rodar,
)
from padroes import NOMES, SINAL  # noqa: E402

CUSTO_BPS = 0.0020
STOP_DECLARADO = 1.0


def familia(sufixo: str, nomes, sinal) -> dict[str, float]:
    return {c.chave: c.p_valor for c, raro in rodar(sufixo, nomes, sinal) if not raro}


def ocorrencias(sufixo: str) -> dict[tuple[str, str], list[dict[str, str]]]:
    grupos: dict[tuple[str, str], list[dict[str, str]]] = {}
    with open(f"{AQUI}/ocorrencias{sufixo}.csv", newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            grupos.setdefault((linha["nome"], linha["tf"]), []).append(linha)
    return grupos


def main() -> None:
    b = familia("", NOMES, SINAL)
    a = familia("-a", kb.NOMES, kb.SINAL)
    uniao = {f"b/{k}": v for k, v in b.items()} | {f"a/{k}": v for k, v in a.items()}
    ajustado = holm(uniao)
    vivos = [k for k in uniao if ajustado[k][1]]
    print(f"familia da parte (b): {len(b)} | da KB-0080: {len(a)} | uniao: {len(uniao)}")
    print(f"sobrevivem ao Holm conjunto (m={len(uniao)}, alfa 0,05): {vivos or 'nenhum'}")
    for chave in sorted(uniao, key=lambda k: uniao[k])[:6]:
        print(f"  {chave:<30} p={uniao[chave]:.4f}  Holm={ajustado[chave][0]:.4f}")

    print()
    print("economia do que sobra (o horizonte de cada sobrevivente, nao o h=4 da tabela geral)")
    print(
        f"{'rotulo':<26}{'n':>6}{'delta ATR':>11}{'atr%':>8}"
        f"{'stop nat.':>11}{'custo nat.':>11}{'R nat.':>9}"
        f"{'custo 1ATR':>12}{'R 1ATR':>9}{'IC baixo':>10}{'IC alto':>9}"
    )
    for chave in vivos:
        braco, resto = chave.split("/", 1)
        nome, tf, h = resto.split("|")
        k = int(h[1:])
        sufixo, nomes, sinal = ("", NOMES, SINAL) if braco == "b" else ("-a", kb.NOMES, kb.SINAL)
        universos = carregar_universo(sufixo)
        marcas = carregar_marcas(universos, sufixo, nomes)
        u = universos[tf]
        marca = marcas[(nome, tf)]
        res = residuo_pareado(u, u.r[k], marca, sinal[nome])

        linhas = [x for x in ocorrencias(sufixo)[(nome, tf)] if float(x["risco_frac"]) > 0]
        atr_pct = median(float(x["atr_pct"]) for x in linhas)
        stop_nat = median(float(x["stop_atr"]) for x in linhas)
        risco_nat = median(float(x["risco_frac"]) for x in linhas)

        delta = float(res[marca].mean())
        custo_nat = CUSTO_BPS / risco_nat
        custo_1 = CUSTO_BPS / (STOP_DECLARADO * atr_pct)
        liquido_1 = res[marca] / STOP_DECLARADO - custo_1
        _, ic = media_por_blocos(u.dia[marca], liquido_1)
        print(
            f"{chave:<26}{int(marca.sum()):>6}{delta:>11.4f}{atr_pct * 100:>8.3f}"
            f"{stop_nat:>11.2f}{custo_nat:>11.3f}{delta / stop_nat:>9.3f}"
            f"{custo_1:>12.3f}{float(liquido_1.mean()):>9.3f}{ic[0]:>10.3f}{ic[1]:>9.3f}"
        )
        # O sinal sobrevivente tem o **sinal errado**: o padrao afirma queda e o
        # mercado sobe. Operar ao contrario e outra hipotese, com outra
        # invalidacao, e a unica forma honesta de precifica-la aqui e com o
        # mesmo stop declarado de 1 ATR -- a invalidacao natural do inverso
        # (abaixo da minima do marubozu) fica colada na entrada.
        invertido = -res[marca] / STOP_DECLARADO - custo_1
        _, ic_inv = media_por_blocos(u.dia[marca], invertido)
        print(
            f"{'  ^ operado ao contrario':<26}{int(marca.sum()):>6}{-delta:>11.4f}"
            f"{atr_pct * 100:>8.3f}{'-':>11}{'-':>11}{-delta / stop_nat:>9.3f}"
            f"{custo_1:>12.3f}{float(invertido.mean()):>9.3f}{ic_inv[0]:>10.3f}{ic_inv[1]:>9.3f}"
        )


if __name__ == "__main__":
    main()
