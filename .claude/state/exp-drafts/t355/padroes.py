"""Detector-protótipo de padrões de candlestick — T3.55b (PESQUISA, não produção).

Mora em ``.claude/state/exp-drafts/`` de propósito: nenhuma linha daqui é importada
por ``hunter_core.strategies.*`` nem entra em ``DEFAULT_REGISTRY``. Se algum padrão
sobreviver à medição, ele volta como ``FeatureDefinition`` versionada num pacote de
produção — e aí o número desta nota é o alvo do teste de paridade.

Regras que o brief impõe e que estão implementadas aqui:

1. **Fechamento, nunca antecipação.** ``detectar(bars, atr, i)`` lê apenas
   ``bars[: i + 1]`` e ``atr[: i + 1]``. Um padrão de três barras terminando em ``i``
   é conhecido no **fechamento de ``i``**, nunca antes. Provado por
   ``test_padroes.py::test_um_padrao_nao_muda_quando_o_futuro_muda``.
2. **Decimal do começo ao fim.** Toda a aritmética de preço roda em
   ``localcontext(CONTEXT)`` do ``hunter_core`` (prec=28, ROUND_HALF_EVEN). ``float``
   só existe do outro lado da fronteira, no bootstrap (NumPy), onde nada é dinheiro.
3. **Escala é o ATR de Wilder congelado** (``hunter_core.strategies.indicators.wilder_atr``,
   período 14, dobrado barra a barra por ``hunter_indicators.patterns.scale.atr_series``):
   não há segunda fórmula de ATR neste repositório e não vou criar uma terceira.
4. **A régua é anterior ao padrão.** Um padrão de ``n`` barras terminando em ``i`` é
   medido contra ``ATR[i-n]`` — o ATR fechado **antes** da primeira barra do padrão.
   Usar ``ATR[i]`` deixaria a barra inflar a própria régua: um marubozu de 3 ATRs
   engorda o ATR e reaparece como um marubozu de 1,8 ATR. Não é antecipação
   (``ATR[i]`` é conhecido no fechamento de ``i``), é um problema de significado.
   Barra sem essa régua (aquecimento) não produz padrão — filtrar por uma escala
   inventada seria pior do que não reportar.

## As definições numéricas (v1 — mudar um número é v2, nunca edição)

Para a barra ``k``: ``corpo = |C-O|``, ``faixa = H-L``, ``pavio_sup = H-max(O,C)``,
``pavio_inf = min(O,C)-L``. Barra com ``faixa = 0`` não produz padrão (razão indefinida).

``contexto(j)`` — a tendência **antes** da primeira barra do padrão, em ATR:
``(C[j-1] - C[j-1-10]) / ATR[j-1]``; ``alta`` se >= +1,0, ``baixa`` se <= -1,0, senão
``lateral``. ``ATR[j-1]`` é exatamente a régua ``escala`` do padrão. Onde o padrão
clássico exige contexto, ele é exigido.

| padrão | direção | definição (``A`` = escala = ``ATR[i-n]``) |
|---|---|---|
| `engolfo_alta` | long | `k-1` de baixa, `k` de alta, `O[k] <= C[k-1]`, `C[k] >= O[k-1]`, `corpo[k] > corpo[k-1]`, `corpo[k] >= 0,5*A`, contexto **baixa** |
| `engolfo_baixa` | short | espelho, contexto **alta** |
| `martelo` | long | `corpo <= 0,35*faixa`, `pavio_inf >= 2,0*corpo`, `pavio_inf >= 0,60*faixa`, `pavio_sup <= 0,15*faixa`, `faixa >= 0,5*A`, contexto **baixa** |
| `enforcado` | short | mesma geometria do martelo, contexto **alta** |
| `estrela_cadente` | short | `corpo <= 0,35*faixa`, `pavio_sup >= 2,0*corpo`, `pavio_sup >= 0,60*faixa`, `pavio_inf <= 0,15*faixa`, `faixa >= 0,5*A`, contexto **alta** |
| `doji` | neutro | `corpo <= 0,10*faixa`, `faixa >= 0,5*A`, qualquer contexto |
| `marubozu_alta` | long | alta, `corpo >= 0,90*faixa`, `faixa >= 0,8*A` |
| `marubozu_baixa` | short | espelho |
| `harami_alta` | long | `k-1` de baixa com `corpo >= 0,60*faixa` e `faixa >= 1,0*A`; `k` de alta com o corpo **dentro** do corpo de `k-1` e `corpo[k] <= 0,5*corpo[k-1]`; contexto **baixa** |
| `harami_baixa` | short | espelho, contexto **alta** |
| `estrela_manha` | long | `k-2` de baixa (`corpo >= 0,60*faixa`, `faixa >= 1,0*A`); `k-1` com `corpo <= 0,30*corpo[k-2]`; `k` de alta com `C[k] >= (O[k-2]+C[k-2])/2` e `corpo[k] >= 0,5*corpo[k-2]`; contexto **baixa** |
| `estrela_noite` | short | espelho, contexto **alta** |
| `tres_soldados` | long | três de alta, cada `corpo >= 0,5*faixa` e `pavio_sup <= 0,3*corpo`, `C` crescente, `O[k]` dentro do corpo anterior, soma dos corpos >= 1,0*A |
| `tres_corvos` | short | espelho |

**Invalidação natural** (o que o padrão afirma e que, se violado, apaga a afirmação) —
é ela que vira distância de stop na lente de pedágio da KB-0076:

| padrão | stop natural |
|---|---|
| engolfo / harami | extremo oposto das **duas** barras |
| martelo / marubozu / estrela de 3 barras / soldados / corvos | extremo oposto do próprio padrão |
| enforcado / estrela_cadente | acima da máxima da barra (o sinal é de baixa) |
| doji | o extremo mais distante do fechamento (não há afirmação direcional) |
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal, localcontext

sys.path.insert(0, "C:/dev/project-hunter/packages/core")

from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.indicators import CONTEXT

VERSAO = "padroes_v1"

CORPO_DOJI = Decimal("0.10")
CORPO_PEQUENO = Decimal("0.35")
CORPO_GRANDE = Decimal("0.60")
CORPO_MARUBOZU = Decimal("0.90")
PAVIO_DOMINANTE = Decimal("0.60")
PAVIO_OPOSTO = Decimal("0.15")
PAVIO_X_CORPO = Decimal("2.0")
FAIXA_MIN_ATR = Decimal("0.5")
MARUBOZU_FAIXA_ATR = Decimal("0.8")
ENGOLFO_CORPO_ATR = Decimal("0.5")
HARAMI_MAE_ATR = Decimal("1.0")
HARAMI_FILHO = Decimal("0.5")
ESTRELA_CORPO = Decimal("0.30")
ESTRELA_CORPO3 = Decimal("0.5")
SOLDADO_CORPO = Decimal("0.5")
SOLDADO_PAVIO = Decimal("0.3")
SOLDADO_SOMA_ATR = Decimal("1.0")
TEND_BARRAS = 10
TEND_ATR = Decimal("1.0")

LONG = "long"
SHORT = "short"
NEUTRO = "neutro"

NOMES: tuple[str, ...] = (
    "engolfo_alta",
    "engolfo_baixa",
    "martelo",
    "enforcado",
    "estrela_cadente",
    "doji",
    "marubozu_alta",
    "marubozu_baixa",
    "harami_alta",
    "harami_baixa",
    "estrela_manha",
    "estrela_noite",
    "tres_soldados",
    "tres_corvos",
)

DIRECAO: dict[str, str] = {
    "engolfo_alta": LONG,
    "engolfo_baixa": SHORT,
    "martelo": LONG,
    "enforcado": SHORT,
    "estrela_cadente": SHORT,
    "doji": NEUTRO,
    "marubozu_alta": LONG,
    "marubozu_baixa": SHORT,
    "harami_alta": LONG,
    "harami_baixa": SHORT,
    "estrela_manha": LONG,
    "estrela_noite": SHORT,
    "tres_soldados": LONG,
    "tres_corvos": SHORT,
}

SINAL: dict[str, int] = {nome: (-1 if DIRECAO[nome] == SHORT else 1) for nome in NOMES}


@dataclass(frozen=True, slots=True)
class Deteccao:
    """Um padrão conhecido no fechamento de ``idx``."""

    nome: str
    direcao: str
    idx: int
    barras: int
    entrada: Decimal
    """O fechamento da última barra: o único preço que existe no instante da detecção."""
    stop: Decimal
    """A invalidação natural do padrão, em preço."""
    escala: Decimal
    """``ATR[idx - barras]``: o ATR fechado antes da primeira barra do padrão."""
    stop_atr: Decimal
    """``|entrada - stop| / escala`` — a distância de stop que o padrão pede."""


def corpo_de(b: Bar) -> Decimal:
    return abs(b.close - b.open)


def faixa_de(b: Bar) -> Decimal:
    return b.high - b.low


def pavio_sup_de(b: Bar) -> Decimal:
    return b.high - max(b.open, b.close)


def pavio_inf_de(b: Bar) -> Decimal:
    return min(b.open, b.close) - b.low


def e_alta(b: Bar) -> bool:
    return b.close > b.open


def e_baixa(b: Bar) -> bool:
    return b.close < b.open


def contexto(bars: list[Bar], atr: list[Decimal | None], j: int) -> str | None:
    """Tendência nas ``TEND_BARRAS`` barras que terminam **antes** de ``j``.

    ``None`` quando não há histórico ou ATR — e sem contexto o padrão que exige
    contexto simplesmente não existe (nunca vira ``lateral`` por conveniência).
    """
    ancora = j - 1
    inicio = ancora - TEND_BARRAS
    if inicio < 0:
        return None
    escala = atr[ancora]
    if escala is None or escala <= 0:
        return None
    with localcontext(CONTEXT):
        delta = (bars[ancora].close - bars[inicio].close) / escala
    if delta >= TEND_ATR:
        return "alta"
    if delta <= -TEND_ATR:
        return "baixa"
    return "lateral"


def dist_em_atr(entrada: Decimal, stop: Decimal, escala: Decimal) -> Decimal:
    with localcontext(CONTEXT):
        return abs(entrada - stop) / escala


def detectar(bars: list[Bar], atr: list[Decimal | None], i: int) -> list[Deteccao]:
    """Todos os padrões cuja **última** barra é ``i``, conhecidos no fechamento de ``i``.

    Lê apenas ``bars[: i + 1]`` e ``atr[: i + 1]``.
    """
    achados: list[Deteccao] = []
    escala1 = atr[i - 1] if i >= 1 else None
    escala2 = atr[i - 2] if i >= 2 else None
    escala3 = atr[i - 3] if i >= 3 else None
    if escala1 is None or escala1 <= 0:
        return achados
    b0 = bars[i]
    faixa0 = faixa_de(b0)
    if faixa0 <= 0:
        return achados
    corpo0 = corpo_de(b0)
    sup0 = pavio_sup_de(b0)
    inf0 = pavio_inf_de(b0)
    entrada = b0.close

    def add(nome: str, barras: int, stop: Decimal, escala: Decimal) -> None:
        achados.append(
            Deteccao(
                nome=nome,
                direcao=DIRECAO[nome],
                idx=i,
                barras=barras,
                entrada=entrada,
                stop=stop,
                escala=escala,
                stop_atr=dist_em_atr(entrada, stop, escala),
            )
        )

    ctx1 = contexto(bars, atr, i)

    # --- uma barra -------------------------------------------------------
    if corpo0 <= CORPO_DOJI * faixa0 and faixa0 >= FAIXA_MIN_ATR * escala1:
        longe = b0.low if (entrada - b0.low) >= (b0.high - entrada) else b0.high
        add("doji", 1, longe, escala1)

    martelo_geom = (
        corpo0 <= CORPO_PEQUENO * faixa0
        and inf0 >= PAVIO_X_CORPO * corpo0
        and inf0 >= PAVIO_DOMINANTE * faixa0
        and sup0 <= PAVIO_OPOSTO * faixa0
        and faixa0 >= FAIXA_MIN_ATR * escala1
    )
    if martelo_geom and ctx1 == "baixa":
        add("martelo", 1, b0.low, escala1)
    if martelo_geom and ctx1 == "alta":
        add("enforcado", 1, b0.high, escala1)

    estrela_geom = (
        corpo0 <= CORPO_PEQUENO * faixa0
        and sup0 >= PAVIO_X_CORPO * corpo0
        and sup0 >= PAVIO_DOMINANTE * faixa0
        and inf0 <= PAVIO_OPOSTO * faixa0
        and faixa0 >= FAIXA_MIN_ATR * escala1
    )
    if estrela_geom and ctx1 == "alta":
        add("estrela_cadente", 1, b0.high, escala1)

    if corpo0 >= CORPO_MARUBOZU * faixa0 and faixa0 >= MARUBOZU_FAIXA_ATR * escala1:
        if e_alta(b0):
            add("marubozu_alta", 1, b0.low, escala1)
        elif e_baixa(b0):
            add("marubozu_baixa", 1, b0.high, escala1)

    # --- duas barras -----------------------------------------------------
    if i >= 2 and escala2 is not None and escala2 > 0:
        b1 = bars[i - 1]
        corpo1 = corpo_de(b1)
        faixa1 = faixa_de(b1)
        ctx2 = contexto(bars, atr, i - 1)
        if faixa1 > 0:
            if (
                e_baixa(b1)
                and e_alta(b0)
                and b0.open <= b1.close
                and b0.close >= b1.open
                and corpo0 > corpo1
                and corpo0 >= ENGOLFO_CORPO_ATR * escala2
                and ctx2 == "baixa"
            ):
                add("engolfo_alta", 2, min(b0.low, b1.low), escala2)
            if (
                e_alta(b1)
                and e_baixa(b0)
                and b0.open >= b1.close
                and b0.close <= b1.open
                and corpo0 > corpo1
                and corpo0 >= ENGOLFO_CORPO_ATR * escala2
                and ctx2 == "alta"
            ):
                add("engolfo_baixa", 2, max(b0.high, b1.high), escala2)

            mae_grande = corpo1 >= CORPO_GRANDE * faixa1 and faixa1 >= HARAMI_MAE_ATR * escala2
            dentro = (
                max(b0.open, b0.close) <= max(b1.open, b1.close)
                and min(b0.open, b0.close) >= min(b1.open, b1.close)
                and corpo0 <= HARAMI_FILHO * corpo1
            )
            if mae_grande and dentro and e_baixa(b1) and e_alta(b0) and ctx2 == "baixa":
                add("harami_alta", 2, min(b0.low, b1.low), escala2)
            if mae_grande and dentro and e_alta(b1) and e_baixa(b0) and ctx2 == "alta":
                add("harami_baixa", 2, max(b0.high, b1.high), escala2)

    # --- três barras -----------------------------------------------------
    if i >= 3 and escala3 is not None and escala3 > 0:
        b1, b2 = bars[i - 1], bars[i - 2]
        corpo1, corpo2 = corpo_de(b1), corpo_de(b2)
        faixa1, faixa2 = faixa_de(b1), faixa_de(b2)
        ctx3 = contexto(bars, atr, i - 2)
        if faixa1 > 0 and faixa2 > 0:
            with localcontext(CONTEXT):
                meio2 = (b2.open + b2.close) / Decimal(2)
            grande2 = corpo2 >= CORPO_GRANDE * faixa2 and faixa2 >= HARAMI_MAE_ATR * escala3
            estrela_pequena = corpo1 <= ESTRELA_CORPO * corpo2
            if (
                grande2
                and estrela_pequena
                and e_baixa(b2)
                and e_alta(b0)
                and b0.close >= meio2
                and corpo0 >= ESTRELA_CORPO3 * corpo2
                and ctx3 == "baixa"
            ):
                add("estrela_manha", 3, min(b0.low, b1.low, b2.low), escala3)
            if (
                grande2
                and estrela_pequena
                and e_alta(b2)
                and e_baixa(b0)
                and b0.close <= meio2
                and corpo0 >= ESTRELA_CORPO3 * corpo2
                and ctx3 == "alta"
            ):
                add("estrela_noite", 3, max(b0.high, b1.high, b2.high), escala3)

            trio = (b2, b1, b0)
            corpos = (corpo2, corpo1, corpo0)
            faixas = (faixa2, faixa1, faixa0)
            soma = corpo0 + corpo1 + corpo2
            forma = all(c >= SOLDADO_CORPO * f for c, f in zip(corpos, faixas, strict=True))
            if (
                forma
                and soma >= SOLDADO_SOMA_ATR * escala3
                and all(e_alta(b) for b in trio)
                and b1.close > b2.close
                and b0.close > b1.close
                and b2.close >= b1.open >= b2.open
                and b1.close >= b0.open >= b1.open
                and all(
                    pavio_sup_de(b) <= SOLDADO_PAVIO * c for b, c in zip(trio, corpos, strict=True)
                )
            ):
                add("tres_soldados", 3, min(b0.low, b1.low, b2.low), escala3)
            if (
                forma
                and soma >= SOLDADO_SOMA_ATR * escala3
                and all(e_baixa(b) for b in trio)
                and b1.close < b2.close
                and b0.close < b1.close
                and b2.close <= b1.open <= b2.open
                and b1.close <= b0.open <= b1.open
                and all(
                    pavio_inf_de(b) <= SOLDADO_PAVIO * c for b, c in zip(trio, corpos, strict=True)
                )
            ):
                add("tres_corvos", 3, max(b0.high, b1.high, b2.high), escala3)

    return achados


def varrer(bars: list[Bar], atr: list[Decimal | None]) -> list[Deteccao]:
    """Uma passada por toda a série, barra a barra, sempre no fechamento."""
    saida: list[Deteccao] = []
    for i in range(len(bars)):
        saida.extend(detectar(bars, atr, i))
    return saida
