"""Derivar as irmãs de uma versão promissora (`docs/plans/REPLICATION.md` §4).

O mesmo desenho de ``paper_line.py``, com um propósito oposto: aquilo deriva a
linha que **pode** um dia chegar à carteira; isto deriva N linhas que **nunca**
chegam — ``purpose = research_only``, que a ponte de execução recusa pelo nome,
e sem linha em ``agents`` que as autorize em qualquer carteira.

Cada irmã é uma linha real de ``strategy_versions``: próximo ``v<n>`` livre,
``parameters_schema`` e ``params_format`` copiados byte a byte do pai,
``default_parameters`` jitterados em ±15 % (`hunter_indicators.replication.jitter`),
``code_ref`` recomputado do módulo que o digest congelado do pai nomeia,
``status = 'active'``, ``activated_at = now()``. **O pai não é tocado** — nenhum
UPDATE, nem no ``changelog``.

Toda recusa é uma recusa (nunca um aviso) e toda rodada deixa auditoria em
``system_events``, como o script de ativação. Nada aqui ativa uma linha
``paper``, altera risco ou toca carteira.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.strategies.canonical import params_hash
from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_indicators.replication import JITTER_PCT, SIBLINGS_N, jitter_parameters
from hunter_indicators.replication.stats import VERDICT_VALIDATED
from hunter_strategy_worker.activation import validate_parameters
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
from hunter_strategy_worker.replication_stats import (
    arm_label,
    build_report,
    load_promising_at,
    load_sibling_rows,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = ["COMPONENT", "Sibling", "record_replication_event", "replicate"]

COMPONENT = "replicate_strategy_version"
"""``system_events.component`` desta ferramenta — separado do script de ativação
de propósito: quem audita replicação não quer ler ativações no meio."""

_INSERT = text(
    "INSERT INTO strategy_versions (id, strategy_id, version, status, parameters_schema, "
    "default_parameters, code_ref, params_format, changelog, activated_at, purpose) "
    "VALUES (gen_random_uuid(), :strategy_id, :version, 'active', CAST(:schema AS jsonb), "
    "CAST(:params AS jsonb), :code_ref, :params_format, :changelog, now(), :purpose) "
    "RETURNING id"
)


@dataclass(frozen=True, slots=True)
class Sibling:
    """Uma irmã antes de existir: o rótulo do braço e os parâmetros deslocados."""

    k: int
    version: str
    label: str
    parameters: dict[str, Any]
    changes: tuple[tuple[str, str, str], ...]

    def summary(self) -> str:
        moved = ", ".join(f"{name} {before}->{after}" for name, before, after in self.changes)
        return f"{self.version} [{self.label}] {moved or '(nenhum parâmetro se moveu)'}"


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


def _derive(
    *,
    parent_id: uuid.UUID,
    parent_params: dict[str, Any],
    schema: dict[str, Any],
    versions: list[str],
    seed: int,
    count: int,
    pct: Any,
) -> list[Sibling]:
    """Os N conjuntos jitterados, já validados e sem colisão de ``params_hash``.

    A semente de cada irmã é ``seed + k``: uma semente por braço, derivada da
    semente da rodada, de forma que registrar um número reproduz as dez.
    """
    seen = {params_hash(parent_params): "pai"}
    siblings: list[Sibling] = []
    for k in range(1, count + 1):
        result = jitter_parameters(parent_params, schema, seed=seed + k, pct=pct)
        report = validate_parameters(schema, result.parameters)
        if not report.ok:
            raise Refused(
                f"a irmã {k} não valida contra o schema congelado do pai: "
                + "; ".join(report.errors)
            )
        digest = params_hash(result.parameters)
        if digest in seen:
            raise Refused(
                f"a irmã {k} tem os mesmos parâmetros de {seen[digest]} (params_hash {digest[:12]}"
                "): seria o mesmo experimento contado duas vezes — troque a semente"
            )
        seen[digest] = f"irmã {k}"
        siblings.append(
            Sibling(
                k=k,
                version=versions[k - 1],
                label=arm_label(parent_id, k),
                parameters=result.parameters,
                changes=tuple(
                    (change.name, change.original, change.jittered) for change in result.changes
                ),
            )
        )
    return siblings


def _changelog(
    sibling: Sibling, *, parent_version: str, promising_at: datetime, seed: int, note: str
) -> str:
    """O rótulo do braço vem **primeiro**: é por ele que as irmãs são encontradas,
    e ``promising_at`` viaja junto porque ``system_events`` expira em 30 dias."""
    return (
        f"{sibling.label} | irmã {sibling.k} de {parent_version} "
        f"(T3.19, docs/plans/REPLICATION.md) | promising_at={promising_at.isoformat()} "
        f"| seed={seed} | pct={JITTER_PCT} | {note}"
    )


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
    report = await build_report(conn, row.id, seed=seed)
    if report.parent_verdict != VERDICT_VALIDATED and force_research is None:
        raise Refused(
            f"{key} {version} não é promissora: o placar diz {report.parent_verdict!r} "
            f"({report.parent.evaluable} resultados avaliáveis, {report.parent.days} dias, "
            f"expectancy {report.parent.expectancy_r}, PF {report.parent.profit_factor}). "
            'Use --force-research "<motivo>" para um experimento manual.'
        )
    promising_at = await load_promising_at(conn, row.id, existing) or datetime.now(UTC)
    schema: dict[str, Any] = dict(row.parameters_schema or {})
    parent_params: dict[str, Any] = dict(row.default_parameters or {})
    if not parent_params:
        raise Refused(f"{key} {version} não tem default_parameters: nada a deslocar")
    labels = [await next_free_version(conn, row.strategy_id)]
    for _ in range(siblings - 1):
        labels.append(f"v{int(labels[-1][1:]) + 1}")
    derived = _derive(
        parent_id=row.id,
        parent_params=parent_params,
        schema=schema,
        versions=labels,
        seed=seed,
        count=siblings,
        pct=JITTER_PCT,
    )
    forced = force_research is not None
    note = f"forçado: {force_research}" if forced else changelog
    if dry_run:
        preview = "\n".join(f"  {item.summary()}" for item in derived)
        return (
            f"derivaria {siblings} irmãs de {key} {version} (semente {seed}, ±{JITTER_PCT}, "
            f"purpose {PURPOSE_RESEARCH_ONLY}, nada ativado na carteira):\n{preview}"
        )
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
                "changelog": _changelog(
                    sibling,
                    parent_version=version,
                    promising_at=promising_at,
                    seed=seed,
                    note=note,
                ),
                "purpose": PURPOSE_RESEARCH_ONLY,
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
    if not forced:
        await record_replication_event(
            conn,
            "info",
            "strategy_version_promising",
            f"{key} {version} promissora em {promising_at.isoformat()}; replicação iniciada",
            {"strategy_version_id": str(row.id), "promising_at": promising_at.isoformat()},
        )
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
