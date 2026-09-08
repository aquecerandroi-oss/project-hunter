"""``ScoreboardRowOut.replication`` reads — briefs T3.18b (item 2) and T3.18c.

An adapter, not a second implementation: every number the replication
protocol needs comes out of
:mod:`hunter_indicators.replication` (pure, no IO — ``replication_report``),
this module only loads its inputs (``Outcome``/``SiblingArm`` populations,
``promising_at``, the registered seed) the way
``hunter_strategy_worker.replication_stats`` does for the worker side,
adapted to this service's own ``AsyncSession`` (that module lives in
``services/strategy-worker``, a different deployable, and this API does not
depend on it — ``notes-T3.19.md`` §1 names this exact fallback).

**Uma definição de "avaliável", e é a do placar** (T3.18c, item 2). Este
módulo carrega as mesmas linhas que ``repositories/lab_scoreboard.rows_for``
carrega e aplica **a mesma função**
``services.lab_summary_metrics.is_evaluable`` — terminal, ``exit_ts <=
as_of`` e horizonte (``entry_bar_open + horizon_s``) já transcorrido —, e só
então constrói ``Outcome``. Enquanto exigia apenas "emitido até ``as_of``,
terminal e R conhecido", o mesmo JSON conseguia publicar ``verdict:
reprovada`` ao lado de ``parent.verdict: inconclusivo`` (Astra, 2026-09-08,
HIGH), e uma leitura histórica contava um desfecho ocorrido **depois** do
corte.

Três desvios deliberados de ``replication_stats.load_outcomes``, todos
exigidos por D15 (``.claude/state/decisions-delegated-2026-09-08.md``):

1. **A população do pai é filtrada por coorte ``prospective``.** Uma consulta
   sem filtro deixaria barras de replay entrarem no bloco fora-da-amostra, na
   partição por metades, no bootstrap e no próprio ``parent`` verdict —
   exatamente o que D15 (b) proíbe.
2. **As irmãs são achadas pelas colunas da ``0012``**
   (``replication_parent_id``/``replication_index``), nunca pelo
   ``changelog`` — toda irmã que esta API enxerga nasceu depois da migração.
3. **A evidência de cada irmã é contada uma vez** (T3.18c, item 3): a mesma
   decisão replayada sob dois ``run_id`` é *uma* decisão, e a coorte viva tem
   precedência sobre qualquer replay que cubra a mesma (mercado, decisão).

A *maturidade* de uma irmã, por D15 (a), pode misturar a coorte viva dela
(``replication:<pai>:<k>`` **e** ``prospective``, quando a irmã foi promovida)
com replay histórico — rotulada por ``evidence`` na saída
(``schemas/lab_replication.py``) e com a janela do replay ao lado.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import func, select

from hunter_api.repositories.lab_common import COHORT
from hunter_api.repositories.lab_replication_rows import (
    EMPTY_WINDOW,
    ReplayWindow,
    dedupe,
    outcome_of,
    outcome_rows_stmt,
)
from hunter_core.db.models.agents import StrategyVersion
from hunter_core.db.models.replay_runs import ReplayRunRow
from hunter_core.db.models.system import SystemEvent
from hunter_core.domain.enums import ShadowCohort
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement

    from hunter_indicators.replication import Outcome

__all__ = [
    "EMPTY_WINDOW",
    "REPLICATION_COMPONENT",
    "REPLICATION_EVENT",
    "SEED_SOURCE_DERIVED",
    "SEED_SOURCE_REGISTERED",
    "LabReplicationRepository",
    "ReplayWindow",
    "SiblingMeta",
    "SiblingPopulation",
]

REPLICATION_COMPONENT = "replicate_strategy_version"
"""``system_events.component`` do CLI de replicação
(``hunter_strategy_worker.replication.COMPONENT``)."""

REPLICATION_EVENT = "strategy_version_replicated"
"""O evento que registra a rodada — e a **semente** dela.

