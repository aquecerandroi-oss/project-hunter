"""``GET /api/v1/lab/shadow/versions`` — the frozen catalogue, global no-RLS
read (DATABASE.md §16.1).

``superseded_by`` has no durable column: ``infra/scripts/activate_strategy_version.py``
only ever writes the relationship as free text, in the deprecated row's
``changelog`` (``"superseded by <version> (code_ref ...)"``) and in a
``system_events`` message. Astra's contract review confirmed there is no
better source (``.claude/state/astra-review-S3-lab-api-contract.md``): the
regex below is best-effort, never treated as an identity.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from hunter_core.db.models.agents import Strategy, StrategyVersion
from hunter_core.domain.enums import StrategyVersionStatus
from hunter_core.strategies.canonical import params_hash as compute_params_hash

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_SUPERSEDED_BY_RE = re.compile(r"^superseded by (\S+)")


@dataclass(frozen=True, slots=True)
class VersionRow:
    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_key: str
    version: str
    status: StrategyVersionStatus
    code_ref: str | None
    activated_at: datetime | None
    deprecated_at: datetime | None
    default_parameters: dict[str, Any]
    params_hash: str
    superseded_by: uuid.UUID | None


class LabVersionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[VersionRow]:
        rows = (
            await self.session.execute(
                select(StrategyVersion, Strategy.key)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .order_by(Strategy.key, StrategyVersion.version)
            )
        ).all()
        by_strategy_and_version: dict[tuple[uuid.UUID, str], uuid.UUID] = {
            (sv.strategy_id, sv.version): sv.id for sv, _key in rows
        }
        out: list[VersionRow] = []
        for sv, key in rows:
            params = dict(sv.default_parameters or {})
            successor_version = _successor_version(sv.changelog, sv.status)
            superseded_by = (
                by_strategy_and_version.get((sv.strategy_id, successor_version))
                if successor_version is not None
                else None
            )
            out.append(
                VersionRow(
                    id=sv.id,
                    strategy_id=sv.strategy_id,
                    strategy_key=key,
                    version=sv.version,
                    status=sv.status,
                    code_ref=sv.code_ref,
                    activated_at=sv.activated_at,
                    deprecated_at=sv.deprecated_at,
                    default_parameters=params,
                    params_hash=compute_params_hash(params),
                    superseded_by=superseded_by,
                )
            )
        return out


def _successor_version(changelog: str | None, status: StrategyVersionStatus) -> str | None:
    if status is not StrategyVersionStatus.DEPRECATED or not changelog:
        return None
    match = _SUPERSEDED_BY_RE.match(changelog)
    return match.group(1) if match else None
