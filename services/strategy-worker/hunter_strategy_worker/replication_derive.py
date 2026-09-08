"""Os conjuntos de parâmetros de uma rodada de replicação (`REPLICATION.md` §4.2).

Separado de :mod:`hunter_strategy_worker.replication` pelo orçamento de 350
linhas (``infra/scripts/check_file_size.py``) e por uma costura real: isto
**deriva** as irmãs (jitter, validação contra o schema congelado do pai,
colisão de ``params_hash``) e aquilo **conduz a rodada** (pré-condições,
``promising_at``, INSERT, auditoria). Nada aqui toca o banco.

``replication.py`` reexporta :class:`Sibling`: uma divisão de módulo que quebra
um import é uma refatoração que quebrou alguma coisa (DATABASE.md §18.10).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hunter_core.strategies.canonical import params_hash
from hunter_indicators.replication import JITTER_PCT, jitter_parameters
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.activation_db import Refused
from hunter_strategy_worker.replication_stats import arm_label

__all__ = ["Sibling", "derive_siblings", "sibling_changelog"]


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


def derive_siblings(
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


def sibling_changelog(
    sibling: Sibling, *, parent_version: str, promising_at: datetime, seed: int, note: str
) -> str:
    """O rótulo do braço vem **primeiro**: é por ele que as irmãs são encontradas,
    e ``promising_at`` viaja junto porque ``system_events`` expira em 30 dias."""
    return (
        f"{sibling.label} | irmã {sibling.k} de {parent_version} "
        f"(T3.19, docs/plans/REPLICATION.md) | promising_at={promising_at.isoformat()} "
        f"| seed={seed} | pct={JITTER_PCT} | {note}"
    )
