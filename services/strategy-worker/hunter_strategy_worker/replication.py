"""Derivar as irmãs de uma versão promissora (`docs/plans/REPLICATION.md` §4).

O mesmo desenho de ``paper_line.py``, com um propósito oposto: aquilo deriva a
linha que **pode** um dia chegar à carteira; isto deriva N linhas que **nunca**
chegam — ``purpose = research_only``, que a ponte de execução recusa pelo nome,
e sem linha em ``agents`` que as autorize em qualquer carteira.

Cada irmã é uma linha real de ``strategy_versions``: próximo ``v<n>`` livre,
``parameters_schema`` e ``params_format`` copiados byte a byte do pai,
``default_parameters`` jitterados em ±15 % (`hunter_indicators.replication.jitter`),
``code_ref`` recomputado do módulo que o digest congelado do pai nomeia,
``status = 'active'``, ``activated_at = now()``, e a linhagem em coluna
(``replication_parent_id``/``replication_index``, ``0012_replication``).

**Do pai, uma única coluna se move**, e é a razão da ``0012``: ``promising_at``
(com ``promising_by``), gravado por :func:`mark_promising` no mesmo commit. A
T3.19 dizia "o pai não é tocado — nenhum UPDATE"; a frase valia enquanto o
carimbo morava no ``changelog`` das irmãs e num ``system_events`` de 30 dias, o
que fazia do marco de onde o bloco 1 conta uma substring de texto livre. O resto
do pai continua intocado: nem ``changelog``, nem ``status``, nem parâmetros —
e o carimbo nunca se move depois de escrito.

Toda recusa é uma recusa (nunca um aviso) e toda rodada deixa auditoria em
``system_events``, como o script de ativação. Nada aqui ativa uma linha
``paper``, altera risco ou toca carteira.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_indicators.replication import JITTER_PCT, SIBLINGS_N
from hunter_indicators.replication.stats import VERDICT_VALIDATED
from hunter_strategy_worker.activation_db import (
    PURPOSE_RESEARCH_ONLY,
    Refused,
    load_row,
    migration_applied,
    next_free_version,
    purpose_column_present,
)
from hunter_strategy_worker.catalogue import resolve_strategy
from hunter_strategy_worker.code_ref import strategy_module, version_code_ref
from hunter_strategy_worker.replication_derive import Sibling, derive_siblings, sibling_changelog
from hunter_strategy_worker.replication_stats import (
    PROMISING_EVENT,
    build_report,
    load_promising_at,
    load_sibling_rows,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "COMPONENT",
    "PROMISING_BY_MAX",
    "Sibling",
    "mark_promising",
    "record_replication_event",
    "replicate",
]

COMPONENT = "replicate_strategy_version"
"""``system_events.component`` desta ferramenta — separado do script de ativação
de propósito: quem audita replicação não quer ler ativações no meio."""

_INSERT = text(
    "INSERT INTO strategy_versions (id, strategy_id, version, status, parameters_schema, "
    "default_parameters, code_ref, params_format, changelog, activated_at, purpose, "
    "replication_parent_id, replication_index) "
    "VALUES (gen_random_uuid(), :strategy_id, :version, 'active', CAST(:schema AS jsonb), "
    "CAST(:params AS jsonb), :code_ref, :params_format, :changelog, now(), :purpose, "
    "CAST(:parent_id AS uuid), :k) "
    "RETURNING id"
)
"""A irmã nasce com a linhagem, no mesmo INSERT que a ativa.

