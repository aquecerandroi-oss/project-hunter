"""``--supersede``: move an *already frozen* version onto a new ``code_ref``.

Pulled out of ``infra/scripts/activate_strategy_version.py`` when
``--deprecate`` (T3.39) pushed the script past the 350-line budget — the same
reason ``paper_line.py``/``activate_derived.py`` were split out earlier. This
is the only path for a *code* change to a frozen version: it retires the old
row (``deprecated`` + a ``changelog`` saying why) and creates ``version + 1``
carrying the **frozen row's own** ``parameters_schema``, ``default_parameters``
and ``params_format``, with the new ``code_ref``, both in one transaction.
Copying from the row rather than recomputing from code is the point: the
successor continues the frozen experiment, not today's code.

It refuses, on purpose, when the successor would only be a *parameter* change
(the ``code_ref`` already matches this build) — ``derive_variant.py`` and
``--deprecate`` (T3.39) are the paths for that.

Retiring the origin row is exactly what ``--deprecate`` does to a version with
no code successor, so it carries the same two structural refusals
(T3.39b review, ALTA-2 — one writer moving a frozen version off ``active``
cannot be looser than the other): ``purpose = 'live'`` is never touched, and
``purpose = 'paper'`` needs ``--force-paper`` *and* a clean
:func:`hunter_strategy_worker.activation_db.open_paper_exposure` check — the
wallet's own coorte does not lose its code successor while it is still
carrying open positions. ``purpose`` itself is copied onto the successor
**explicitly**: the ``INSERT`` used to omit the column, which meant every
successor of a paper line silently landed on the schema default
(``research_only``) and the wallet's coorte would have gone dark on its next
supersede.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.activation_db import (
    PURPOSE_LIVE,
    PURPOSE_PAPER,
    VERSION_RE,
    Refused,
    load_row,
    migration_applied,
    open_paper_exposure,
    record_event,
)
from hunter_strategy_worker.catalogue import resolve_strategy
from hunter_strategy_worker.code_ref import strategy_module, version_code_ref

__all__ = ["supersede"]


def _next_version(version: str) -> str:
    """``v1 -> v2``. Anything else is refused rather than guessed at."""
    match = VERSION_RE.fullmatch(version)
    if match is None:
        raise Refused(f"cannot derive the next version from {version!r}: expected 'v<n>'")
    return f"v{int(match.group(1)) + 1}"


async def supersede(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    *,
    dry_run: bool,
    registry: StrategyRegistry = DEFAULT_REGISTRY,
    force_paper: bool = False,
) -> str:
    """Retire a frozen version and activate its successor, in one transaction.

    The old row keeps every frozen field — the trigger would refuse anything
    else, and rewriting an experiment's identity is what the freeze exists to
    prevent. What moves to the successor is the experiment *content* read back
    from that row (schema, parameters, ``params_format``), so the only thing
    that actually changes is the ``code_ref`` and the version label.
    """
    if not await migration_applied(conn):
        raise Refused("0002_shadow_lab is not applied: apply the migration before superseding")
    row = await load_row(conn, key, version)
    if row is None:
        raise Refused(f"no strategy_version for {key} {version}")
    if row.purpose == PURPOSE_LIVE:
        raise Refused(
            f"{key} {version} carries purpose 'live': live é Fase 4; ENABLE_LIVE_TRADING=false. "
            "This script never retires a live version either, the same as it never activates one."
        )
    if row.purpose == PURPOSE_PAPER:
        if not force_paper:
            raise Refused(
                f"{key} {version} is the paper line (purpose 'paper'): superseding it retires "
                "the wallet's own coorte. Pass --force-paper to confirm, and only once its "
                "positions and shadow slots are clear (checked below)."
            )
        exposure = await open_paper_exposure(conn, row.id)
        if exposure:
            raise Refused(
                f"{key} {version} still has skin in the game: {'; '.join(exposure)}. "
                "Close or hand them off before superseding the paper line."
            )
    if row.activated_at is None:
        raise Refused(
            f"{key} {version} was never activated: nothing is frozen, activate it instead"
        )
    # Resolved the way the *worker* resolves it, not by ``(key, version)``: a
    # successor's version was bumped while its code stayed put, so ``v2`` has no
    # registry entry and only its frozen ``code_ref`` can name the module. This
    # is what lets a successor itself be superseded (Astra, S2 fixes diff
    # review, HIGH b).
    strategy = resolve_strategy(key, version, row.code_ref, registry)
    if strategy is None:
        raise Refused(
            f"this build cannot bind {key} {version} to code: neither the registry nor its "
            f"frozen code_ref ({row.code_ref}) names a module it carries"
        )
    code_ref = version_code_ref(strategy_module(strategy))
    if row.code_ref == code_ref:
        raise Refused(f"{key} {version} is already frozen against this code ({code_ref})")
    successor = _next_version(version)
    if await load_row(conn, key, successor) is not None:
        raise Refused(f"{key} {successor} already exists: it may already be the successor")
    schema: dict[str, Any] = dict(row.parameters_schema or {})
    params: dict[str, Any] = dict(row.default_parameters or {})
    report = validate_parameters(schema, params)
    if not report.ok:
        raise Refused(
            f"the frozen parameters of {key} {version} do not match its own schema: "
            + "; ".join(report.errors)
        )
    note = (
        f"superseded by {successor} (code_ref {row.code_ref} -> {code_ref}); frozen fields "
        f"cannot be corrected in place (DATABASE.md §16.1): {changelog}"
    )
    if dry_run:
        return f"would supersede {key} {version} with {successor} at code_ref {code_ref}"
    await conn.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version, status, "
            "parameters_schema, default_parameters, code_ref, params_format, purpose, "
            "changelog, activated_at) VALUES (gen_random_uuid(), :strategy_id, :version, "
            "'active', CAST(:schema AS jsonb), CAST(:params AS jsonb), :code_ref, "
            ":params_format, :purpose, :changelog, now())"
        ),
        {
            "strategy_id": row.strategy_id,
            "version": successor,
            "schema": json.dumps(schema, separators=(",", ":"), sort_keys=True),
            "params": json.dumps(params, separators=(",", ":"), sort_keys=True),
            "code_ref": code_ref,
            "params_format": row.params_format,
            "purpose": row.purpose,
            "changelog": f"succeeds {version}: {changelog}",
        },
    )
    await conn.execute(
        text(
            "UPDATE strategy_versions SET status = 'deprecated', deprecated_at = now(), "
            "changelog = :changelog WHERE id = :id"
        ),
        {"changelog": note, "id": row.id},
    )
    await record_event(
        conn,
        "info",
        "strategy_version_superseded",
        f"{key} {version} -> {successor} with code_ref={code_ref}: {changelog}",
    )
    return f"superseded {key} {version} with {successor} at code_ref {code_ref}"
