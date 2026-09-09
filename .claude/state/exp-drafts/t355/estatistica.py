"""O contraste principal: cada padrão contra a baseline pareada — T3.55b.

Família declarada **antes** de olhar: 14 padrões × 2 timeframes × 3 horizontes
(1, 4 e 16 barras) = 84 testes. Dela saem os rótulos **raros** (`MIN_OCORRENCIAS`
/ `MIN_DIAS` abaixo), que continuam na tabela com o `n` e sem IC publicável;
`tres_corvos` em 1 h não ocorre nenhuma vez e entra como `n = 0`, não some. Holm
sobre a família que sobra, e também sobre cada horizonte isolado, para quem
quiser a leitura menos severa.

Métrica: retorno futuro em ATRs do fechamento da decisão, na direção que o padrão
afirma (`+1` long, `-1` short, `+1` para o doji com a ressalva de que ele não
afirma direção). Baseline pareada por (mercado, hora do dia UTC) sobre as barras
**sem** aquele padrão, subtraída linha a linha antes do bootstrap.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict

import numpy as np

AQUI = "C:/dev/project-hunter/.claude/state/exp-drafts/t355"
for _p in (AQUI, "C:/dev/project-hunter/.claude/state/exp-drafts/t342-blocos"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bootstrap_padroes import Contraste, contraste_rapido, holm  # noqa: E402
from padroes import NOMES, SINAL  # noqa: E402

HORIZONTES = (1, 4, 16)
TFS = ("15m", "1h")

MIN_OCORRENCIAS = 30
MIN_DIAS = 10
"""Portao de raridade, com o numero da propria KB-0080 §7.

