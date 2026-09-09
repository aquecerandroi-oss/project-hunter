"""O segundo conjunto de definições: as da [[KB-0080]] §7 — T3.55b (pesquisa).

A parte (a) desta task ficou pronta **depois** que a medição da parte (b) já
estava rodando (KB-0080 gravada 2026-09-09 00:16 BRT; a varredura de `padroes_v1`
começou 23:58 BRT). O brief previa exatamente isso ("se (a) não estiver pronta,
use o conjunto padrão... (a) pode refiná-las"). Em vez de trocar as constantes e
publicar um número só, este arquivo implementa **o conjunto da (a) inteiro** e a
nota publica os dois. Se a conclusão mudasse entre os dois, ela seria sobre as
constantes, não sobre os padrões — e isso é o que precisa aparecer.

Diferenças que valem registro contra `padroes.py` (`padroes_v1`):

| item | `padroes_v1` (b) | `padroes_kb0080_v1` (a) |
|---|---|---|
| contexto | `(C[t0-1] - C[t0-11]) / ATR` >= 1,0 em módulo | `C < EMA10` **e** `EMA10` caindo (`EMA10[t0-1] < EMA10[t0-4]`), régua de Marshall |
| martelo | `amp >= 0,5·ATR`, `inf >= 0,60·amp`, `sup <= 0,15·amp` | `amp >= 0,8·ATR`, `sup <= 0,10·amp`, sem piso em `inf/amp` |
| marubozu | `corpo >= 0,90·amp` e `amp >= 0,8·ATR` | `corpo >= 1,0·ATR` e as duas sombras `<= 0,10·amp` |
| harami | corpo dentro **com igualdade**, cor da filha oposta à mãe | corpo **estritamente** dentro, cor da filha livre |
| doji | direção nenhuma | direção = reversão do contexto (dois rótulos) |
| soldados | `corpo >= 0,5·amp`, `sup <= 0,3·corpo`, soma `>= 1,0·ATR` | `corpo_i >= 0,5·ATR`, `sup_i <= 0,2·amp_i` |
| a mais | — | martelo invertido, três-dentro para cima/baixo |

Iguais nos dois: a régua é `ATR[t0-1]` (anterior à primeira barra), a detecção é no
fechamento da última barra, e o meio do corpo da estrela (`C1 + 0,5·corpo1` é
algebricamente `(O1+C1)/2`).

EMA10: semeada com a média simples dos dez primeiros fechamentos no índice 9 e
`alfa = 2/11` depois. A semente é uma escolha declarada — a KB-0080 não a fixa e
uma EMA sem semente declarada é um número diferente por implementação.
"""

from __future__ import annotations

import sys
from decimal import Decimal, localcontext

