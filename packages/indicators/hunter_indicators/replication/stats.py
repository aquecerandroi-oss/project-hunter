"""População avaliável, maturidade e o veredito do placar — as definições que o
resto do protocolo reusa (`docs/plans/REPLICATION.md` §1 e §2).

Um nome por conta, com o denominador junto (item 9 da decisão conjunta e a regra
5 do plantão): *expectancy líquida hipotética em R por entrada encerrada
avaliável* não é *taxa de lucro líquido*, e *profit factor* é **nulo com motivo**
quando um dos lados do quociente é vazio — nunca infinito, nunca zero inventado.

Só ``Decimal`` aqui: são os R que a tela mostra e que o placar persiste. A
estatística em ``float`` mora em :mod:`~hunter_indicators.replication.bootstrap`,
e a fronteira entre as duas é explícita de propósito.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

__all__ = [
    "EXPECTANCY_MIN",
    "MATURITY_DAYS",
    "MATURITY_HALF_DAYS",
    "MATURITY_HALF_OUTCOMES",
    "MATURITY_OUTCOMES",
    "PF_NO_LOSSES",
    "PF_NO_SAMPLE",
    "PROFIT_FACTOR_MIN",
    "VERDICT_INCONCLUSIVE",
    "VERDICT_REJECTED",
    "VERDICT_VALIDATED",
    "Outcome",
    "PopulationStats",
    "after",
    "dedupe_outcomes",
    "profit_factor_passes",
    "scoreboard_verdict",
]

MATURITY_OUTCOMES = 100
"""``MATURIDADE_RESULTADOS`` — régua cheia do placar (SHADOW-LAB.md §9)."""

MATURITY_DAYS = 30
"""``MATURIDADE_DIAS`` — régua cheia do placar."""

MATURITY_HALF_OUTCOMES = 50
"""``MATURIDADE_META_RESULTADOS`` — meia-régua dos blocos 1 e 2 (REPLICATION.md §1.5)."""

MATURITY_HALF_DAYS = 15
"""``MATURIDADE_META_DIAS`` — meia-régua dos blocos 1 e 2."""

EXPECTANCY_MIN = Decimal("0")
"""Desigualdade **estrita**: empate não passa."""

PROFIT_FACTOR_MIN = Decimal("1")
"""Idem."""

PF_NO_LOSSES = "sem_perdas"
"""O **único** motivo de um profit factor nulo (SHADOW-LAB.md item 9)."""

PF_NO_SAMPLE = "sem_amostra"
"""População vazia: não há quociente e não há veredito."""

VERDICT_INCONCLUSIVE = "inconclusivo"
VERDICT_VALIDATED = "validada"
VERDICT_REJECTED = "reprovada"

_FOUR = Decimal("0.0001")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_FOUR, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Outcome:
    """Um resultado **avaliável**: R líquido, decisão, saída e mercado.

    Quem constrói esta lista já aplicou o **mesmo** portão de avaliabilidade do
    placar (``hunter_api.services.lab_summary_metrics.is_evaluable``:
    ``tracking_state = 'terminal'``, ``exit_ts <= as_of``, horizonte
    ``entry_bar_open + horizon_s`` já transcorrido em ``as_of`` e ``r_multiple``
    conhecido); aqui dentro não existe outcome pendente, sem entrada, censurado
    ou com horizonte aberto — o que entra conta.

    ``exit_at`` não tem padrão, de propósito (T3.18c, item 2): a régua de
    maturidade conta **dias de saída**, e um construtor que pudesse esquecer o
    instante da saída reintroduziria a segunda definição de "avaliável" que este
    contrato existe para apagar.
    """

    r: Decimal
    decision_at: datetime
    market: str
    exit_at: datetime

    @property
    def decision_day(self) -> date:
        """Dia UTC da **decisão** (``agent_signals.emitted_at``).

        É o dia que agrupa o bootstrap por blocos (§3.4): a dependência entre
        resultados nasce de decisões simultâneas sobre mercados correlacionados,
        não do instante em que cada uma foi encerrada.
        """
        return self.decision_at.date()

    @property
    def exit_day(self) -> date:
        """Dia UTC da **saída** — o dia que a régua de maturidade conta.

        É a definição do placar (``lab_scoreboard.py``: ``maturity.days`` =
        ``{exit_ts.date()}``), e ela é a que vale: "30 dias distintos" é
        evidência **encerrada** acumulada, não decisões espalhadas por 30 dias
        cujos desfechos ainda não existem.
        """
        return self.exit_at.date()


@dataclass(frozen=True, slots=True)
class PopulationStats:
    """As contas de uma população avaliável, todas com denominador declarado.

    **Um contrato só** com o placar (T3.18c, item 2): ``evaluable`` conta a mesma
    população que ``ScoreboardRowOut.evaluable``, ``days`` conta os mesmos dias
    de **saída** que ``ScoreboardRowOut.maturity.days``, e ``profit_factor``
    segue a mesma regra de nulo com motivo — só ``sem_perdas`` é nulo
    (``SHADOW-LAB.md``, "Placar (T3.18)"; item 9 da decisão conjunta). Duas
    definições de "avaliável" publicariam dois vereditos sobre a mesma evidência,
    que foi exatamente o defeito que esta versão fechou.
    """

    evaluable: int
    days: int
    """Dias **de saída** distintos (``Outcome.exit_day``)."""
    markets: int
    expectancy_r: Decimal | None
    profit_factor: Decimal | None
    """Σ ganhos / |Σ perdas|. **Zero** quando não houve um único ganho (o
    quociente existe e vale 0, com ``profit_factor_reason`` nulo); ``None``
    **apenas** quando não houve perda alguma."""
    profit_factor_reason: str | None
    """``sem_amostra`` (população vazia) ou ``sem_perdas``. Nunca
    ``sem_ganhos``: 0 dividido por uma perda real é 0, não é indefinido, e
    inventar um nulo aí faria o mesmo PF ser publicado como ``0.0000`` no placar
    e como ``null`` na replicação."""
    sum_r: Decimal | None
    wins: int
    losses: int

    @classmethod
    def of(cls, outcomes: Iterable[Outcome]) -> PopulationStats:
        rows = list(outcomes)
        if not rows:
            return cls(0, 0, 0, None, None, PF_NO_SAMPLE, None, 0, 0)
        values = [row.r for row in rows]
        gains = sum((value for value in values if value > 0), Decimal(0))
        drops = sum((value for value in values if value < 0), Decimal(0))
        wins = sum(1 for value in values if value > 0)
        losses = sum(1 for value in values if value < 0)
        total = sum(values, Decimal(0))
        if losses == 0:
            factor, reason = None, PF_NO_LOSSES
        else:
            factor, reason = _quantize(gains / -drops), None
        return cls(
            evaluable=len(rows),
            days=len({row.exit_day for row in rows}),
            markets=len({row.market for row in rows}),
            expectancy_r=_quantize(total / len(rows)),
            profit_factor=factor,
            profit_factor_reason=reason,
            sum_r=_quantize(total),
            wins=wins,
            losses=losses,
        )

    def mature(self, *, outcomes: int = MATURITY_OUTCOMES, days: int = MATURITY_DAYS) -> bool:
        """Régua **E**, nunca **OU**: 300 resultados em 3 dias não é maturidade."""
        return self.evaluable >= outcomes and self.days >= days

    def positive(self) -> bool:
        return self.expectancy_r is not None and self.expectancy_r > EXPECTANCY_MIN

    def shortfall(self, *, outcomes: int, days: int) -> str:
        """ "38 de 50 resultados · 9 de 15 dias" — o que falta, sempre visível."""
        return f"{self.evaluable} de {outcomes} resultados · {self.days} de {days} dias"

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "evaluable": self.evaluable,
            "days": self.days,
            "markets": self.markets,
            "expectancy_r": None if self.expectancy_r is None else str(self.expectancy_r),
            "profit_factor": None if self.profit_factor is None else str(self.profit_factor),
            "profit_factor_reason": self.profit_factor_reason,
            "sum_r": None if self.sum_r is None else str(self.sum_r),
            "wins": self.wins,
            "losses": self.losses,
        }


def dedupe_outcomes(
    streams: Sequence[Sequence[Outcome]],
) -> tuple[list[Outcome], list[int], int]:
    """Junta populações contando cada ``(mercado, decisão)`` **uma vez**.

    A ordem das correntes é a precedência: a primeira lista ganha os empates, e
    é sempre a viva — uma irmã promovida a linha viva não perde a evidência
    prospectiva dela porque um replay cobriu os mesmos minutos (T3.18c, itens 3
    e 13).

    Devolve a população, quantos sobraram de cada corrente (o rótulo de origem
    descreve o que **restou**, não o que foi lido) e quantos foram descartados.

    O caso que isto fecha: 25 resultados replayados sob dois ``run_id`` entravam
    como 50 e atingiam a meia-régua sem uma única informação nova (Astra,
    2026-09-08, HIGH). Sete irmãs assim aprovavam o bloco 2 sozinhas.

    Puro de propósito: a mesma função serve a API (``lab_replication``) e o
    worker (``replication_stats``), que não podem se importar um ao outro.
    """
    seen: set[tuple[str, datetime]] = set()
    kept: list[Outcome] = []
    counts = [0 for _ in streams]
    dropped = 0
    for index, stream in enumerate(streams):
        for outcome in stream:
            key = (outcome.market, outcome.decision_at)
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            kept.append(outcome)
            counts[index] += 1
    return kept, counts, dropped


def profit_factor_passes(stats: PopulationStats) -> bool:
    """``profit_factor > 1``, ou nulo por ``sem_perdas`` — nada mais.

    ``sem_amostra`` não passa (não há o que aprovar) e um PF numérico ``<= 1``
    não passa: a desigualdade é estrita (§2).
    """
    if stats.profit_factor is not None:
        return stats.profit_factor > PROFIT_FACTOR_MIN
    return stats.profit_factor_reason == PF_NO_LOSSES


def scoreboard_verdict(stats: PopulationStats) -> str:
    """O veredito do placar (T3.18), **a mesma regra**, aqui como função pura.

    ``inconclusivo`` enquanto imaturo; depois ``validada`` sse
    ``expectancy_r > 0`` **e** o profit factor passa. "Passa" é o contrato do
    placar (``lab_scoreboard_metrics.compute_verdict``, ``SHADOW-LAB.md``
    "Placar (T3.18)"): ``profit_factor > 1``, **ou** nulo por ``sem_perdas`` —
    um lado perdedor vazio não pode reprovar uma versão madura e positiva.
    Enquanto esta função recusava o nulo, a mesma população era ``validada`` no
    placar e ``reprovada`` na replicação (Astra, 2026-09-08, MEDIUM).
    """
    if not stats.mature():
        return VERDICT_INCONCLUSIVE
    if not stats.positive():
        return VERDICT_REJECTED
    if not profit_factor_passes(stats):
        return VERDICT_REJECTED
    return VERDICT_VALIDATED


def after(outcomes: Sequence[Outcome], moment: datetime) -> list[Outcome]:
    """Só o que foi decidido **depois** de ``moment`` — a fronteira do bloco 1.

    Estritamente maior: a decisão que aconteceu no mesmo instante em que a versão
    virou promissora ainda pertence à amostra que a tornou promissora.
    """
    return [outcome for outcome in outcomes if outcome.decision_at > moment]
