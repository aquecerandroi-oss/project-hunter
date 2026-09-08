"""O que o protocolo de replicação lê do banco (`docs/plans/REPLICATION.md`).

Só leitura e só tradução: as contas moram em
:mod:`hunter_indicators.replication`, que é puro e testável com séries
sintéticas. Aqui ficam as três consultas que o protocolo precisa —

1. a população **avaliável** de uma versão, sob a coorte pedida e com o
   **mesmo** portão do placar (T3.18c, itens 1 e 2): ``tracking_state =
   'terminal'``, ``r_multiple IS NOT NULL``, ``exit_ts <= as_of`` e horizonte
   (``entry_bar_open + horizon_s``) já transcorrido. A tradução em SQL de
   ``hunter_api.services.lab_summary_metrics.is_evaluable``, linha por linha;
2. as irmãs de um pai, reconhecidas por ``replication_parent_id`` desde a
   ``0012_replication`` (e ainda pelo rótulo ``replication:<pai>:<k>`` no
   ``changelog``, para as derivadas antes dela);
3. o ``promising_at``, lido da **coluna** desde a ``0012_replication`` e, na
   falta dela, do ``changelog`` das irmãs e de ``system_events`` (retenção de
   30 dias — por isso nunca foi a fonte primária).

**Chave de mercado.** As metades do bloco 3 são partidas por
``<exchange>:<symbol>``, não só pelo símbolo: o mesmo ``BTCUSDT`` em duas
corretoras é mercado diferente, e uma partição que os confunde partiria a
população pelo lugar errado.

**Coorte, e por que ela é obrigatória aqui (T3.18c, item 1).** Esta consulta
nasceu antes do motor de replay e não filtrava coorte nenhuma. Depois que uma
versão passou a poder ser replayada sob o próprio ``strategy_version_id``
(``replay:<uuid>``, T3.19b), a CLI de replicação — que decide se o pai é
promissor e **carimba ``promising_at``** — podia ser convencida por um replay:
prospectivo pequeno e negativo, replay grande e positivo, e a rodada era aceita
sem ``--force-research``, congelando o marco de onde o bloco 1 conta. O pai é
lido **só** em ``prospective`` (D15 b); as irmãs podem contar replay (D15 a),
uma vez cada (``dedupe_outcomes``).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.enums import ShadowCohort
from hunter_core.domain.types import ensure_utc
from hunter_indicators.replication import (
    Outcome,
    SiblingArm,
    dedupe_outcomes,
    replication_report,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection
    from sqlalchemy.sql.elements import TextClause

    from hunter_indicators.replication import ReplicationReport

__all__ = [
    "ARM_RE",
    "PROMISING_EVENT",
    "REPLICATION_PREFIX",
    "SiblingRow",
    "arm_label",
    "build_report",
    "data_of",
    "load_outcomes",
    "load_promising_at",
    "load_sibling_outcomes",
    "load_sibling_rows",
    "parse_promising_at",
    "summarise",
]

REPLICATION_PREFIX = "replication:"
"""Prefixo do rótulo do braço — e, desde a ``0012_replication``, também o
prefixo da coorte de ``shadow_episodes`` (``replication:<pai>:<k>``, ``k`` de 1
a 99). A pendência da REPLICATION.md §4.4 está fechada: o rótulo que vivia só no
``changelog`` é uma coorte que o banco aceita e duas colunas
(``replication_parent_id``, ``replication_index``) que ele garante."""

PROMISING_EVENT = "strategy_version_promising"

ARM_RE = re.compile(
    r"^replication:(?P<parent>[0-9a-fA-F-]{36}):(?P<k>\d+)\b",
)
_PROMISING_RE = re.compile(r"promising_at=(?P<ts>[0-9T:\-\.+Z]+)")

_EVALUABLE_SQL = (
    "SELECT s.emitted_at, s.id, o.r_multiple, o.exit_ts, e.code AS exchange, m.symbol "
    "FROM agent_signals s "
    "JOIN signal_outcomes o ON o.signal_id = s.id "
    "JOIN markets m ON m.id = s.market_id "
    "JOIN exchanges e ON e.id = m.exchange_id "
    "WHERE s.strategy_version_id = :version_id "
    "AND o.tracking_state = 'terminal' AND o.r_multiple IS NOT NULL "
    "AND s.emitted_at <= coalesce(CAST(:as_of AS timestamptz), now()) "
    "AND o.exit_ts IS NOT NULL "
    "AND o.exit_ts <= coalesce(CAST(:as_of AS timestamptz), now()) "
    "AND (o.meta -> 'entry_plan' ->> 'entry_bar_open') IS NOT NULL "
    "AND (o.meta ->> 'horizon_s') IS NOT NULL "
    "AND (CAST(o.meta -> 'entry_plan' ->> 'entry_bar_open' AS timestamptz) "
    "     + make_interval(secs => CAST(o.meta ->> 'horizon_s' AS double precision))) "
    "    <= coalesce(CAST(:as_of AS timestamptz), now()) "
)
"""O portão de avaliabilidade do placar, em SQL.

