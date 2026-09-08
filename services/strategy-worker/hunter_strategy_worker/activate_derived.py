"""Activate a row whose content was already copied byte for byte (T3.15e).

Pulled out of ``infra/scripts/activate_strategy_version.py`` — same reason
``paper_line.py`` was: the 350-line budget (T3.15). A ``--paper-line`` product
carries its own ``parameters_schema``/``default_parameters``/``params_format``,
copied from the frozen research row it was derived from (D10, "parâmetros
copiados bit a bit"). Activating it must confirm the build still matches the
frozen ``code_ref`` and then write only ``status``, ``activated_at`` and
``changelog`` — never rewrite the copy from today's code, which is what
``activate()``'s plain research path does and what a derived row must not go
through (review T3.15-risk, "Antes de ligar a ponte" item 1).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.activation_db import Refused, record_event

__all__ = ["activate_derived"]


async def activate_derived(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    row: Any,
    *,
    code_ref: str,
    dry_run: bool,
) -> str:
    """``row`` already carries its own content; ``code_ref`` is what this
    build recomputes for it (the caller resolves the strategy — the same
    resolution :func:`activate` uses for the plain research path)."""
    if row.code_ref != code_ref:
        raise Refused(
            f"{key} {version} is frozen at code_ref {row.code_ref} but this build is "
            f"{code_ref}: deploy the matching build or derive again"
        )
    if row.activated_at is not None:
        return f"{key} {version} was already activated at {row.activated_at.isoformat()}; nothing to do"
    schema: dict[str, Any] = dict(row.parameters_schema or {})
    params: dict[str, Any] = dict(row.default_parameters or {})
    report = validate_parameters(schema, params)
    if not report.ok:
        raise Refused(
            "default_parameters do not match parameters_schema: " + "; ".join(report.errors)
        )
    if dry_run:
        return (
            f"would activate {key} {version} (purpose {row.purpose}) with code_ref {code_ref} "
            f"({len(params)} parameters)"
        )
    updated = await conn.execute(
        text(
            "UPDATE strategy_versions SET status = 'active', activated_at = now(), "
            "changelog = :changelog WHERE id = :id AND activated_at IS NULL "
            "RETURNING activated_at"
        ),
        {"changelog": changelog, "id": row.id},
    )
    activated = updated.first()
    if activated is None:
        raise Refused(f"{key} {version} was activated concurrently; nothing was written")
    await record_event(
        conn,
        "info",
        "strategy_version_activated",
        f"{key} {version} (purpose {row.purpose}) activated with its already-copied "
        f"code_ref={code_ref} params_format={row.params_format}: {changelog}",
    )
    return (
        f"activated {key} {version} (purpose {row.purpose}) at {activated[0].isoformat()} "
        f"with code_ref {code_ref}"
    )
