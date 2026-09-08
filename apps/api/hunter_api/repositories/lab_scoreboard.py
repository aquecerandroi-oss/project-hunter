"""``GET /api/v1/lab/shadow/{scoreboard,curve}`` reads — T3.18.

Global, no-RLS reads, same as every other Shadow Lab repository (DATABASE.md
§16): Shadow Lab tables carry no ``organization_id`` and no RLS policy by
design — research is shared across the product, never per-tenant. Reuses
``OutcomeRow`` from ``repositories/lab_summary.py`` verbatim rather than
declaring a parallel shape.

Population freeze uses ``agent_signals.emitted_at`` directly (the brief's
``as_of`` rule), not the ``supporting_features->>'decision_at'`` JSONB
expression ``lab_summary``/``lab_signals`` use: ``persist.py`` always writes
``emitted_at=record.decision_at`` (``services/strategy-worker/hunter_strategy_worker/persist.py:65``),
so the two are numerically identical for every row that exists, and the
native column has an index (``ix_agent_signals_version_emitted``) the JSONB
expression does not.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from hunter_api.repositories.lab_common import COHORT
from hunter_api.repositories.lab_summary import OutcomeRow
from hunter_core.db.models.agents import AgentSignal, SignalOutcome, Strategy, StrategyVersion
from hunter_core.db.models.replay_runs import ReplayRunRow
from hunter_core.domain.enums import ShadowCohort, StrategyVersionStatus
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement

__all__ = [
    "REPLAY_COHORT_WILDCARD",
    "ReplayRunWindow",
    "ReplayRunsSummary",
    "ScoreboardVersionMeta",
    "LabScoreboardRepository",
]

REPLAY_COHORT_WILDCARD = "replay"
"""Not a real cohort (``ShadowCohort.is_valid`` refuses it): a caller-facing
shorthand for "every ``replay:<uuid>`` cohort of this version", used by both
the scoreboard's replay block (brief T3.18b, item 1) and ``GET .../curve``
(item 3) so the two never define "all replay evidence" two different ways.
"""


def _cohort_condition(cohort: str) -> ColumnElement[bool]:
    """``cohort`` as a ``WHERE`` condition against the JSONB envelope's own
    ``cohort`` field: the wildcard becomes a prefix match, anything else
    (``prospective``, one exact ``replay:<uuid>``, one
    ``replication:<parent>:<k>``) is an exact match.
    """
    if cohort == REPLAY_COHORT_WILDCARD:
        return COHORT.like(f"{ShadowCohort.REPLAY_PREFIX}%")
    return COHORT == cohort


@dataclass(frozen=True, slots=True)
class ReplayRunWindow:
    """Uma corrida de replay e a janela que as fatias dela cobriram."""

    run_id: uuid.UUID
    window_from: datetime
    window_to: datetime


@dataclass(frozen=True, slots=True)
class ReplayRunsSummary:
    """The ``replay_runs`` receipts of one version, summed across every run
    (brief T3.18b, item 1) — never per slice, since a slice is not the unit the
    scoreboard reports (DATABASE.md §25.1).

    **Ponto no tempo** (T3.18c, item 7): só recibos com ``finished_at <=
    as_of``. Uma leitura histórica que mostrasse a massa de corridas
    posteriores ao corte descreveria trabalho que, naquele instante, ainda não
    tinha acontecido.
    """

    runs: int
    """Count of *distinct* ``run_id`` values — the number of times a replay
    was launched for this version, not the number of slices it took."""
    bars_evaluated: int
    """Sum of every slice's ``bars_evaluated`` — barras varridas, incluindo as
    que a estratégia não conseguiu avaliar."""
    evaluations_by_state: dict[str, int]
    """Soma dos mapas de cada fatia: ``triggered``, ``not_triggered``,
    ``rejected``, ``unavailable``, ``ineligible``. É o que torna a massa
    honesta (T3.18c, item 9): sem ele, "500 mil por dia" era medido contra
    barras, e uma barra em warm-up ou de mercado inelegível não é uma decisão.
    """
    window_from: datetime | None
    window_to: datetime | None
    windows: list[ReplayRunWindow]
    """Uma linha por corrida — o que permite recusar a soma de corridas com
    janelas sobrepostas na curva (T3.18c, item 10)."""


@dataclass(frozen=True, slots=True)
class ScoreboardVersionMeta:
    id: uuid.UUID
    strategy_key: str
    version: str
    purpose: str
    status: StrategyVersionStatus
    code_ref: str | None
    activated_at: datetime | None


class LabScoreboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def versions_with_signals(self, as_of: datetime) -> list[ScoreboardVersionMeta]:
        """One row per version that has **emitted at least one signal** by
        ``as_of`` — active, deprecated and draft-with-signals alike (brief
        T3.18, item 1). Deliberately not ``activated_at IS NOT NULL``
        (``lab_summary.LabSummaryRepository.activated_versions``): a version
        with zero signals within the frozen population would show an
        all-zero card that adds nothing, and "ever emitted" is the population
        the rest of this module actually measures.
        """
        rows = (
            await self.session.execute(
                select(StrategyVersion, Strategy.key)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .where(
                    StrategyVersion.id.in_(
                        select(AgentSignal.strategy_version_id)
                        .where(
                            AgentSignal.emitted_at <= as_of,
                            COHORT == ShadowCohort.PROSPECTIVE,
                        )
                        .distinct()
                    )
                )
                .order_by(Strategy.key, StrategyVersion.version)
            )
        ).all()
        return [
            ScoreboardVersionMeta(
                id=sv.id,
                strategy_key=key,
                version=sv.version,
                purpose=sv.purpose,
                status=sv.status,
                code_ref=sv.code_ref,
                activated_at=sv.activated_at,
            )
            for sv, key in rows
        ]

    async def rows_for(
        self, version_id: uuid.UUID, as_of: datetime, *, cohort: str = ShadowCohort.PROSPECTIVE
    ) -> list[OutcomeRow]:
        """Every outcome row emitted by ``version_id`` at or before ``as_of``
        under ``cohort`` — shared by the scoreboard's prospective and replay
        blocks and by the curve (brief T3.18b, items 1 and 3) so no two of
        them can disagree on what a given cohort's population is.
        ``cohort`` is ``"prospective"`` (default), one exact cohort string
        (``"replay:<uuid>"``, ``"replication:<parent>:<k>"``) or the
        ``"replay"`` wildcard (:data:`REPLAY_COHORT_WILDCARD`) meaning every
        replay run of this version at once.
        """
        stmt = (
            select(
                SignalOutcome.tracking_state,
                SignalOutcome.result,
                SignalOutcome.no_entry_reason,
                SignalOutcome.censored_reason,
                SignalOutcome.entry_ts,
                SignalOutcome.exit_ts,
                SignalOutcome.r_multiple,
                SignalOutcome.meta,
                AgentSignal.market_id,
                AgentSignal.emitted_at,
            )
            .join(AgentSignal, AgentSignal.id == SignalOutcome.signal_id)
            .where(
                AgentSignal.strategy_version_id == version_id,
                AgentSignal.emitted_at <= as_of,
                _cohort_condition(cohort),
            )
            .order_by(AgentSignal.emitted_at, AgentSignal.id)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            OutcomeRow(
                tracking_state=r.tracking_state,
                result=r.result,
                no_entry_reason=r.no_entry_reason,
                censored_reason=r.censored_reason,
                entry_ts=r.entry_ts,
                exit_ts=r.exit_ts,
                r_multiple=r.r_multiple,
                meta=r.meta,
                market_id=r.market_id,
                decision_at=r.emitted_at,
            )
            for r in rows
        ]

    async def replay_runs_summary(
        self, version_id: uuid.UUID, *, as_of: datetime
    ) -> ReplayRunsSummary:
        """Os recibos de ``replay_runs`` desta versão até ``as_of``, agregados.

        Uma consulta, agregação em Python: as fatias por versão são dezenas
        (a corrida-prova da T3.19b teve onze), e o mesmo SELECT entrega a massa
        (``bars_evaluated``), os estados de avaliação (``evaluations_by_state``,
        que o SQL somaria com um ``jsonb_each`` bem mais caro de ler) e a janela
        **por corrida**, que a curva precisa para recusar sobreposição.

        ``runs == 0`` é como quem chama sabe que não há evidência de replay
        alguma — uma versão replayada e ainda sem recibo continua mostrando as
        ``operations_closed`` das linhas de outcome, com estes contadores em
        zero, nunca um erro.
        """
        rows = (
            await self.session.execute(
                select(
                    ReplayRunRow.run_id,
                    ReplayRunRow.bars_evaluated,
                    ReplayRunRow.evaluations_by_state,
                    ReplayRunRow.window_from,
                    ReplayRunRow.window_to,
                )
                .where(
                    ReplayRunRow.strategy_version_id == version_id,
                    ReplayRunRow.finished_at <= as_of,
                )
                .order_by(ReplayRunRow.window_from, ReplayRunRow.run_id)
            )
        ).all()
        bars = 0
        states: dict[str, int] = {}
        spans: dict[uuid.UUID, tuple[datetime, datetime]] = {}
        for row in rows:
            bars += int(row.bars_evaluated)
            recorded: dict[str, int] = row.evaluations_by_state or {}
            for state, count in recorded.items():
                states[state] = states.get(state, 0) + int(count)
            start, end = ensure_utc(row.window_from), ensure_utc(row.window_to)
            known = spans.get(row.run_id)
            spans[row.run_id] = (
                (start, end) if known is None else (min(known[0], start), max(known[1], end))
            )
        windows = sorted(
            (ReplayRunWindow(run_id, start, end) for run_id, (start, end) in spans.items()),
            key=lambda item: (item.window_from, item.window_to),
        )
        return ReplayRunsSummary(
            runs=len(spans),
            bars_evaluated=bars,
            evaluations_by_state=states,
            window_from=windows[0].window_from if windows else None,
            window_to=max((item.window_to for item in windows), default=None),
            windows=windows,
        )