Com 1 ou 2 ocorrencias o bootstrap de blocos degenera: toda reamostragem que
sorteia aquele dia devolve exatamente o mesmo valor, o IC encolhe ao redor de uma
observacao e o p-valor vira 0,0001. Nao e evidencia, e aritmetica de amostra
minuscula. Rotulo abaixo do portao recebe `raro`, sai da familia de Holm e NAO
recebe IC publicavel -- mas continua na tabela, com o n, porque sumir com ele
esconderia que a definicao existe e quase nao dispara."""


class Universo:
    """As barras utilizáveis de um timeframe, em colunas NumPy."""

    def __init__(self, linhas: list[dict[str, str]]) -> None:
        simbolos = sorted({linha["symbol"] for linha in linhas})
        codigo = {s: k for k, s in enumerate(simbolos)}
        self.simbolos = simbolos
        self.sym = np.array([codigo[linha["symbol"]] for linha in linhas])
        self.hora = np.array([int(linha["hora"]) for linha in linhas])
        self.dia = np.array([linha["dia"] for linha in linhas])
        self.atr_pct = np.array([float(linha["atr_pct"]) for linha in linhas])
        self.r = {k: np.array([float(linha[f"r{k}"]) for linha in linhas]) for k in HORIZONTES}
        self.celula = self.sym * 24 + self.hora
        self.n_celulas = len(simbolos) * 24
        self.chave = {(linha["symbol"], linha["ts"]): i for i, linha in enumerate(linhas)}


def carregar_universo(sufixo: str = "") -> dict[str, Universo]:
    por_tf: dict[str, list[dict[str, str]]] = defaultdict(list)
    with open(f"{AQUI}/universo{sufixo}.csv", newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            por_tf[linha["tf"]].append(linha)
    return {tf: Universo(linhas) for tf, linhas in por_tf.items()}


def carregar_marcas(
    universos: dict[str, Universo], sufixo: str = "", nomes: tuple[str, ...] = NOMES
) -> dict[tuple[str, str], np.ndarray]:
    marcas = {
        (nome, tf): np.zeros(universos[tf].sym.size, dtype=bool)
        for nome in nomes
        for tf in TFS
        if tf in universos
    }
    with open(f"{AQUI}/ocorrencias{sufixo}.csv", newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            u = universos[linha["tf"]]
            marcas[(linha["nome"], linha["tf"])][u.chave[(linha["symbol"], linha["ts"])]] = True
    return marcas


def residuo_pareado(u: Universo, r: np.ndarray, marca: np.ndarray, sinal: int) -> np.ndarray:
    """`sinal * (r - media(r | mesma célula, sem o padrão))`.

    A célula é (mercado, hora do dia UTC). Célula sem nenhuma barra livre do
    padrão fica com deslocamento zero — não há baseline a subtrair e inventar uma
    seria pior do que declarar.
    """
    livre = ~marca
    soma = np.bincount(u.celula[livre], weights=r[livre], minlength=u.n_celulas)
    conta = np.bincount(u.celula[livre], minlength=u.n_celulas)
    base = np.divide(soma, conta, out=np.zeros_like(soma), where=conta > 0)
    return sinal * (r - base[u.celula])


def rodar(
    sufixo: str = "", nomes: tuple[str, ...] = NOMES, sinal: dict[str, int] | None = None
) -> list[tuple[Contraste, bool]]:
    """Devolve `(contraste, raro)`; `raro` fica fora da familia de Holm."""
    sinal = SINAL if sinal is None else sinal
    universos = carregar_universo(sufixo)
    marcas = carregar_marcas(universos, sufixo, nomes)
    saida: list[tuple[Contraste, bool]] = []
    for tf in TFS:
        u = universos[tf]
        for nome in nomes:
            marca = marcas[(nome, tf)]
            dias_ocor = len(set(u.dia[marca].tolist()))
            raro = int(marca.sum()) < MIN_OCORRENCIAS or dias_ocor < MIN_DIAS
            for k in HORIZONTES:
                chave = f"{nome}|{tf}|h{k}"
                if not marca.any():
                    vazio = Contraste(
                        chave,
                        0,
                        int(marca.size),
                        0,
                        float("nan"),
                        float("nan"),
                        float("nan"),
                        (float("nan"), float("nan")),
                        1.0,
                        0,
                    )
                    saida.append((vazio, True))
                    continue
                res = residuo_pareado(u, u.r[k], marca, sinal[nome])
                saida.append((contraste_rapido(chave, u.dia, res, marca), raro))
    return saida


def main(
    sufixo: str = "", nomes: tuple[str, ...] = NOMES, sinal: dict[str, int] | None = None
) -> dict[str, float]:
    """Imprime a tabela e devolve os p-valores da familia (para o Holm conjunto)."""
    linhas = rodar(sufixo, nomes, sinal)
    contrastes = [c for c, _ in linhas]
    raros = {c.chave for c, raro in linhas if raro}
    familia = {c.chave: c.p_valor for c in contrastes if c.chave not in raros}
    ajustado = holm(familia)
    por_horizonte = {}
    for k in HORIZONTES:
        sub = {ch: p for ch, p in familia.items() if ch.endswith(f"h{k}")}
        por_horizonte.update(holm(sub))

    print(
        f"rotulos medidos: {len(contrastes)} "
        f"({len(nomes)} x {len(TFS)} tf x {len(HORIZONTES)} horizontes) | "
        f"raros (n < {MIN_OCORRENCIAS} ou dias < {MIN_DIAS}): {len(raros)} | "
        f"familia de Holm: {len(familia)}"
    )
    print(
        f"{'padrao':<16}{'tf':>5}{'h':>4}{'n':>7}{'dias':>6}{'bruto':>10}{'delta':>10}"
        f"{'IC95 baixo':>12}{'IC95 alto':>11}{'p':>9}{'Holm':>9}{'Holm/h':>9}"
    )
    for c in contrastes:
        nome, tf, h = c.chave.split("|")
        bruto = c.exp_variante
        print(
            f"{nome:<16}{tf:>5}{h[1:]:>4}{c.n_variante:>7}{c.dias:>6}"
            f"{bruto:>10.4f}{c.delta:>10.4f}{c.ic95[0]:>12.4f}{c.ic95[1]:>11.4f}"
            f"{c.p_valor:>9.4f}"
            + (
                f"{'raro':>9}{'raro':>9}"
                if c.chave in raros
                else f"{ajustado[c.chave][0]:>9.3f}{por_horizonte[c.chave][0]:>9.3f}"
            )
        )
    sobreviventes = [ch for ch in familia if ajustado[ch][1]]
    print(f"sobrevivem a Holm(m={len(familia)}) com alfa 0,05: {sobreviventes or 'nenhum'}")
    sob28 = [ch for ch in familia if por_horizonte[ch][1]]
    print(f"sobrevivem a Holm por horizonte: {sob28 or 'nenhum'}")
    return {ch: familia[ch] for ch in familia}


if __name__ == "__main__":
    main()