Três exigências além de "terminal com R conhecido", e cada uma responde a um
jeito de enviesar a população: ``exit_ts <= as_of`` impede uma leitura
histórica de contar um desfecho posterior ao corte; o horizonte transcorrido
impede que saídas rápidas entrem antes das operações que ainda estão abertas; e
a ausência de ``entry_plan``/``horizon_s`` (uma linha que este worker não
escreveu) **exclui**, em vez de passar por falta de informação.
"""

_ORDER = " ORDER BY s.emitted_at, s.id"
"""Ordem total (T3.18c, item 5): o bootstrap reamostra por índice, e o replay
produz empates de ``emitted_at`` por construção."""

_COHORT = "(s.supporting_features ->> 'cohort')"

_OUTCOMES_PROSPECTIVE_SQL = text(
    _EVALUABLE_SQL + f"AND {_COHORT} = '{ShadowCohort.PROSPECTIVE}'" + _ORDER
)
_OUTCOMES_LIVE_SQL = text(
    _EVALUABLE_SQL + f"AND {_COHORT} IN (:arm, '{ShadowCohort.PROSPECTIVE}')" + _ORDER
)
"""A população **viva** de uma irmã: o braço dela e ``prospective``.

``prospective`` está aí porque uma irmã promovida a linha viva passa a carimbar
essa coorte, e ignorá-la apagava justamente a evidência mais forte que ela tem
(quant, revisão T3.18b, achado 13).
"""
_OUTCOMES_REPLAY_SQL = text(
    _EVALUABLE_SQL + f"AND {_COHORT} LIKE '{ShadowCohort.REPLAY_PREFIX}%'" + _ORDER
)

_SIBLINGS_SQL = text(
    "SELECT v.id, v.version, v.changelog, v.status, v.purpose, v.replication_index "
    "FROM strategy_versions v "
    "WHERE v.replication_parent_id = CAST(:parent AS uuid) "
    "OR v.changelog LIKE :prefix || :parent || ':%' "
    "ORDER BY v.version"
)
"""A irmã é reconhecida pela **coluna** (``0012_replication``) e, ainda, pelo
rótulo no ``changelog``: as duas condições, não uma. A coluna é a verdade; o
``LIKE`` continua aqui porque uma irmã derivada antes da migração só tem o
rótulo, e trocar a consulta por uma delas sozinha faria dessa irmã ou uma órfã
(só coluna) ou uma linha que nenhuma constraint protege (só rótulo)."""

_PROMISING_COLUMN_SQL = text(
    "SELECT promising_at FROM strategy_versions WHERE id = CAST(:parent AS uuid)"
)

_PROMISING_SQL = text(
    "SELECT data ->> 'promising_at' AS promising_at FROM system_events "
    "WHERE event = :event AND data ->> 'strategy_version_id' = :parent "
    "ORDER BY created_at LIMIT 1"
)


def arm_label(parent_id: uuid.UUID, k: int) -> str:
    """``replication:<parent_version_id>:<k>`` — o nome do braço, k de 1 a N."""
    return f"{REPLICATION_PREFIX}{parent_id}:{k}"


@dataclass(frozen=True, slots=True)
class SiblingRow:
    """Uma irmã como o banco a guarda, com o braço que ela ocupa."""

    id: uuid.UUID
    version: str
    k: int
    """O braço. Vem de ``replication_index`` quando a coluna está preenchida e do
    rótulo do ``changelog`` quando não — nunca de uma contagem de linhas."""
    changelog: str
    status: str
    purpose: str


async def _load(
    conn: AsyncConnection, statement: TextClause, params: dict[str, Any]
) -> list[Outcome]:
    rows = (await conn.execute(statement, params)).all()
    return [
        Outcome(
            r=row.r_multiple,
            decision_at=ensure_utc(row.emitted_at),
            market=f"{row.exchange}:{row.symbol}",
            exit_at=ensure_utc(row.exit_ts),
        )
        for row in rows
    ]


async def load_outcomes(
    conn: AsyncConnection, version_id: uuid.UUID, *, as_of: datetime | None = None
) -> list[Outcome]:
    """A população avaliável **prospectiva** de uma versão (D15 b).

    É esta que o veredito do placar mede e a que autoriza (ou recusa) uma
    rodada de replicação. Nenhuma barra de replay entra aqui.
    """
    return await _load(conn, _OUTCOMES_PROSPECTIVE_SQL, {"version_id": version_id, "as_of": as_of})


async def load_sibling_outcomes(
    conn: AsyncConnection,
    sibling_id: uuid.UUID,
    parent_id: uuid.UUID,
    k: int,
    *,
    as_of: datetime | None = None,
) -> list[Outcome]:
    """A população de uma irmã: viva primeiro, replay depois, **sem repetir**.

    D15 (a) permite que o replay amadureça o bloco 2; D15 não permite que a
    mesma decisão conte duas vezes por ter sido replayada sob dois ``run_id``.
    A junção é a pura ``dedupe_outcomes``, a mesma que a API usa.
    """
    live = await _load(
        conn,
        _OUTCOMES_LIVE_SQL,
        {"version_id": sibling_id, "as_of": as_of, "arm": arm_label(parent_id, k)},
    )
    replay = await _load(conn, _OUTCOMES_REPLAY_SQL, {"version_id": sibling_id, "as_of": as_of})
    outcomes, _, _ = dedupe_outcomes([live, replay])
    return outcomes


def parse_promising_at(changelog: str | None) -> datetime | None:
    """``promising_at=<iso>`` de dentro de um ``changelog`` de irmã."""
    if not changelog:
        return None
    found = _PROMISING_RE.search(changelog)
    if found is None:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(found.group("ts").replace("Z", "+00:00")))
    except ValueError:
        return None


async def load_sibling_rows(conn: AsyncConnection, parent_id: uuid.UUID) -> list[SiblingRow]:
    """As irmãs de um pai, na ordem de ``k``."""
    rows = (
        await conn.execute(_SIBLINGS_SQL, {"prefix": REPLICATION_PREFIX, "parent": str(parent_id)})
    ).all()
    siblings: list[SiblingRow] = []
    for row in rows:
        match = ARM_RE.match(row.changelog or "")
        labelled = match is not None and match.group("parent").lower() == str(parent_id).lower()
        if row.replication_index is not None:
            k = int(row.replication_index)
        elif match is not None and labelled:
            k = int(match.group("k"))
        else:
            continue
        siblings.append(
            SiblingRow(
                id=row.id,
                version=row.version,
                k=k,
                changelog=row.changelog or "",
                status=row.status,
                purpose=row.purpose,
            )
        )
    return sorted(siblings, key=lambda item: item.k)


async def load_promising_at(
    conn: AsyncConnection, parent_id: uuid.UUID, siblings: list[SiblingRow] | None = None
) -> datetime | None:
    """``promising_at`` do pai: a coluna, depois o ``changelog``, depois o evento.

    A ordem não é estética. A **coluna** (``0012_replication``) é a única fonte
    que existe para um pai marcado como promissor e ainda não replicado — é o
    caso normal entre o veredito e a rodada. O ``changelog`` da irmã é
    permanente e cobre as irmãs derivadas antes da migração. ``system_events``
    vem por último porque tem retenção de 30 dias e o bloco 1 precisa de mais
    que isso. Quando duas existem, valem o mesmo instante (mesmo commit).
    """
    from_column = await conn.scalar(_PROMISING_COLUMN_SQL, {"parent": str(parent_id)})
    if from_column is not None:
        return ensure_utc(from_column)
    rows = siblings if siblings is not None else await load_sibling_rows(conn, parent_id)
    stamps = [
        stamp for stamp in (parse_promising_at(row.changelog) for row in rows) if stamp is not None
    ]
    if stamps:
        return min(stamps)
    recorded = await conn.scalar(
        _PROMISING_SQL, {"event": PROMISING_EVENT, "parent": str(parent_id)}
    )
    if recorded is None:
        return None
    return parse_promising_at(f"promising_at={recorded}")


async def build_report(
    conn: AsyncConnection,
    parent_id: uuid.UUID,
    *,
    seed: int,
    as_of: datetime | None = None,
) -> ReplicationReport:
    """O relatório completo de um pai: quatro blocos e o veredito do §5."""
    parent_outcomes = await load_outcomes(conn, parent_id, as_of=as_of)
    siblings = await load_sibling_rows(conn, parent_id)
    arms = [
        SiblingArm(
            k=row.k,
            version=row.version,
            outcomes=await load_sibling_outcomes(conn, row.id, parent_id, row.k, as_of=as_of),
        )
        for row in siblings
    ]
    return replication_report(
        parent_outcomes=parent_outcomes,
        promising_at=await load_promising_at(conn, parent_id, siblings),
        siblings=arms,
        seed=seed,
    )


def summarise(report: ReplicationReport) -> str:
    """Uma linha por bloco, em português, para o ``--report`` da CLI."""
    lines = [
        f"veredito: {report.status}" + (f" ({report.reason})" if report.reason else ""),
        f"pai: {report.parent_verdict} — {report.parent.evaluable} resultados avaliáveis, "
        f"{report.parent.days} dias, {report.parent.markets} mercados, "
        f"expectancy {report.parent.expectancy_r}, PF "
        f"{report.parent.profit_factor or report.parent.profit_factor_reason}",
    ]
    for block in (report.out_of_sample, report.siblings, report.market_halves, report.bootstrap):
        verdict = {True: "passou", False: "FALHOU", None: "aguardando"}[block.passed]
        lines.append(f"{block.name}: {verdict}" + (f" — {block.reason}" if block.reason else ""))
    return "\n".join(lines)


def data_of(report: ReplicationReport) -> dict[str, Any]:
    """O payload do relatório, para o evento de auditoria e para o placar."""
    return report.to_jsonable()
