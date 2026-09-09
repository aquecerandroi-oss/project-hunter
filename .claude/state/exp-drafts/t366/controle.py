"""T3.66 / EXP-0024 — a dobra de 15 min, o sinal lag-1 e os planos dos controles.

**Não há um segundo caminho de saída.** Tudo aqui termina chamando
``hunter_strategy_worker.walker.walk`` e ``hunter_strategy_worker.pricing.r_net``
— o mesmo código congelado que decidiu e liquidou as decisões da população. Este
módulo só monta os dois pontos que o walker lê do mundo (o plano e as velas) e a
regra de sinal do controle. Uma reimplementação das regras de saída teria
liberdade para discordar da população que ela tenta explicar, que é exatamente o
erro que este experimento existe para não cometer.

Contratos congelados em `EXP-0024-controle-contrarian.md`:

* a barra "anterior" é ``[b − 15 min, b)`` — a própria barra que a estratégia de
  15 min leu, a última **fechada antes da entrada** (a entrada abre em ``b + 1 min``);
* balde de 15 min só existe com **15 velas de 1 min ``is_final``** contíguas;
* ``sign(close − open)``; ``close == open`` é **doji** e não dispara;
* geometria do controle: ``risco_pct`` e a razão alvo:risco ``tr`` **da decisão
  pareada**, aplicadas ao ``P_entry`` da barra do controle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hunter_core.strategies.envelope import AssumedCosts
from hunter_strategy_worker.pricing import entry_price, exit_price, r_net
from hunter_strategy_worker.progress import Bar, Progress, TrackingPlan
from hunter_strategy_worker.walker import walk

__all__ = [
    "BARRA",
    "CUSTOS",
    "Serie",
    "Barra15",
    "caminhar",
    "plano_do_controle",
    "sinal",
]

BARRA = timedelta(minutes=15)
MINUTO = timedelta(minutes=1)

CUSTOS = AssumedCosts(spread_bps="2", slippage_bps="5", fee_bps="4", max_entry_delay_s=120)
"""Os custos assumidos das quatro versões (20 bps ida e volta). Lidos do catálogo
(`t366-q00`), não inventados: as quatro têm ``spread 2 / slippage 5 / fee 4``."""


@dataclass(frozen=True)
class Barra15:
    """Um balde de 15 min completo. ``fecha_em`` é o instante do fechamento."""

    fecha_em: datetime
    abertura: float
    fechamento: float


def sinal(barra: Barra15) -> int:
    """``-1`` baixa, ``+1`` alta, ``0`` doji. O controle só compra em ``-1``."""
    if barra.fechamento < barra.abertura:
        return -1
    if barra.fechamento > barra.abertura:
        return 1
    return 0


class Serie:
    """As velas de 1 min de **um** mercado, indexadas por minuto.

    Guarda preços em ``float`` para varrer barato e constrói ``Decimal`` só nas
    janelas que realmente vão ser caminhadas — 1,2 milhão de ``Bar`` com quatro
    ``Decimal`` cada não cabe em memória e não seria mais exato onde importa
    (a prova disso é a validação da população: o R recomputado tem de bater com
    o persistido).
    """

    __slots__ = ("_por_minuto", "_minutos")

    def __init__(self) -> None:
        self._por_minuto: dict[datetime, tuple[float, float, float, float]] = {}
        self._minutos: set[datetime] = set()

    def adicionar(self, t: datetime, o: float, h: float, l: float, c: float) -> None:  # noqa: E741
        self._por_minuto[t] = (o, h, l, c)
        self._minutos.add(t)

    def __len__(self) -> int:
        return len(self._por_minuto)

    def minutos(self) -> set[datetime]:
        return self._minutos

    def vela(self, t: datetime) -> tuple[float, float, float, float] | None:
        return self._por_minuto.get(t)

    def balde15(self, fecha_em: datetime) -> Barra15 | None:
        """O balde ``[fecha_em − 15 min, fecha_em)``, ou ``None`` se incompleto.

        Incompleto **nunca** é preenchido: um minuto ausente é ausência de sinal,
        não um sinal neutro.
        """
        inicio = fecha_em - BARRA
        primeira = self._por_minuto.get(inicio)
        ultima = self._por_minuto.get(fecha_em - MINUTO)
        if primeira is None or ultima is None:
            return None
        for k in range(1, 14):
            if (inicio + timedelta(minutes=k)) not in self._por_minuto:
                return None
        return Barra15(fecha_em=fecha_em, abertura=primeira[0], fechamento=ultima[3])

    def janela(self, inicio: datetime, minutos: int) -> list[Bar] | None:
        """``minutos`` velas contíguas a partir de ``inicio``, como ``Bar``.

        ``None`` se faltar qualquer minuto — o acompanhamento seria **censurado**,
        e um acompanhamento censurado não vira número.
        """
        saida: list[Bar] = []
        t = inicio
        for _ in range(minutos):
            v = self._por_minuto.get(t)
            if v is None:
                return None
            saida.append(
                Bar(
                    open_time=t,
                    open=Decimal(repr(v[0])),
                    high=Decimal(repr(v[1])),
                    low=Decimal(repr(v[2])),
                    close=Decimal(repr(v[3])),
                )
            )
            t += MINUTO
        return saida


def plano_do_controle(
    *,
    entrada: datetime,
    abertura: Decimal,
    risco_pct: Decimal,
    tr: Decimal,
    horizonte_s: int,
    custos: AssumedCosts = CUSTOS,
) -> TrackingPlan:
    """O plano do controle: mesma convenção de entrada, geometria **relativa** da decisão.

    ``risco_pct = risco_decisão / P_entry_decisão`` e ``tr = (alvo1 − P_entry) / risco``
    — as duas quantidades que fazem "mesmo stop e mesmo alvo" sobreviver a um preço
    diferente, e que mantêm idêntica a identidade de pedágio ``custo_R = 0,0020 / risco_pct``
    ([[KB-0076]]) nos dois lados da comparação.
    """
    p_entry = entry_price(abertura, custos)
    risco = p_entry * risco_pct
    return TrackingPlan(
        entry_bar_open=entrada,
        stop=p_entry - risco,
        target1=p_entry + tr * risco,
        horizon_s=horizonte_s,
        costs=custos,
    )


def caminhar(plano: TrackingPlan, velas: list[Bar]) -> Progress:
    """``walker.walk`` sobre um acompanhamento novo. Sem estado, sem IO."""
    return walk(plano, Progress.start(), velas)


def r_sem_funding(plano: TrackingPlan, progresso: Progress) -> Decimal | None:
    """O R a 20 bps, sem perna de funding — a mesma aritmética de ``settle.settle``."""
    if progresso.exit_base is None or progresso.entry is None:
        return None
    return r_net(
        entry=progresso.entry,
        exit_=exit_price(progresso.exit_base, plano.costs),
        stop=plano.stop,
        costs=plano.costs,
        funding_per_unit=Decimal(0),
    )


def utc(texto: str) -> datetime:
    """``2026-09-08T20:00:00Z`` → ``datetime`` ciente de fuso, em UTC."""
    return datetime.strptime(texto, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
