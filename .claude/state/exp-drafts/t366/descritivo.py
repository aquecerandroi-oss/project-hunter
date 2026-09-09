"""T3.66 / EXP-0024 — as leituras **descritivas**, fora da família de Holm.

Nada aqui é um dos dois testes pré-registrados. São três fatos que a leitura dos
testes precisa ter ao lado para não ser mal interpretada:

1. **a taxa de reversão de sinal a 15 min no NOSSO dado** — a afirmação central de
   [[KB-0082]] (Kitron & Wengrowicz) é sobre spot; a nota registra como refutação
   "se o nosso dado não mostrar reversão de sinal a 15 m nem no controle". Aqui ela
   é medida sobre os 56 perpétuos da população, em toda a janela;
2. **a expectancy do próprio controle C2** — se o contrarian lag-1 com a nossa
   geometria e os nossos 20 bps já for positivo, "a família é uma forma cara de
   comprar lag-1" ganha força; se for negativo, a frase perde o pressuposto;
3. **o corte por coorte e por sinal da barra** — o pré-registro manda reportar
   `replay` e `prospective` separados antes de qualquer agregado.

Manivela: ``uv run python .claude/state/exp-drafts/t366/descritivo.py``
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from blocos import media_por_blocos  # noqa: E402
from controle import BARRA, sinal  # noqa: E402
from rodar import RAIZ, carregar_velas, linha  # noqa: E402


def reversao_de_sinal() -> None:
    """P(próxima barra de 15 m fecha em alta | esta fechou em baixa), e o espelho.

    Bloco de dia (UTC da barra atual) para o IC, porque 56 perpétuos do mesmo dia
    não são 56 observações independentes ([[KB-0051]]).
    """
    series = carregar_velas()
    obs_apos_baixa: list[tuple[str, float]] = []
    obs_apos_alta: list[tuple[str, float]] = []
    for serie in series.values():
        minutos = serie.minutos()
        if not minutos:
            continue
        inicio, fim = min(minutos), max(minutos)
        t = inicio + BARRA - (inicio - inicio.replace(minute=0, second=0)) % BARRA
        anterior = None
        while t <= fim:
            balde = serie.balde15(t)
            if balde is not None and anterior is not None and anterior.fecha_em + BARRA == t:
                s_ant, s_cur = sinal(anterior), sinal(balde)
                if s_ant != 0 and s_cur != 0:
                    dia = t.strftime("%Y-%m-%d")
                    alvo = obs_apos_baixa if s_ant == -1 else obs_apos_alta
                    alvo.append((dia, 1.0 if s_cur == 1 else 0.0))
            anterior = balde
            t += BARRA

    e_baixa = media_por_blocos(obs_apos_baixa)
    e_alta = media_por_blocos(obs_apos_alta)
    print("=== reversão de sinal a 15 min nos 56 perpétuos da população ===")
    print("  " + linha("P(próxima em alta | esta em baixa)", e_baixa))
    print("  " + linha("P(próxima em alta | esta em alta) ", e_alta))
    print(f"  diferença de pontos: {100 * (e_baixa.ponto - e_alta.ponto):+.2f} p.p.")
    print()


def cortes() -> None:
    with (RAIZ / "pareado.csv").open(newline="", encoding="utf-8") as fh:
        linhas = list(csv.DictReader(fh))

    print("=== expectancy do próprio controle C2 (a mesma regra, barras pareadas) ===")
    for nome, sel in [
        ("AGREGADO", linhas),
        *[(v, [x for x in linhas if x["versao"] == v]) for v in ("v1", "v2", "v6", "v10")],
    ]:
        obs = [(x["dia_br"], float(x["r_c2"])) for x in sel if x["r_c2"] != ""]
        if obs:
            print("  " + linha(f"C2 {nome}", media_por_blocos(obs)))
    print()

    print("=== por coorte (o pré-registro manda separar antes de agregar) ===")
    for c in ("replay", "prospective"):
        sel = [x for x in linhas if x["coorte"] == c]
        if not sel:
            continue
        obs_b = [(x["dia_br"], float(x["r_exf"])) for x in sel]
        obs_c = [(x["dia_br"], float(x["r_exf"]) - float(x["r_c2"])) for x in sel if x["r_c2"] != ""]
        print("  " + linha(f"expectancy {c}", media_por_blocos(obs_b)))
        print("  " + linha(f"Δ2 {c}", media_por_blocos(obs_c)))
    print()

    print("=== a decisão por sinal da barra que a estratégia leu ===")
    por_sinal: dict[str, list[dict[str, str]]] = defaultdict(list)
    for x in linhas:
        rotulo = {"-1": "barra de BAIXA (lag-1 concorda)", "1": "barra de ALTA", "0": "doji"}.get(
            x["sinal"], "sem balde"
        )
        por_sinal[rotulo].append(x)
    for rotulo, sel in sorted(por_sinal.items()):
        obs = [(x["dia_br"], float(x["r_exf"])) for x in sel]
        print("  " + linha(rotulo, media_por_blocos(obs)))


if __name__ == "__main__":
    reversao_de_sinal()
    cortes()
