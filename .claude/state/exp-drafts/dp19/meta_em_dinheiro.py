"""D-P19 — a meta de R$ 9.000/dia em DINHEIRO, por mercado e por hora.

Rascunho de pesquisa (fora de produção). Aritmética pura em `Decimal`, sem
rede, sem banco, sem relógio: tudo entra como argumento — a mesma disciplina de
`hunter_risk.evaluate` (`docs/ARCHITECTURE.md` §6). O IO (ler os CSV do dump da
VPS, escrever os CSV derivados) vive em `roda.py`.

**Nenhum limite é redigitado aqui.** `PAPER_V1` (`packages/risk-core`) é a fonte
dos tetos e `round_trip_cost_fraction` é a mesma função que `size_entry` chama;
`CUSTO_RT_LAB` é essa função aplicada à hipótese de custo que o Lab carimba em
`signal_outcomes.meta.assumed_costs` (fee 4 bps, spread 2 bps, slippage 5 bps)
= 0,0020.

**Duas medianas, duas convenções — declaradas:**

* a mediana das 30 barras da referência de participação (`docs/RISK_ENGINE.md`
  §4, "Janela da referência de volume") é **interpolada**, como o
  `percentile_cont(0.5)` que a T3.60 usou no banco;
* os p10/p50/p90 da distribuição por hora são **nearest-rank**, como o
  `percentile` do T3.78 — o cliente consegue recontar à mão.

**Dois R diferentes, nunca somados:**

* o R do Lab (`signal_outcomes.r_multiple`) tem denominador `|entrada - stop|`
  **sem** custo, então o dinheiro de 1 R é `notional x d_stop` (notes-T3.60 §2);
* o R do motor (a perda planejada do `risk_per_trade_pct`) tem denominador
  `d_stop + custo`, e é ele que dimensiona o teto de risco.

`valor_de_1r_usdt` usa o primeiro; `caps_do_motor` usa o segundo.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, localcontext

from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.numeric import CONTEXT
from hunter_risk.limits import PAPER_V1
from hunter_risk.sizing import round_trip_cost_fraction

__all__ = [
    "CAP_ORDER",
    "CUSTO_RT_LAB",
    "PARTICIPACOES",
    "Caps",
    "Cenario",
    "brl",
    "caps_do_motor",
    "dinheiro_por_dia",
    "impacto_raiz_quadrada",
    "mediana_interpolada",
    "percentil_nearest_rank",
    "referencias_de_volume",
    "valor_de_1r_usdt",
]

_CUSTOS_DO_LAB = AssumedCosts.model_validate(
    {"fee_bps": "4", "spread_bps": "2", "slippage_bps": "5", "max_entry_delay_s": "120"}
)
CUSTO_RT_LAB: Decimal = round_trip_cost_fraction(_CUSTOS_DO_LAB)
"""0,0020 — a hipótese de custo carimbada em cada desfecho, pela função do motor."""

PARTICIPACOES: tuple[Decimal, ...] = (Decimal("0.01"), Decimal("0.02"), Decimal("0.05"))
"""1 % é o `max_participation_pct` do `paper_v1`; 2 % e 5 % são SENSIBILIDADE
(5 % é o `participation_cap` do sentinel-trader-research, hipótese de cenário do
autor, não medição). Nada aqui altera `limits.py`."""

CAP_ORDER: tuple[str, ...] = (
    "requested",
    "risk_per_trade",
    "aggregate_risk",
    "market_participation",
    "book_depth",
    "asset_exposure",
    "total_exposure",
    "beta_exposure",
    "cash",
)
"""A ordem de desempate do contrato (`docs/RISK_ENGINE.md` §4, `tied_limits`)."""


# --------------------------------------------------------------- percentis


def mediana_interpolada(valores: Sequence[Decimal]) -> Decimal:
    """`percentile_cont(0.5)`: com n par, a média dos dois centrais."""
    if not valores:
        raise ValueError("mediana de população vazia é indefinida")
    ordenados = sorted(valores)
    n = len(ordenados)
    meio = n // 2
    if n % 2 == 1:
        return ordenados[meio]
    with localcontext(CONTEXT):
        return (ordenados[meio - 1] + ordenados[meio]) / Decimal(2)


def percentil_nearest_rank(valores: Sequence[Decimal], q: Decimal) -> Decimal:
    """`rank = ceil(q x n)`, preso em [1, n] — a convenção do T3.78."""
    if not valores:
        raise ValueError("percentil de população vazia é indefinido")
    ordenados = sorted(valores)
    n = len(ordenados)
    rank = max(1, min(n, math.ceil(q * n)))
    return ordenados[rank - 1]


# ------------------------------------------- referência de volume (§4)


def referencias_de_volume(
    serie: Sequence[tuple[int, Decimal]], *, janela: int = 30
) -> list[tuple[int, Decimal]]:
    """`min(último minuto completo, mediana das janela barras completas)`.

    `serie` é `(minuto, quote_volume)` ordenada, com o minuto como inteiro
    (índice absoluto, não posição na lista). Uma janela que não tenha as
    `janela` barras **contíguas** não produz referência — barra ausente é
    indisponibilidade, nunca zero e nunca mediana de janela reduzida
    (`docs/RISK_ENGINE.md` §4).
    """
    saida: list[tuple[int, Decimal]] = []
    for i in range(janela - 1, len(serie)):
        bloco = serie[i - janela + 1 : i + 1]
        if bloco[-1][0] - bloco[0][0] != janela - 1:
            continue  # buraco: a janela não é contígua
        minuto, ultimo = bloco[-1]
        saida.append((minuto, min(ultimo, mediana_interpolada([v for _, v in bloco]))))
    return saida


# ------------------------------------------------------------ tetos


@dataclass(frozen=True, slots=True)
class Caps:
    notional: Decimal
    binding: str
    valores: dict[str, Decimal]
    empatados: tuple[str, ...] = field(default=())


def caps_do_motor(
    *,
    equity_usdt: Decimal,
    d_stop: Decimal,
    referencia_volume: Decimal | None,
    participacao: Decimal,
) -> Caps:
    """Os tetos de tamanho de UMA entrada numa carteira vazia, em notional.

    Cobre os tetos que dependem só do mercado e do patrimônio:
    `risk_per_trade`, `market_participation`, `asset_exposure`,
    `total_exposure` e `cash`. **Fora**: `aggregate_risk`, `book_depth` e
    `beta_exposure` — são estado de carteira/livro, e omiti-los só faz o número
    ser um **teto superior** (a mesma declaração da T3.78 CONCERN 2 e da T3.60
    §9.2).
    """
    if referencia_volume is None:
        raise ValueError("referência de volume ausente não vira zero (§4)")
    if d_stop <= 0:
        raise ValueError("distância de stop tem de ser positiva")
    with localcontext(CONTEXT):
        d_efetiva = d_stop + CUSTO_RT_LAB
        valores = {
            "risk_per_trade": equity_usdt * PAPER_V1.risk_per_trade_pct / d_efetiva,
            "market_participation": referencia_volume * participacao,
            "asset_exposure": equity_usdt * PAPER_V1.max_asset_exposure_pct,
            "total_exposure": equity_usdt * PAPER_V1.max_total_exposure_pct,
            "cash": equity_usdt,
        }
        menor = min(valores.values())
        vencedor = next(n for n in CAP_ORDER if n in valores and valores[n] == menor)
        empatados = tuple(
            n for n in CAP_ORDER if n in valores and valores[n] == menor and n != vencedor
        )
    return Caps(notional=menor, binding=vencedor, valores=valores, empatados=empatados)


# --------------------------------------------------- dinheiro


def valor_de_1r_usdt(notional: Decimal, d_stop: Decimal) -> Decimal:
    """`notional x d_stop` — a identidade da T3.60 §2 para o R do Lab."""
    if d_stop <= 0:
        raise ValueError("distância de stop tem de ser positiva")
    with localcontext(CONTEXT):
        return notional * d_stop


def brl(valor_usdt: Decimal, cambio: Decimal) -> Decimal:
    """Uma observação de `fx_observations.rate`, nunca uma taxa adivinhada."""
    with localcontext(CONTEXT):
        return valor_usdt * cambio


def dinheiro_por_dia(
    apostas_por_dia: Decimal, valor_1r_brl: Decimal, r_por_aposta: Decimal
) -> Decimal:
    """`N x 1R x R medio` — a forma da Astra, por mercado, somada fora daqui."""
    with localcontext(CONTEXT):
        return apostas_por_dia * valor_1r_brl * r_por_aposta


def impacto_raiz_quadrada(notional: Decimal, adv: Decimal, k: Decimal) -> Decimal:
    """SENSIBILIDADE, não medição: `k*sqrt(notional/ADV)`, o modelo escrito no
    `sentinel/carry/capacity.py` do sentinel-trader-research.

    O `k` **não é nosso** e o próprio autor não publica o valor calibrado; a
    Astra registrou que os coeficientes de custo dele não fecham como
    decomposição aditiva. Entra como coluna rotulada, com `k` varrido numa
    grade declarada, e nunca substitui o `max_slippage_pct` do perfil.
    """
    if adv <= 0:
        raise ValueError("ADV tem de ser positivo")
    with localcontext(CONTEXT):
        return k * (notional / adv).sqrt()


@dataclass(frozen=True, slots=True)
class Cenario:
    """Teto e esperado lado a lado — nunca um no lugar do outro."""

    nome: str
    apostas_por_dia: Decimal
    valor_1r_brl: Decimal
    r_por_aposta: Decimal

    @property
    def teto_brl_dia(self) -> Decimal:
        """O máximo que os limites permitem: toda aposta fechando +1 R.
        NÃO é lucro esperado — é capacidade."""
        return dinheiro_por_dia(self.apostas_por_dia, self.valor_1r_brl, Decimal(1))

    @property
    def esperado_brl_dia(self) -> Decimal:
        """O dinheiro com o R medido da família."""
        return dinheiro_por_dia(self.apostas_por_dia, self.valor_1r_brl, self.r_por_aposta)