``replication_parent_id``/``replication_index`` (``0012_replication``) entram
aqui, e não num UPDATE depois, por duas razões: a trigger de congelamento
recusaria o UPDATE (``activated_at`` já está preenchido na mesma linha), e uma
irmã que existisse por um instante sem pai seria exatamente a linha órfã que o
CHECK da §24 existe para tornar irrepresentável. O rótulo continua no
``changelog`` ao lado — é o que uma irmã derivada antes da migração tem, e o que
um humano lê."""

_MARK_PROMISING = text(
    "UPDATE strategy_versions SET promising_at = coalesce(CAST(:at AS timestamptz), now()), "
    "promising_by = :by WHERE id = :id AND promising_at IS NULL "
    "RETURNING promising_at"
)
"""``AND promising_at IS NULL`` é a idempotência inteira: um carimbo existente
nunca se move, e mover não é um caso a tratar — é uma linha que não é atualizada."""

_READ_PROMISING = text("SELECT promising_at FROM strategy_versions WHERE id = :id")
_EXISTS = text("SELECT 1 FROM strategy_versions WHERE id = :id")

PROMISING_BY_MAX = 64
"""``ck_strategy_versions_promising_is_attributed`` aceita 1..64 caracteres."""


async def _replication_columns_present(conn: AsyncConnection) -> bool:
    """``0012_replication`` aplicada — as quatro colunas que esta rodada escreve."""
    found = await conn.scalar(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'strategy_versions' AND column_name IN "
            "('promising_at', 'promising_by', 'replication_parent_id', 'replication_index')"
        )
    )
    return int(found or 0) == 4


async def record_replication_event(
    conn: AsyncConnection, level: str, event: str, message: str, data: dict[str, Any]
) -> None:
    """A linha de auditoria — com ``data`` estruturada, que é o que o placar lê."""
    await conn.execute(
        text(
            "INSERT INTO system_events (id, created_at, level, component, event, message, data) "
            "VALUES (gen_random_uuid(), now(), CAST(:level AS event_severity), :component, "
            ":event, :message, CAST(:data AS jsonb))"
        ),
        {
            "level": level,
            "component": COMPONENT,
            "event": event,
            "message": message[:1000],
            "data": json.dumps(data, separators=(",", ":"), sort_keys=True, default=str),
        },
    )


async def mark_promising(
    conn: AsyncConnection,
    version_id: uuid.UUID,
    verdict_source: str,
    *,
    at: datetime | None = None,
) -> datetime:
    """Grava ``promising_at`` **uma vez** e devolve o instante que vale.

    Este é o único lugar que escreve a coluna (brief T3.19c, entrega 3), e ele é
    o único porque o carimbo decide onde o bloco 1 do protocolo começa a contar
    (REPLICATION.md §1.6/§3.1): dois escritores seriam duas datas, e a mais
    recente ganharia sem que ninguém visse a outra desaparecer.

    Três propriedades, e cada uma tem uma razão:

    - **idempotente por SQL, não por leitura anterior.** O ``WHERE promising_at
      IS NULL`` do UPDATE é o que decide; um ``SELECT`` antes seguido de um
      ``UPDATE`` seria a mesma corrida que a §17.8 recusa no seed. Uma segunda
      chamada não move o carimbo e não escreve evento nenhum;
    - **conexão de dono.** ``0010``/``0011`` deixaram ``hunter_worker`` com
      ``SELECT`` e mais nada de tabela em ``strategy_versions``, então esta
      função só roda pela ``DATABASE_URL_MIGRATIONS`` (DATABASE.md §24). Como
      ``purpose``;
    - **auditada.** Um ``system_events`` por marcação de fato feita, com o
      instante e a origem do veredito — a mesma linha que a T3.19 já escrevia,
      agora escrita por quem escreve a coluna.

    ``verdict_source`` é o que a coluna ``promising_by`` guarda: qual veredito
    carimbou. Vazio ou maior que 64 caracteres é recusa, não truncamento — o
    CHECK recusaria de qualquer forma, e truncar inventaria uma atribuição.
    """
    source = verdict_source.strip()
    if not 1 <= len(source) <= PROMISING_BY_MAX:
        raise Refused(
            f"promising_by precisa ter de 1 a {PROMISING_BY_MAX} caracteres "
            f"(recebi {len(source)}): um carimbo que ninguém consegue atribuir é uma data"
        )
    marked = await conn.scalar(_MARK_PROMISING, {"id": version_id, "by": source, "at": at})
    if marked is not None:
        stamped = ensure_utc(marked)
        await record_replication_event(
            conn,
            "info",
            PROMISING_EVENT,
            f"strategy_version {version_id} promissora em {stamped.isoformat()} ({source})",
            {
                "strategy_version_id": str(version_id),
                "promising_at": stamped.isoformat(),
                "promising_by": source,
            },
        )
        return stamped
    existing = await conn.scalar(_READ_PROMISING, {"id": version_id})
    if existing is None:
        raise Refused(
            f"não existe strategy_version {version_id} para marcar como promissora"
            if await conn.scalar(_EXISTS, {"id": version_id}) is None
            else f"strategy_version {version_id} não pôde ser marcada"
        )
    return ensure_utc(existing)


async def replicate(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    *,
    dry_run: bool,
    siblings: int = SIBLINGS_N,
    seed: int,
    force_research: str | None = None,
    registry: StrategyRegistry = DEFAULT_REGISTRY,
) -> str:
    """Deriva ``siblings`` irmãs do pai ``(key, version)``. Devolve o resumo."""
    if siblings < 1:
        raise Refused("--siblings precisa ser pelo menos 1")
    if not await migration_applied(conn):
        raise Refused("0002_shadow_lab não está aplicada: aplique a migração antes de replicar")
    if not await purpose_column_present(conn):
        raise Refused("0010_strategy_purpose não está aplicada: aplique a migração antes")
    if not await _replication_columns_present(conn):
        raise Refused(
            "0012_replication não está aplicada: sem promising_at e sem a linhagem em coluna "
            "a rodada gravaria uma irmã que só o changelog liga ao pai (DATABASE.md §24)"
        )
    row = await load_row(conn, key, version)
    if row is None:
        raise Refused(f"não existe strategy_version para {key} {version}")
    if row.activated_at is None:
        raise Refused(f"{key} {version} nunca foi ativada: uma irmã copia uma coorte **congelada**")
    if row.purpose != PURPOSE_RESEARCH_ONLY:
        raise Refused(
            f"{key} {version} tem purpose {row.purpose!r}: só uma versão {PURPOSE_RESEARCH_ONLY!r} "
            "é replicada — uma linha que pode tocar carteira nunca é multiplicada por dez"
        )
    strategy = resolve_strategy(key, version, row.code_ref, registry)
    if strategy is None:
        raise Refused(
            f"este build não liga {key} {version} a código: nem o registry nem o code_ref "
            f"congelado ({row.code_ref}) nomeiam um módulo que ele carrega"
        )
    code_ref = version_code_ref(strategy_module(strategy))
    if row.code_ref != code_ref:
        raise Refused(
            f"{key} {version} está congelada em code_ref {row.code_ref} e este build é {code_ref}: "
            "uma irmã roda exatamente o código que o pai rodou"
        )
    existing = await load_sibling_rows(conn, row.id)
    if existing:
        raise Refused(
            f"{key} {version} já tem {len(existing)} irmãs "
            f"({', '.join(item.version for item in existing)}): replicar de novo seria dobrar as "
            "tentativas e inflar o falso positivo que o protocolo combate (REPLICATION.md §4.1)"
        )
    # A conta que autoriza a rodada é a população **prospectiva** do pai, com o
    # portão do placar (``replication_stats``, T3.18c 1 e 2): um replay positivo
    # nem entra nela, então ``promising_at`` não nasce de história.
    report = await build_report(conn, row.id, seed=seed)
    if report.parent_verdict != VERDICT_VALIDATED and force_research is None:
        raise Refused(
            f"{key} {version} não é promissora: o placar diz {report.parent_verdict!r} "
            f"sobre a coorte prospectiva ({report.parent.evaluable} resultados avaliáveis, "
            f"{report.parent.days} dias de saída, expectancy {report.parent.expectancy_r}, "
            f"PF {report.parent.profit_factor}). "
            'Use --force-research "<motivo>" para um experimento manual.'
        )
    forced = force_research is not None
    promising_at = await load_promising_at(conn, row.id, existing) or datetime.now(UTC)
    schema: dict[str, Any] = dict(row.parameters_schema or {})
    parent_params: dict[str, Any] = dict(row.default_parameters or {})
    if not parent_params:
        raise Refused(f"{key} {version} não tem default_parameters: nada a deslocar")
    labels = [await next_free_version(conn, row.strategy_id)]
    for _ in range(siblings - 1):
        labels.append(f"v{int(labels[-1][1:]) + 1}")
    derived = derive_siblings(
        parent_id=row.id,
        parent_params=parent_params,
        schema=schema,
        versions=labels,
        seed=seed,
        count=siblings,
        pct=JITTER_PCT,
    )
    note = f"forçado: {force_research}" if forced else changelog
    if dry_run:
        preview = "\n".join(f"  {item.summary()}" for item in derived)
        return (
            f"derivaria {siblings} irmãs de {key} {version} (semente {seed}, ±{JITTER_PCT}, "
            f"purpose {PURPOSE_RESEARCH_ONLY}, nada ativado na carteira):\n{preview}"
        )
    if not forced:
        # O carimbo vem antes das irmãs porque é ele que elas citam: uma rodada
        # que gravasse dez changelogs e só então descobrisse que não consegue
        # marcar o pai teria escrito dez linhas apontando para um marco que não
        # existe. Um pai forçado continua sem carimbo — ele não é promissor,
        # é um experimento manual (REPLICATION.md §4.1).
        promising_at = await mark_promising(conn, row.id, f"{COMPONENT}:{report.parent_verdict}")
    created: list[str] = []
    for sibling in derived:
        await conn.execute(
            _INSERT,
            {
                "strategy_id": row.strategy_id,
                "version": sibling.version,
                "schema": json.dumps(schema, separators=(",", ":"), sort_keys=True),
                "params": json.dumps(sibling.parameters, separators=(",", ":"), sort_keys=True),
                "code_ref": code_ref,
                "params_format": row.params_format,
                "changelog": sibling_changelog(
                    sibling,
                    parent_version=version,
                    promising_at=promising_at,
                    seed=seed,
                    note=note,
                ),
                "purpose": PURPOSE_RESEARCH_ONLY,
                "parent_id": str(row.id),
                "k": sibling.k,
            },
        )
        created.append(sibling.version)
    payload: dict[str, Any] = {
        "strategy_version_id": str(row.id),
        "strategy": key,
        "version": version,
        "promising_at": promising_at.isoformat(),
        "seed": seed,
        "pct": str(JITTER_PCT),
        "siblings": created,
        "forced": forced,
        "parent_verdict": report.parent_verdict,
        "purpose": PURPOSE_RESEARCH_ONLY,
    }
    await record_replication_event(
        conn,
        "warning" if forced else "info",
        "strategy_version_replicated",
        f"{key} {version} replicada em {len(created)} irmãs research_only "
        f"({', '.join(created)}), semente {seed}: {note}",
        payload,
    )
    return (
        f"criadas {len(created)} irmãs de {key} {version} ({', '.join(created)}), "
        f"purpose {PURPOSE_RESEARCH_ONLY}, semente {seed}, promising_at "
        f"{promising_at.isoformat()}; nada foi ativado para a carteira"
        + (" [FORÇADO]" if forced else "")
    )
