"""h036 — instrumento de custo: o que uma ida-e-volta custaria na Binance USDⓈ-M nos instantes do Lab.

Medido por trade, em R do Lab (unidade U = entry_c − stop, a mesma do lab-cost-sweep), a partir do que o banco guarda:

* spread cotado: ``market_snapshots`` (1 linha por minuto e mercado; bid/ask do último ``bookTicker`` lido do hot state
  na virada do minuto, anulado se o ticker tem > 10 s). Entrada: o minuto ``entry_ts`` (o Lab entra na abertura dessa
  vela). Saída: o minuto ``exit_bar_open`` (a vela onde a saída aconteceu);
* taxa: tabela pública da Binance USDⓈ-M, nível VIP 0 sem desconto de BNB — taker 5 bp, maker 2 bp por perna
  (suposição declarada; não lida de conta nenhuma);
* preenchimento passivo: velas 1 m ``is_final`` depois da entrada (só atravessar o bid conta; tocar não, por causa da
  fila).

Custo de uma perna (fração do preço): taker = taxa + meio spread; maker = taxa (sem spread). Em R:
``cost_r = (c_in·O + c_out·B) / U``. Régua de decisão: custo efetivo ponderado ``2·Σcost_r / Σh × 1e4`` (bp) com
``h = (O + B)/U`` — o mesmo ``Σ h·k / Σ h`` de ``sweep.effective_cost_bp`` com ``k_i = 2·cost_r_i/h_i × 1e4``.

O que NÃO mede (limites, ditos no relatório): impacto além do topo do livro (quantidades do topo e profundidade não
são persistidas), deslizamento do stop-mercado dentro do minuto, latência entre a abertura e a ordem, e o spread
dentro do minuto (a amostra é a da virada). Estatística em float; nenhum dinheiro é publicado.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

import numpy as np

BP = 1e-4
TAKER = 5 * BP
MAKER = 2 * BP


@dataclass(frozen=True, slots=True)
class Legs:
    """O que o instrumento precisa de um trade (preços em unidade de preço; spreads em fração do mid)."""

    open: float  # O: abertura limpa (sem custo) da vela de entrada
    base: float  # B: base da saída sem custo (o que o Lab creditou)
    risk: float  # U: unidade de risco gravada pelo Lab
    result: str  # stop | target | expired | invalidated
    exit_at_open: bool
    exit_high: float | None  # máxima da vela de saída (só saídas dentro da vela)
    target1: float  # preço da venda limite no alvo (o chamador já o põe no grid: limit_at_or_above)
    sp_in: float  # spread na entrada (já com o fallback aplicado)
    sp_out: float  # spread na saída (já com o fallback aplicado)
    bid_in: float | None  # bid no minuto da entrada (None = não observado)
    entry_lows: tuple[float | None, ...]  # mínimas das velas entry, entry+1, entry+2


def cost_r(*, open_: float, base: float, risk: float, c_in: float, c_out: float) -> float:
    """Custo das duas pernas em R do Lab: cada perna cobrada sobre o próprio preço."""
    return (c_in * open_ + c_out * base) / risk


def taker_taker(legs: Legs, *, fee: float = TAKER) -> tuple[float, float]:
    """Ordem a mercado nas duas pernas: taxa taker + meio spread em cada uma."""
    return fee + legs.sp_in / 2, fee + legs.sp_out / 2


def _target_rests(legs: Legs, *, strict: bool) -> bool:
    """A venda limite no alvo executa? Dentro da vela, ``strict`` exige que a máxima tenha passado do limite no grid
    (tocar pode não executar — fila); máxima desconhecida conta como não executada. Saída na abertura: o Lab testa a
    abertura contra o alvo original, não contra o limite no grid, e a abertura da vela de saída não está no instrumento
    — ``strict`` cobra taker (Astra H-036, must-fix 5); o modo de toque aceita como maker."""
    if legs.result != "target":
        return False
    if legs.exit_at_open:
        return not strict
    if legs.exit_high is None:
        return False
    return legs.exit_high > legs.target1 if strict else legs.exit_high >= legs.target1


def taker_in_resting_tp(legs: Legs, *, strict: bool, taker: float = TAKER, maker: float = MAKER
                        ) -> tuple[float, float]:
    """Entrada a mercado; alvo como venda limite em repouso (maker, sem spread); stop/expiração/invalidação a mercado.

    Um alvo que só tocou (``strict``) é cobrado como taker — limite conservador: o caminho alternativo (a posição
    seguir aberta) não é observável sem as velas seguintes."""
    c_in = taker + legs.sp_in / 2
    c_out = maker if _target_rests(legs, strict=strict) else taker + legs.sp_out / 2
    return c_in, c_out


def passive_fill(*, bid: float | None, lows: Sequence[float | None], minutes: int) -> bool | None:
    """Uma compra limite no bid do minuto da entrada executa em ``minutes`` velas? Só atravessar conta (low < bid).

    ``None`` quando o bid ou alguma vela necessária falta antes de uma execução provada (desconhecido, nunca não)."""
    if bid is None:
        return None
    for low in lows[:minutes]:
        if low is None:
            return None
        if low < bid:
            return True
    return False if len(lows) >= minutes else None


def passive_entry_cost(*, bid: float, open_: float, maker: float = MAKER) -> float:
    """Custo da entrada passiva contra a abertura O: taxa maker + (bid − O)/O (negativo = melhora de preço)."""
    return maker + (bid - open_) / open_


def pick_spread(at_minute: float | None, neighbours: Sequence[float | None], *, market_median: float | None,
                cohort_p90: float) -> tuple[float, str]:
    """Spread de uma perna, com a ordem de substituição congelada: minuto → vizinho (±1 min) → mediana do mercado na
    coorte → p90 da coorte (conservador). Devolve o valor e a origem, para publicar a cobertura."""
    if at_minute is not None:
        return at_minute, "minuto"
    for value in neighbours:
        if value is not None:
            return value, "vizinho"
    if market_median is not None:
        return market_median, "mediana_mercado"
    return cohort_p90, "p90_coorte"


def tick_of(prices: Sequence[str]) -> float:
    """Passo de preço estimado: a casa decimal mais fina entre os preços impressos (zeros à direita descartados).

    Subestima a precisão quando os preços vistos terminam em zero — passo maior, limite mais alto, mais alvos
    contados como "só tocou": erra para o lado conservador."""
    places = 0
    for p in prices:
        if p:
            frac = Decimal(p).normalize().as_tuple().exponent
            places = max(places, -int(frac))
    return float(Decimal(1).scaleb(-places))


def limit_at_or_above(price: float, tick: float) -> float:
    """O preço de uma venda limite no alvo: o primeiro passo do grid em ou acima dele."""
    steps = Decimal(repr(price)) / Decimal(repr(tick))
    return float(steps.to_integral_value(rounding=ROUND_CEILING) * Decimal(repr(tick)))


def passive_signal_r(net: np.ndarray, filled: np.ndarray) -> np.ndarray:
    """R por SINAL da entrada passiva: executado leva o R líquido do trade; não executado é trade que não houve (0)."""
    return np.where(filled, net, 0.0)


def effective_cost_bp(cost_rs: np.ndarray, h: np.ndarray) -> float:
    """Custo efetivo de ida-e-volta (bp) que entra no R médio: Σh·k/Σh = 2·Σcost_r/Σh × 1e4."""
    return float(2.0 * np.sum(cost_rs) / np.sum(h) / BP)


def net_r(gross: np.ndarray, funding_r: np.ndarray, cost_rs: np.ndarray) -> np.ndarray:
    """R líquido ao custo medido: bruto − funding − custo (todos na unidade U do Lab)."""
    return gross - funding_r - cost_rs
