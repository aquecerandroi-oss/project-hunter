"""Os dois recortes condicionais do brief — T3.55b.

**Horizonte declarado: 4 barras**, o do meio dos três do contraste principal,
fixado antes de qualquer número condicional ser calculado. Rodar os três aqui
seria triplicar a família para comprar significância.

Recorte 1 — **linha**: a barra encosta numa linha de tendência viva? Suporte para
padrão de alta, resistência para padrão de baixa, tolerância `0,25 ATR` (o
`tolerance_atr` do `DEFAULT_PARAMS` da T3.34: a mesma régua que decide se um toque
é toque). Fonte: `linhas-*.csv`, produzido por `linhas.py` com o `tl_scan`
congelado.

Recorte 2 — **regime do BTC na hora anterior**: `market_regimes` como o sistema
gravou (PIPELINE §4b). A hora usada é a última que terminou **estritamente antes**
do fechamento da barra — uma decisão às 11:00 em ponto não pode ler o regime da
hora [10:00, 11:00), que só é calculado depois das 11:00.

Família declarada: 8 testes (2 recortes × 2 fatias × 2 timeframes), com os padrões
**agrupados por direção** (o doji fica de fora do agrupamento: ele não afirma
direção). A tabela por padrão que vem depois é descritiva, sem inferência —
14 × 2 × 2 × 2 testes não teriam poder para nada.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta

import numpy as np

AQUI = "C:/dev/project-hunter/.claude/state/exp-drafts/t355"
for _p in (AQUI, "C:/dev/project-hunter/.claude/state/exp-drafts/t342-blocos"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bootstrap_padroes import contraste_rapido, holm  # noqa: E402
from estatistica import TFS, carregar_marcas, carregar_universo, residuo_pareado  # noqa: E402
from padroes import DIRECAO, NOMES  # noqa: E402

HORIZONTE = 4
TOLERANCIA = 0.25
PASSO = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1)}
LONGS = tuple(n for n in NOMES if DIRECAO[n] == "long")
SHORTS = tuple(n for n in NOMES if DIRECAO[n] == "short")


def carregar_linhas() -> dict[tuple[str, str, str], tuple[float | None, float | None]]:
    saida: dict[tuple[str, str, str], tuple[float | None, float | None]] = {}
    for arquivo in ("linhas-15m-A.csv", "linhas-15m-B.csv", "linhas-1h.csv"):
        with open(f"{AQUI}/{arquivo}", newline="", encoding="utf-8") as fh:
            for linha in csv.DictReader(fh):
                saida[(linha["symbol"], linha["tf"], linha["ts"])] = (
                    float(linha["dist_sup"]) if linha["dist_sup"] else None,
                    float(linha["dist_res"]) if linha["dist_res"] else None,
                )
    return saida


def carregar_regimes() -> list[tuple[datetime, str]]:
    saida: list[tuple[datetime, str]] = []
    with open(f"{AQUI}/regimes.csv", newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(
            linha_bruta for linha_bruta in fh if linha_bruta.count(",") >= 5
        ):
            saida.append((datetime.fromisoformat(linha["start_time"]), linha["regime"]))
    return sorted(saida)


def regime_da_barra(regimes: dict[datetime, str], fechamento: datetime) -> str:
    """A última hora que terminou **estritamente antes** de `fechamento`."""
    inicio = fechamento.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    if inicio + timedelta(hours=1) >= fechamento:
        inicio -= timedelta(hours=1)
    return regimes.get(inicio, "SEM_REGIME")


def main() -> None:
    universos = carregar_universo()
    marcas = carregar_marcas(universos)
    dist = carregar_linhas()
    regimes = dict(carregar_regimes())

    contrastes = []
    descritivo: list[tuple[str, str, str, int, float]] = []
    for tf in TFS:
        u = universos[tf]
        passo = PASSO[tf]
        ts = [None] * u.sym.size
        for (simbolo, carimbo), i in u.chave.items():
            ts[i] = (simbolo, carimbo)
        sup = np.full(u.sym.size, np.nan)
        res = np.full(u.sym.size, np.nan)
        reg = np.array([regime_da_barra(regimes, datetime.fromisoformat(c) + passo) for _, c in ts])
        for i, (simbolo, carimbo) in enumerate(ts):
            achado = dist.get((simbolo, tf, carimbo))
            if achado is None:
                continue
            sup[i] = np.inf if achado[0] is None else achado[0]
            res[i] = np.inf if achado[1] is None else achado[1]

        pool = {
            "long": np.any([marcas[(n, tf)] for n in LONGS], axis=0),
            "short": np.any([marcas[(n, tf)] for n in SHORTS], axis=0),
        }
        residuo = {
            lado: residuo_pareado(u, u.r[HORIZONTE], pool[lado], +1 if lado == "long" else -1)
            for lado in ("long", "short")
        }
        tem_linha = ~np.isnan(sup)
        fatias = {
            "linha:encostado": {
                "long": tem_linha & (sup <= TOLERANCIA),
                "short": tem_linha & (res <= TOLERANCIA),
            },
            "linha:solto": {
                "long": tem_linha & ~(sup <= TOLERANCIA),
                "short": tem_linha & ~(res <= TOLERANCIA),
            },
            "regime:alinhado": {
                "long": reg == "BTC_BULL",
                "short": reg == "BTC_BEAR",
            },
            "regime:contra": {
                "long": reg == "BTC_BEAR",
                "short": reg == "BTC_BULL",
            },
        }
        for rotulo, selecao in fatias.items():
            dias = np.concatenate([u.dia[selecao[lado]] for lado in ("long", "short")])
            valores = np.concatenate([residuo[lado][selecao[lado]] for lado in ("long", "short")])
            marca = np.concatenate([pool[lado][selecao[lado]] for lado in ("long", "short")])
            contrastes.append(contraste_rapido(f"{rotulo}|{tf}", dias, valores, marca))

        for nome in NOMES:
            marca_n = marcas[(nome, tf)]
            lado = DIRECAO[nome]
            sinal = -1 if lado == "short" else 1
            r = residuo_pareado(u, u.r[HORIZONTE], marca_n, sinal)
            perto = sup if lado != "short" else res
            encostado = marca_n & ~np.isnan(perto) & (perto <= TOLERANCIA)
            solto = marca_n & ~np.isnan(perto) & ~(perto <= TOLERANCIA)
            for rotulo, sel in (("encostado", encostado), ("solto", solto)):
                descritivo.append(
                    (
                        nome,
                        tf,
                        rotulo,
                        int(sel.sum()),
                        float(r[sel].mean()) if sel.any() else float("nan"),
                    )
                )

    ajustado = holm({c.chave: c.p_valor for c in contrastes})
    print(f"horizonte {HORIZONTE} barras | tolerancia {TOLERANCIA} ATR | familia {len(contrastes)}")
    print(
        f"{'fatia':<24}{'tf':>5}{'n_pad':>8}{'n_pop':>8}{'bruto':>10}{'delta':>10}"
        f"{'IC baixo':>11}{'IC alto':>10}{'p':>9}{'Holm8':>8}"
    )
    for c in contrastes:
        fatia, tf = c.chave.rsplit("|", 1)
        print(
            f"{fatia:<24}{tf:>5}{c.n_variante:>8}{c.n_pai:>8}{c.exp_variante:>10.4f}"
            f"{c.delta:>10.4f}{c.ic95[0]:>11.4f}{c.ic95[1]:>10.4f}{c.p_valor:>9.4f}"
            f"{ajustado[c.chave][0]:>8.3f}"
        )
    sobrevive = [c.chave for c in contrastes if ajustado[c.chave][1]]
    print(f"sobrevivem a Holm(8): {sobrevive or 'nenhum'}")

    print()
    print("descritivo por padrao (sem inferencia): media do residuo em ATR, h=4")
    print(f"{'padrao':<16}{'tf':>5}{'n encostado':>13}{'media':>9}{'n solto':>9}{'media':>9}")
    juntos: dict[tuple[str, str], dict[str, tuple[int, float]]] = {}
    for nome, tf, rotulo, n, media in descritivo:
        juntos.setdefault((nome, tf), {})[rotulo] = (n, media)
    for (nome, tf), dados in juntos.items():
        e = dados.get("encostado", (0, float("nan")))
        s = dados.get("solto", (0, float("nan")))
        print(f"{nome:<16}{tf:>5}{e[0]:>13}{e[1]:>9.3f}{s[0]:>9}{s[1]:>9.3f}")


if __name__ == "__main__":
    main()