AQUI = "C:/dev/project-hunter/.claude/state/exp-drafts/t355"
for _p in (AQUI, "C:/dev/project-hunter/packages/core"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from padroes import (  # noqa: E402
    Deteccao,
    e_alta,
    e_baixa,
    corpo_de,
    dist_em_atr,
    faixa_de,
    pavio_inf_de,
    pavio_sup_de,
)

from hunter_core.strategies.aggregate import Bar  # noqa: E402
from hunter_core.strategies.indicators import CONTEXT  # noqa: E402

VERSAO = "padroes_kb0080_v1"

AMP_ATR = Decimal("0.8")
CORPO_PEQUENO = Decimal("0.35")
PAVIO_X_CORPO = Decimal("2")
SOMBRA_CURTA = Decimal("0.1")
DOJI_CORPO = Decimal("0.1")
DOJI_AMP_ATR = Decimal("0.5")
MARUBOZU_CORPO_ATR = Decimal("1.0")
ENGOLFO_CORPO_ATR = Decimal("0.5")
HARAMI_MAE_ATR = Decimal("1.0")
HARAMI_FILHA = Decimal("0.5")
ESTRELA_CORPO2 = Decimal("0.3")
ESTRELA_CORPO3_ATR = Decimal("0.5")
ESTRELA_MEIO = Decimal("0.5")
SOLDADO_CORPO_ATR = Decimal("0.5")
SOLDADO_SOMBRA = Decimal("0.2")
EMA_N = 10
EMA_INCLINACAO = 3

NOMES: tuple[str, ...] = (
    "a_martelo",
    "a_enforcado",
    "a_estrela_cadente",
    "a_martelo_invertido",
    "a_doji_alta",
    "a_doji_baixa",
    "a_marubozu_alta",
    "a_marubozu_baixa",
    "a_engolfo_alta",
    "a_engolfo_baixa",
    "a_harami_alta",
    "a_harami_baixa",
    "a_estrela_manha",
    "a_estrela_noite",
    "a_tres_soldados",
    "a_tres_corvos",
    "a_tres_dentro_alta",
    "a_tres_dentro_baixa",
)

DIRECAO: dict[str, str] = {
    nome: (
        "short" if nome.endswith(("baixa", "cadente", "enforcado", "corvos", "noite")) else "long"
    )
    for nome in NOMES
}
SINAL: dict[str, int] = {n: (-1 if DIRECAO[n] == "short" else 1) for n in NOMES}


def ema10(bars: list[Bar]) -> list[Decimal | None]:
    """EMA de ``EMA_N`` fechamentos, semeada na média simples do índice ``EMA_N - 1``."""
    saida: list[Decimal | None] = [None] * len(bars)
    if len(bars) < EMA_N:
        return saida
    with localcontext(CONTEXT):
        alfa = Decimal(2) / Decimal(EMA_N + 1)
        atual = sum((b.close for b in bars[:EMA_N]), Decimal(0)) / Decimal(EMA_N)
        saida[EMA_N - 1] = atual
        for k in range(EMA_N, len(bars)):
            atual = bars[k].close * alfa + atual * (Decimal(1) - alfa)
            saida[k] = atual
    return saida


def contexto(bars: list[Bar], ema: list[Decimal | None], t0: int) -> str | None:
    """`baixa` / `alta` / `lateral` na barra anterior a ``t0`` (régua de Marshall)."""
    ancora = t0 - 1
    antes = ancora - EMA_INCLINACAO
    if antes < 0:
        return None
    atual, passado = ema[ancora], ema[antes]
    if atual is None or passado is None:
        return None
    fechamento = bars[ancora].close
    if fechamento < atual and atual < passado:
        return "baixa"
    if fechamento > atual and atual > passado:
        return "alta"
    return "lateral"


def detectar(
    bars: list[Bar], atr: list[Decimal | None], ema: list[Decimal | None], i: int
) -> list[Deteccao]:
    """Padrões da KB-0080 §7 cuja última barra é ``i``, no fechamento de ``i``."""
    achados: list[Deteccao] = []
    b0 = bars[i]
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

    def regua(n: int) -> Decimal | None:
        if i - n < 0:
            return None
        valor = atr[i - n]
        return valor if valor is not None and valor > 0 else None

    # ---- uma barra ------------------------------------------------------
    escala = regua(1)
    amp0 = faixa_de(b0)
    if escala is not None and amp0 > 0:
        corpo0, sup0, inf0 = corpo_de(b0), pavio_sup_de(b0), pavio_inf_de(b0)
        ctx = contexto(bars, ema, i)
        martelo = (
            amp0 >= AMP_ATR * escala
            and corpo0 <= CORPO_PEQUENO * amp0
            and inf0 >= PAVIO_X_CORPO * corpo0
            and sup0 <= SOMBRA_CURTA * amp0
        )
        estrela = (
            amp0 >= AMP_ATR * escala
            and corpo0 <= CORPO_PEQUENO * amp0
            and sup0 >= PAVIO_X_CORPO * corpo0
            and inf0 <= SOMBRA_CURTA * amp0
        )
        if martelo and ctx == "baixa":
            add("a_martelo", 1, b0.low, escala)
        if martelo and ctx == "alta":
            add("a_enforcado", 1, b0.high, escala)
        if estrela and ctx == "alta":
            add("a_estrela_cadente", 1, b0.high, escala)
        if estrela and ctx == "baixa":
            add("a_martelo_invertido", 1, b0.low, escala)
        if corpo0 <= DOJI_CORPO * amp0 and amp0 >= DOJI_AMP_ATR * escala:
            if ctx == "baixa":
                add("a_doji_alta", 1, b0.low, escala)
            elif ctx == "alta":
                add("a_doji_baixa", 1, b0.high, escala)
        if (
            corpo0 >= MARUBOZU_CORPO_ATR * escala
            and sup0 <= SOMBRA_CURTA * amp0
            and inf0 <= SOMBRA_CURTA * amp0
        ):
            if e_alta(b0):
                add("a_marubozu_alta", 1, b0.open, escala)
            elif e_baixa(b0):
                add("a_marubozu_baixa", 1, b0.open, escala)

    # ---- duas barras ----------------------------------------------------
    escala = regua(2)
    if escala is not None and i >= 2:
        b1 = bars[i - 1]
        amp1, corpo1, corpo0 = faixa_de(b1), corpo_de(b1), corpo_de(b0)
        if amp0 > 0 and amp1 > 0:
            ctx = contexto(bars, ema, i - 1)
            if (
                ctx == "baixa"
                and e_baixa(b1)
                and e_alta(b0)
                and b0.open <= b1.close
                and b0.close >= b1.open
                and (b0.open < b1.close or b0.close > b1.open)
                and corpo0 > corpo1
                and corpo0 >= ENGOLFO_CORPO_ATR * escala
            ):
                add("a_engolfo_alta", 2, min(b0.low, b1.low), escala)
            if (
                ctx == "alta"
                and e_alta(b1)
                and e_baixa(b0)
                and b0.open >= b1.close
                and b0.close <= b1.open
                and (b0.open > b1.close or b0.close < b1.open)
                and corpo0 > corpo1
                and corpo0 >= ENGOLFO_CORPO_ATR * escala
            ):
                add("a_engolfo_baixa", 2, max(b0.high, b1.high), escala)
            if _harami(b1, b0, corpo1, corpo0, escala, "baixa") and ctx == "baixa":
                add("a_harami_alta", 2, b1.low, escala)
            if _harami(b1, b0, corpo1, corpo0, escala, "alta") and ctx == "alta":
                add("a_harami_baixa", 2, b1.high, escala)

    # ---- três barras ----------------------------------------------------
    escala = regua(3)
    if escala is not None and i >= 3:
        b1, b2 = bars[i - 1], bars[i - 2]
        corpo0, corpo1, corpo2 = corpo_de(b0), corpo_de(b1), corpo_de(b2)
        amp1, amp2 = faixa_de(b1), faixa_de(b2)
        if amp0 > 0 and amp1 > 0 and amp2 > 0:
            ctx = contexto(bars, ema, i - 2)
            grande = corpo2 >= HARAMI_MAE_ATR * escala
            if (
                ctx == "baixa"
                and grande
                and e_baixa(b2)
                and corpo1 <= ESTRELA_CORPO2 * corpo2
                and max(b1.open, b1.close) <= b2.close
                and e_alta(b0)
                and corpo0 >= ESTRELA_CORPO3_ATR * escala
                and b0.close >= b2.close + ESTRELA_MEIO * corpo2
            ):
                add("a_estrela_manha", 3, min(b0.low, b1.low, b2.low), escala)
            if (
                ctx == "alta"
                and grande
                and e_alta(b2)
                and corpo1 <= ESTRELA_CORPO2 * corpo2
                and min(b1.open, b1.close) >= b2.close
                and e_baixa(b0)
                and corpo0 >= ESTRELA_CORPO3_ATR * escala
                and b0.close <= b2.close - ESTRELA_MEIO * corpo2
            ):
                add("a_estrela_noite", 3, max(b0.high, b1.high, b2.high), escala)

            corpos = (corpo2, corpo1, corpo0)
            trio = (b2, b1, b0)
            corpo_ok = all(c >= SOLDADO_CORPO_ATR * escala for c in corpos)
            if (
                ctx == "baixa"
                and corpo_ok
                and all(e_alta(b) for b in trio)
                and b0.close > b1.close > b2.close
                and b2.open <= b1.open <= b2.close
                and b1.open <= b0.open <= b1.close
                and all(pavio_sup_de(b) <= SOLDADO_SOMBRA * faixa_de(b) for b in trio)
            ):
                add("a_tres_soldados", 3, b2.low, escala)
            if (
                ctx == "alta"
                and corpo_ok
                and all(e_baixa(b) for b in trio)
                and b0.close < b1.close < b2.close
                and b2.close <= b1.open <= b2.open
                and b1.close <= b0.open <= b1.open
                and all(pavio_inf_de(b) <= SOLDADO_SOMBRA * faixa_de(b) for b in trio)
            ):
                add("a_tres_corvos", 3, b2.high, escala)

            if (
                ctx == "baixa"
                and _harami(b2, b1, corpo2, corpo1, escala, "baixa")
                and e_alta(b0)
                and b0.close > b2.open
            ):
                add("a_tres_dentro_alta", 3, min(b0.low, b1.low, b2.low), escala)
            if (
                ctx == "alta"
                and _harami(b2, b1, corpo2, corpo1, escala, "alta")
                and e_baixa(b0)
                and b0.close < b2.open
            ):
                add("a_tres_dentro_baixa", 3, max(b0.high, b1.high, b2.high), escala)

    return achados


def _harami(
    mae: Bar, filha: Bar, corpo_mae: Decimal, corpo_filha: Decimal, escala: Decimal, lado: str
) -> bool:
    """Corpo da filha **estritamente** dentro do corpo da mãe; cor da filha livre."""
    if corpo_mae < HARAMI_MAE_ATR * escala or corpo_filha > HARAMI_FILHA * corpo_mae:
        return False
    alto, baixo = max(filha.open, filha.close), min(filha.open, filha.close)
    if lado == "baixa":
        return e_baixa(mae) and alto < mae.open and baixo > mae.close
    return e_alta(mae) and alto < mae.close and baixo > mae.open


def varrer(bars: list[Bar], atr: list[Decimal | None]) -> list[Deteccao]:
    ema = ema10(bars)
    return [d for i in range(len(bars)) for d in detectar(bars, atr, ema, i)]