A semente sai daqui, e não de um ``seed=<n>`` dentro do ``changelog`` da irmã
(T3.18c, item 6): o evento é escrito pelo mesmo commit que criou as irmãs, com
a semente em campo próprio; o ``changelog`` é texto livre onde um número pode
ser reescrito por quem editar a linha e onde uma expressão regular acha
qualquer coisa parecida.
"""

Evidence = Literal["prospective", "replay", "mixed"]

SEED_SOURCE_REGISTERED = "registrada"
SEED_SOURCE_DERIVED = "derivada_do_id"


@dataclass(frozen=True, slots=True)
class SiblingMeta:
    """Uma linha de ``strategy_versions`` que nomeia uma irmã (só colunas da
    ``0012_replication`` — ver docstring do módulo, desvio 2)."""

    id: uuid.UUID
    version: str
    k: int
    changelog: str | None


@dataclass(frozen=True, slots=True)
class SiblingPopulation:
    """A população de uma irmã, com a origem declarada (D15) e sem repetição."""

    meta: SiblingMeta
    outcomes: list[Outcome]
    evidence: Evidence | None
    """``None`` enquanto a irmã não produziu nenhum resultado avaliável."""
    replay_window: ReplayWindow = EMPTY_WINDOW
    """A janela dos replays **desta** irmã — nula quando ela não tem replay."""
    duplicates_dropped: int = 0
    """Quantos resultados de replay foram descartados por repetirem uma
    (mercado, decisão) que a coorte viva — ou outro replay — já trazia.

    Publicado, e não silenciado, porque é a diferença entre "25 resultados" e
    "50 resultados" numa irmã replayada duas vezes: quem lê o bloco precisa
    saber que o número menor é o correto.
    """


class LabReplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def promising_at(self, version_id: uuid.UUID) -> datetime | None:
        stamped = await self.session.scalar(
            select(StrategyVersion.promising_at).where(StrategyVersion.id == version_id)
        )
        return None if stamped is None else ensure_utc(stamped)

    async def registered_seed(self, version_id: uuid.UUID) -> int | None:
        """A semente da rodada, lida do evento que a registrou.

        ``None`` quando nenhuma rodada foi registrada — aí quem chama declara
        que derivou a semente (``seed_source``), em vez de apresentar um número
        como se alguém o tivesse escolhido.
        """
        raw = await self.session.scalar(
            select(SystemEvent.data["seed"].astext)
            .where(
                SystemEvent.component == REPLICATION_COMPONENT,
                SystemEvent.event == REPLICATION_EVENT,
                SystemEvent.data["strategy_version_id"].astext == str(version_id),
            )
            .order_by(SystemEvent.created_at)
            .limit(1)
        )
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    async def siblings(self, parent_id: uuid.UUID) -> list[SiblingMeta]:
        rows = (
            await self.session.execute(
                select(
                    StrategyVersion.id,
                    StrategyVersion.version,
                    StrategyVersion.replication_index,
                    StrategyVersion.changelog,
                )
                .where(StrategyVersion.replication_parent_id == parent_id)
                .order_by(StrategyVersion.replication_index)
            )
        ).all()
        return [
            SiblingMeta(
                id=row.id, version=row.version, k=row.replication_index, changelog=row.changelog
            )
            for row in rows
            if row.replication_index is not None
        ]

    async def replay_windows(
        self, version_ids: list[uuid.UUID], *, as_of: datetime
    ) -> dict[uuid.UUID, ReplayWindow]:
        """A janela de replay de cada versão, **respeitando o corte**.

        ``finished_at <= as_of`` (T3.18c, item 7): um recibo de corrida que
        terminou depois do corte descreve trabalho que, na leitura pedida,
        ainda não tinha acontecido.
        """
        if not version_ids:
            return {}
        rows = (
            await self.session.execute(
                select(
                    ReplayRunRow.strategy_version_id,
                    func.min(ReplayRunRow.window_from),
                    func.max(ReplayRunRow.window_to),
                )
                .where(
                    ReplayRunRow.strategy_version_id.in_(version_ids),
                    ReplayRunRow.finished_at <= as_of,
                )
                .group_by(ReplayRunRow.strategy_version_id)
            )
        ).all()
        return {
            row[0]: ReplayWindow(
                window_from=None if row[1] is None else ensure_utc(row[1]),
                window_to=None if row[2] is None else ensure_utc(row[2]),
            )
            for row in rows
        }

    async def _outcomes(
        self, version_id: uuid.UUID, *, as_of: datetime, cohort_condition: ColumnElement[bool]
    ) -> list[Outcome]:
        stmt = outcome_rows_stmt(version_id, as_of=as_of, cohort_condition=cohort_condition)
        rows = (await self.session.execute(stmt)).all()
        return [outcome for outcome in (outcome_of(row, as_of) for row in rows) if outcome]

    async def parent_outcomes(self, version_id: uuid.UUID, *, as_of: datetime) -> list[Outcome]:
        """A população avaliável do pai — ``prospective`` e só ela (D15 b)."""
        return await self._outcomes(
            version_id, as_of=as_of, cohort_condition=(COHORT == ShadowCohort.PROSPECTIVE)
        )

    async def sibling_population(
        self,
        sibling: SiblingMeta,
        parent_id: uuid.UUID,
        *,
        as_of: datetime,
        replay_window: ReplayWindow = EMPTY_WINDOW,
    ) -> SiblingPopulation:
        """A população de uma irmã: viva primeiro, replay depois, sem repetir.

        "Viva" são **duas** coortes: o braço (``replication:<pai>:<k>``) e
        ``prospective``, que é o que uma irmã promovida a linha viva passa a
        carimbar (T3.18, item 13) — ignorá-la apagava a evidência mais forte
        que a irmã tem.
        """
        arm_cohort = ShadowCohort.replication(parent_id, sibling.k)
        live = await self._outcomes(
            sibling.id,
            as_of=as_of,
            cohort_condition=COHORT.in_([arm_cohort, ShadowCohort.PROSPECTIVE]),
        )
        replay = await self._outcomes(
            sibling.id, as_of=as_of, cohort_condition=COHORT.like(f"{ShadowCohort.REPLAY_PREFIX}%")
        )
        outcomes, (live_kept, replay_kept), dropped = dedupe([live, replay])
        evidence: Evidence | None
        if live_kept and replay_kept:
            evidence = "mixed"
        elif replay_kept:
            evidence = "replay"
        elif live_kept:
            evidence = "prospective"
        else:
            evidence = None
        return SiblingPopulation(
            meta=sibling,
            outcomes=outcomes,
            evidence=evidence,
            replay_window=replay_window if replay_kept else EMPTY_WINDOW,
            duplicates_dropped=dropped,
        )
