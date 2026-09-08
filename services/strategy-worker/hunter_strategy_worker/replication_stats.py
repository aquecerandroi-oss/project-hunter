"""O que o protocolo de replicação lê do banco (`docs/plans/REPLICATION.md`).

Só leitura e só tradução: as contas moram em
:mod:`hunter_indicators.replication`, que é puro e testável com séries
sintéticas. Aqui ficam as três consultas que o protocolo precisa —

1. a população **avaliável** de uma versão (``tracking_state = 'terminal'`` e
   ``r_multiple IS NOT NULL``, a mesma definição do plantão e do placar);
2. as irmãs de um pai, reconhecidas pelo rótulo ``replication:<pai>:<k>`` no
   ``changelog``;
3. o ``promising_at``, lido do ``changelog`` das irmãs (durável) e, na falta
   dele, de ``system_events`` (retenção de 30 dias — por isso não é a fonte
   primária).

**Chave de mercado.** As metades do bloco 3 são partidas por
``<exchange>:<symbol>``, não só pelo símbolo: o mesmo ``BTCUSDT`` em duas
corretoras é mercado diferente, e uma partição que os confunde partiria a
população pelo lugar errado.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import ensure_utc
from hunter_indicators.replication import Outcome, SiblingArm, replication_report

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

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
    "load_sibling_rows",
    "parse_promising_at",
    "summarise",
]

REPLICATION_PREFIX = "replication:"
"""Prefixo do rótulo do braço. **Ainda não é** a coorte de ``shadow_episodes``:
o CHECK de ``0002_shadow_lab`` só aceita ``prospective`` e ``replay:<uuid>``
(REPLICATION.md §4.4 — pendência declarada, não um esquecimento)."""

PROMISING_EVENT = "strategy_version_promising"

ARM_RE = re.compile(
    r"^replication:(?P<parent>[0-9a-fA-F-]{36}):(?P<k>\d+)\b",
)
_PROMISING_RE = re.compile(r"promising_at=(?P<ts>[0-9T:\-\.+Z]+)")

_OUTCOMES_SQL = text(
    "SELECT s.emitted_at, o.r_multiple, e.code AS exchange, m.symbol "
    "FROM agent_signals s "
    "JOIN signal_outcomes o ON o.signal_id = s.id "
    "JOIN markets m ON m.id = s.market_id "
    "JOIN exchanges e ON e.id = m.exchange_id "
    "WHERE s.strategy_version_id = :version_id "
    "AND o.tracking_state = 'terminal' AND o.r_multiple IS NOT NULL "
    "AND (CAST(:as_of AS timestamptz) IS NULL OR s.emitted_at <= CAST(:as_of AS timestamptz)) "
    "ORDER BY s.emitted_at, s.id"
)

_SIBLINGS_SQL = text(
    "SELECT v.id, v.version, v.changelog, v.status, v.purpose "
    "FROM strategy_versions v "
    "WHERE v.changelog LIKE :prefix || :parent || ':%' "
    "ORDER BY v.version"
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
    """Uma irmã como o banco a guarda, com o ``k`` lido do rótulo."""

    id: uuid.UUID
    version: str
    k: int
    changelog: str
    status: str
    purpose: str


async def load_outcomes(
    conn: AsyncConnection, version_id: uuid.UUID, *, as_of: datetime | None = None
) -> list[Outcome]:
    """A população avaliável de uma versão, pronta para a estatística pura."""
    rows = (await conn.execute(_OUTCOMES_SQL, {"version_id": version_id, "as_of": as_of})).all()
    return [
        Outcome(
            r=row.r_multiple,
            decision_at=ensure_utc(row.emitted_at),
            market=f"{row.exchange}:{row.symbol}",
        )
        for row in rows
    ]


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
        if match is None or match.group("parent").lower() != str(parent_id).lower():
            continue
        siblings.append(
            SiblingRow(
                id=row.id,
                version=row.version,
                k=int(match.group("k")),
                changelog=row.changelog,
                status=row.status,
                purpose=row.purpose,
            )
        )
    return sorted(siblings, key=lambda item: item.k)


async def load_promising_at(
    conn: AsyncConnection, parent_id: uuid.UUID, siblings: list[SiblingRow] | None = None
) -> datetime | None:
    """``promising_at`` do pai: primeiro o ``changelog`` das irmãs, depois o evento.

    A ordem não é estética: ``system_events`` tem retenção de 30 dias e o bloco 1
    precisa de mais que isso; a linha da irmã é permanente. Quando as duas
    existem, valem o mesmo instante (foram escritas no mesmo commit).
    """
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
            outcomes=await load_outcomes(conn, row.id, as_of=as_of),
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
