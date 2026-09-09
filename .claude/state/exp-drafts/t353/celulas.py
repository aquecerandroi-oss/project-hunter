"""T3.53 - o mapa de onde cada versao ganha e perde, celula a celula.

Nao e codigo de producao: mora em ``.claude/state/exp-drafts/`` e responde a uma
unica pergunta desta nota - *existe alguma fatia (mercado, hora do dia, dia da
semana, regime horario do BTC, faixa de pedagio) em que uma versao se comporta
diferente do resto da propria populacao, e essa diferenca sobrevive ao fato de
termos olhado para dezenas de fatias?*

TRES DECISOES QUE MUDAM O RESULTADO E ESTAO AQUI, EXPLICITAS:

1. **O dia e o bloco.** Decisoes do mesmo dia, em mercados correlacionados,
   compartilham choque ([[KB-0010]]); trata-las como independentes estreita o
   intervalo artificialmente. Reamostram-se **dias inteiros** com reposicao -
   a mesma convencao de ``t342-blocos/blocos.py``, que este arquivo importa e
   usa como oraculo de conferencia (``conferir.py``).

2. **O contraste e celula contra RESTO da mesma populacao**, nao celula contra a
   populacao inteira (que contem a celula). ``blocos.contraste_por_piso`` faz o
   segundo; os dois tem o mesmo sinal em cada reamostragem, porque
   ``media(celula) - media(tudo) = (1-w) * (media(celula) - media(resto))`` com
   ``w`` = fracao da celula, sempre positiva. A conferencia usa essa identidade.

3. **Hora de Brasilia e hora UTC sao a MESMA particao** (deslocada de 3 h), entao
   trata-las como duas dimensoes dobraria a multiplicidade sem trazer nenhuma
   informacao. A hora e testada **uma vez** e o rotulo sai nos dois relogios.

MULTIPLICIDADE: Holm ao nivel 5 % sobre todas as celulas **julgaveis** da mesma
versao (n >= 30, >= 7 dias distintos, e resto com n >= 30). Celula que nao atinge
o minimo e impressa com ``nao julgavel`` e fica fora da familia de testes - nem
gasta orcamento nem ganha selo.

p-valor: nivel de significancia alcancado do bootstrap (ASL de dois lados),
``2*min(#{D*<=0}+1, #{D*>=0}+1)/(B+1)``, limitado a 1. E o p que o proprio
intervalo percentil implica; nao ha aproximacao normal em lugar nenhum.

NumPy sobre janelas em memoria; nada de ``Decimal`` porque nada disto e dinheiro
persistido (a fronteira ``Decimal`` fica no banco, PIPELINE 9).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

B_PADRAO = 10_000
SEED = 20260908
N_MIN = 30
DIAS_MIN = 7
ALFA = 0.05


@dataclass(frozen=True)
class Celula:
    versao: str
    coorte: str
    dimensao: str
    rotulo: str
    n: int
    dias: int
    exp: float
    exp_resto: float
    delta: float
    ic95: tuple[float, float]
    p: float
    pf: float
    acerto: float
    soma_r: float
    custo: float
    exp_bruta: float
    julgavel: bool
    n_resto: int
    dias_resto: int


def pf(r: np.ndarray) -> float:
    ganho = float(r[r > 0].sum())
    perda = float(-r[r < 0].sum())
    if perda == 0:
        return float("inf") if ganho > 0 else float("nan")
    return ganho / perda


def media(r: np.ndarray) -> float:
    """Media simples; ``nan`` para amostra vazia (nunca 0,0, que seria inventado)."""
    return float(r.mean()) if r.size else float("nan")


def bootstrap_celula(
    dias: np.ndarray,
    n_dias: int,
    r: np.ndarray,
    dentro: np.ndarray,
    *,
    reamostragens: int = B_PADRAO,
    seed: int = SEED,
) -> tuple[float, tuple[float, float], float, int]:
    """(delta, IC95, p, reamostragens validas) com o dia como bloco.

    Vetorizado: por dia guardam-se ``(soma, n)`` dentro e fora da celula; uma
    reamostragem e uma soma de linhas dessas quatro colunas. E exatamente o mesmo
    estimador do laco ingenuo de ``blocos.py`` - ``conferir.py`` prova.
    """
    fora = ~dentro
    soma_in = np.bincount(dias[dentro], weights=r[dentro], minlength=n_dias)
    n_in = np.bincount(dias[dentro], minlength=n_dias).astype(float)
    soma_out = np.bincount(dias[fora], weights=r[fora], minlength=n_dias)
    n_out = np.bincount(dias[fora], minlength=n_dias).astype(float)

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n_dias, size=(reamostragens, n_dias))
    si = soma_in[idx].sum(axis=1)
    ni = n_in[idx].sum(axis=1)
    so = soma_out[idx].sum(axis=1)
    no = n_out[idx].sum(axis=1)
    ok = (ni > 0) & (no > 0)
    deltas = si[ok] / ni[ok] - so[ok] / no[ok]

    delta = media(r[dentro]) - media(r[fora])
    if deltas.size == 0:
        return delta, (float("nan"), float("nan")), float("nan"), 0
    ic = (float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5)))
    n_le = int((deltas <= 0).sum())
    n_ge = int((deltas >= 0).sum())
    p = min(1.0, 2.0 * (min(n_le, n_ge) + 1) / (deltas.size + 1))
    return delta, ic, p, int(deltas.size)


def holm(ps: list[float], alfa: float = ALFA) -> list[bool]:
    """Holm ao nivel ``alfa``: passo descendente, para no primeiro que falha."""
    m = len(ps)
    ordem = sorted(range(m), key=lambda i: ps[i])
    sobrevive = [False] * m
    for pos, i in enumerate(ordem):
        if ps[i] <= alfa / (m - pos):
            sobrevive[i] = True
        else:
            break
    return sobrevive


def carregar(caminho: str) -> list[dict]:
    with open(caminho, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


FAIXAS_PEDAGIO = (
    ("pedagio < 0,10 R", lambda c: c < 0.10),
    ("pedagio 0,10-0,20 R", lambda c: 0.10 <= c <= 0.20),
    ("pedagio > 0,20 R", lambda c: c > 0.20),
)

DIA_SEMANA = {1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex", 6: "sab", 7: "dom"}


def dimensoes(linhas: list[dict]) -> list[tuple[str, str, np.ndarray]]:
    """(dimensao, rotulo, mascara) de todas as celulas candidatas da populacao."""
    n = len(linhas)
    saida: list[tuple[str, str, np.ndarray]] = []

    def por_chave(dim, chave, rotulo=str):
        grupos: dict[object, list[int]] = defaultdict(list)
        for i, linha in enumerate(linhas):
            grupos[chave(linha)].append(i)
        for valor, idxs in sorted(grupos.items(), key=lambda kv: str(kv[0])):
            m = np.zeros(n, dtype=bool)
            m[idxs] = True
            saida.append((dim, rotulo(valor), m))

    por_chave("mercado", lambda l: l["symbol"])
    por_chave(
        "hora",
        lambda l: int(l["hora_br"]),
        lambda h: f"{h:02d}h BRT ({(h + 3) % 24:02d}h UTC)",
    )
    por_chave("dia_semana", lambda l: int(l["dow_br"]), lambda d: f"{DIA_SEMANA[d]} (BRT)")
    por_chave("regime", lambda l: l["regime"])
    por_chave("trend_x_vol", lambda l: f"{l['trend']}/{l['vol']}")

    custos = np.array([float(l["custo_id"]) for l in linhas])
    for nome, teste in FAIXAS_PEDAGIO:
        saida.append(("pedagio", nome, np.array([teste(c) for c in custos], dtype=bool)))
    return saida


def deduplicar(
    dims: list[tuple[str, str, np.ndarray]]
) -> tuple[list[tuple[str, str, np.ndarray]], list[str]]:
    """Funde celulas que sao a MESMA hipotese - senao Holm cobra duas vezes por ela.

    Duas fontes de duplicata nesta populacao:
      * ``regime`` e ``trend_x_vol`` sao a mesma particao quando o rotulo do
        regime cobre um unico par (``SIDEWAYS`` == ``flat/normal``); o
        classificador horario projeta trend x vol em regime, entao a coarsening
        coincide com a celula fina em varios rotulos.
      * mascara complementar: numa dimensao com exatamente duas celulas nao
        vazias, ``A contra o resto`` e ``B contra o resto`` sao o mesmo teste com
        o sinal trocado.
    Fica a primeira ocorrencia, com o rotulo das duas; a segunda sai da familia.
    """
    vistas: dict[bytes, int] = {}
    saida: list[tuple[str, str, np.ndarray]] = []
    fusoes: list[str] = []
    for dim, rotulo, m in dims:
        chave = m.tobytes()
        chave_c = (~m).tobytes()
        if chave in vistas:
            i = vistas[chave]
            d0, r0, m0 = saida[i]
            saida[i] = (f"{d0}+{dim}", f"{r0} = {rotulo}", m0)
            fusoes.append(f"{dim}:{rotulo} == {d0}:{r0}")
            continue
        if chave_c in vistas:
            i = vistas[chave_c]
            d0, r0, m0 = saida[i]
            saida[i] = (f"{d0}+{dim}", f"{r0} (vs {rotulo})", m0)
            fusoes.append(f"{dim}:{rotulo} == complemento de {d0}:{r0}")
            continue
        vistas[chave] = len(saida)
        saida.append((dim, rotulo, m))
    return saida, fusoes


def analisar(
    linhas: list[dict],
    versao: str,
    coorte: str,
    *,
    reamostragens: int = B_PADRAO,
    fusoes: list[str] | None = None,
) -> list[Celula]:
    dias_rotulo = sorted({l["dia_br"] for l in linhas})
    idx_dia = {d: i for i, d in enumerate(dias_rotulo)}
    dias = np.array([idx_dia[l["dia_br"]] for l in linhas], dtype=int)
    r = np.array([float(l["r_net"]) for l in linhas])
    bruto = np.array([float(l["r_gross"]) for l in linhas])
    custo = np.array([float(l["custo_id"]) for l in linhas])
    alvo = np.array([l["motivo"] == "target" for l in linhas])

    # A deduplicacao so vale entre celulas grandes: duas celulas minusculas
    # identicas por acaso nao sao a mesma hipotese testada, sao duas nao
    # julgaveis - e nenhuma delas gasta orcamento de Holm.
    candidatas = [(d, r, m) for d, r, m in dimensoes(linhas) if m.any()]
    grandes = [(d, r, m) for d, r, m in candidatas if int(m.sum()) >= N_MIN]
    pequenas = [(d, r, m) for d, r, m in candidatas if int(m.sum()) < N_MIN]
    grandes, fundidas = deduplicar(grandes)
    if fusoes is not None:
        fusoes.extend(fundidas)

    celulas: list[Celula] = []
    for dim, rotulo, m in grandes + pequenas:
        n_cel = int(m.sum())
        resto = ~m
        d_cel = len({dias_rotulo[i] for i in dias[m]})
        julgavel = n_cel >= N_MIN and d_cel >= DIAS_MIN and int(resto.sum()) >= N_MIN
        if julgavel:
            delta, ic, p, _ = bootstrap_celula(
                dias, len(dias_rotulo), r, m, reamostragens=reamostragens
            )
        else:
            delta = media(r[m]) - media(r[resto])
            ic, p = (float("nan"), float("nan")), float("nan")
        celulas.append(
            Celula(
                versao=versao,
                coorte=coorte,
                dimensao=dim,
                rotulo=rotulo,
                n=n_cel,
                dias=d_cel,
                exp=media(r[m]),
                exp_resto=media(r[resto]),
                delta=delta,
                ic95=ic,
                p=p,
                pf=pf(r[m]),
                acerto=100.0 * float(alvo[m].mean()),
                soma_r=float(r[m].sum()),
                custo=float(custo[m].mean()),
                exp_bruta=media(bruto[m]),
                julgavel=julgavel,
                n_resto=int(resto.sum()),
                dias_resto=len({dias_rotulo[i] for i in dias[resto]}),
            )
        )
    return celulas
