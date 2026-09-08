"""Como uma linha do banco vira um ``Outcome`` do protocolo — T3.18c, item 2.

Separado de ``repositories/lab_replication.py`` pelo orçamento de 350 linhas e
porque esta metade é a que um teste quer isolada: uma consulta em ordem total,
o **mesmo** portão de avaliabilidade do placar e a junção que conta cada
decisão uma vez. Sem sessão, sem orquestração.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from hunter_api.repositories.lab_summary import OutcomeRow
from hunter_api.services.lab_summary_metrics import is_evaluable
from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState
from hunter_core.domain.types import ensure_utc
from hunter_indicators.replication import Outcome, dedupe_outcomes

if TYPE_CHECKING:
    from sqlalchemy import Row, Select
    from sqlalchemy.sql import ColumnElement

__all__ = [
    "EMPTY_WINDOW",
    "ReplayWindow",
    "dedupe",
    "outcome_of",
    "outcome_rows_stmt",
]

dedupe = dedupe_outcomes
"""Contar cada (mercado, decisão) uma vez é regra do protocolo, não deste
serviço: mora em :func:`hunter_indicators.replication.dedupe_outcomes`, pura, e
o worker usa a **mesma** função (T3.18c, item 3)."""

OutcomeRowShape = tuple[
    ShadowTrackingState,
    OutcomeResult,
    datetime | None,
    datetime | None,
    Decimal | None,
    dict[str, Any],
    datetime,
    uuid.UUID,
    str,
    str,
]


@dataclass(frozen=True, slots=True)
class ReplayWindow:
    """A janela coberta pelos replays de **uma** versão, ``as_of`` respeitado."""

    window_from: datetime | None
    window_to: datetime | None

    @property
    def declared(self) -> bool:
        return self.window_from is not None and self.window_to is not None


EMPTY_WINDOW = ReplayWindow(None, None)


def outcome_rows_stmt(
    version_id: uuid.UUID, *, as_of: datetime, cohort_condition: ColumnElement[bool]
) -> Select[OutcomeRowShape]:
    """As linhas candidatas de uma versão sob uma coorte, em ordem estável.

    ``ORDER BY (emitted_at, id)`` e não só ``emitted_at`` (T3.18c, item 5): o
    bootstrap reamostra **por índice**, e uma população com empates de
    ``emitted_at`` — o replay produz empates por construção
    (``replay/environment.py``) — devolvida em ordem diferente pelo Postgres
    mede um intervalo diferente com a mesma semente. Empate desempatado por
    ``id`` é uma ordem total.
    """
    return (
        select(
            SignalOutcome.tracking_state,
            SignalOutcome.result,
            SignalOutcome.entry_ts,
            SignalOutcome.exit_ts,
            SignalOutcome.r_multiple,
            SignalOutcome.meta,
            AgentSignal.emitted_at,
            AgentSignal.market_id,
            Exchange.code,
            Market.symbol,
        )
        .join(AgentSignal, AgentSignal.id == SignalOutcome.signal_id)
        .join(Market, Market.id == AgentSignal.market_id)
        .join(Exchange, Exchange.id == Market.exchange_id)
        .where(
            AgentSignal.strategy_version_id == version_id,
            AgentSignal.emitted_at <= as_of,
            cohort_condition,
        )
        .order_by(AgentSignal.emitted_at, AgentSignal.id)
    )


def outcome_of(row: Row[OutcomeRowShape], as_of: datetime) -> Outcome | None:
    """``None`` quando a linha **não é avaliável pela régua do placar**.

    O portão é literalmente ``lab_summary_metrics.is_evaluable`` — terminal,
    ``exit_ts <= as_of`` e horizonte (``entry_bar_open + horizon_s``)
    transcorrido —, mais ``r_multiple`` conhecido. Uma segunda cópia da regra
    aqui é o que permitia ao mesmo JSON publicar dois vereditos (Astra,
    2026-09-08, HIGH); por isso esta função **chama** a do placar em vez de
    reescrevê-la.
    """
    candidate = OutcomeRow(
        tracking_state=row.tracking_state,
        result=row.result,
        no_entry_reason=None,
        censored_reason=None,
        entry_ts=None if row.entry_ts is None else ensure_utc(row.entry_ts),
        exit_ts=None if row.exit_ts is None else ensure_utc(row.exit_ts),
        r_multiple=row.r_multiple,
        meta=row.meta,
        market_id=row.market_id,
        decision_at=ensure_utc(row.emitted_at),
    )
    if not is_evaluable(candidate, as_of) or candidate.r_multiple is None:
        return None
    return Outcome(
        r=candidate.r_multiple,
        decision_at=candidate.decision_at,
        market=f"{row.code}:{row.symbol}",
        # ``is_evaluable`` já garantiu ``exit_ts`` não nulo — o ``cast`` diz
        # isso ao type checker em vez de um ramo que nunca roda.
        exit_at=cast("datetime", candidate.exit_ts),
    )
