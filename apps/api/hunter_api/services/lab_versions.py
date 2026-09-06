"""Assembling ``GET /api/v1/lab/shadow/versions``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_api.schemas.lab_versions import VersionOut, VersionsOut

if TYPE_CHECKING:
    from hunter_api.repositories.lab_versions import VersionRow


def build_versions(rows: list[VersionRow]) -> VersionsOut:
    return VersionsOut(
        items=[
            VersionOut(
                strategy_version_id=row.id,
                strategy_key=row.strategy_key,
                version=row.version,
                status=row.status,
                code_ref=row.code_ref,
                activated_at=row.activated_at,
                deprecated_at=row.deprecated_at,
                superseded_by=row.superseded_by,
                params_hash=row.params_hash,
                default_parameters=row.default_parameters,
            )
            for row in rows
        ]
    )
