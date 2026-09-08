"""``--paper-line``: the paper coorte is *derived* from a frozen research version
(T3.15, D10 — ``.claude/state/decisions-delegated-2026-09-07.md``).

A new ``strategy_versions`` row, next free ``v<n>``, carrying the source row's
own ``parameters_schema``, ``default_parameters`` and ``params_format`` byte
for byte, the ``code_ref`` recomputed from the module the frozen digest names,
``status = 'draft'``, ``activated_at = NULL`` and ``purpose = 'paper'``. The
source row is not written to at all — the research coorte keeps running beside
the paper one — and **nothing is activated**: activating the derived line is a
later, separate, audited ``activate`` run, and D10 names the seven conditions
that come first. ``purpose`` is written only here, on the migration/owner
connection: ``0010_strategy_purpose`` revoked it from every application role.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.activation_db import (
    PURPOSE_PAPER,
    PURPOSE_RESEARCH_ONLY,
    Refused,
    load_row,
    migration_applied,
    next_free_version,
    purpose_column_present,
    record_event,
)
from hunter_strategy_worker.catalogue import resolve_strategy
from hunter_strategy_worker.code_ref import strategy_module, version_code_ref

__all__ = ["paper_line"]


async def paper_line(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    *,
    dry_run: bool,
    registry: StrategyRegistry = DEFAULT_REGISTRY,
) -> str:
    """Derive the paper coorte from a frozen research version. Returns a summary."""
    if not await migration_applied(conn):
        raise Refused("0002_shadow_lab is not applied: apply the migration before deriving")
    if not await purpose_column_present(conn):
        raise Refused("0010_strategy_purpose is not applied: apply the migration before deriving")
    row = await load_row(conn, key, version)
    if row is None:
        raise Refused(f"no strategy_version for {key} {version}")
    if row.activated_at is None:
        raise Refused(
            f"{key} {version} was never activated: a paper line copies a *frozen* coorte, "
            "activate the research version first"
        )
    if row.purpose != PURPOSE_RESEARCH_ONLY:
        raise Refused(
            f"{key} {version} carries purpose {row.purpose!r}: a paper line is derived from a "
            f"{PURPOSE_RESEARCH_ONLY!r} version only"
        )
    # OPEN POLICY QUESTION (T3.26c, review T3.26-risk): "frozen research_only"
    # is the *only* condition on the source. A research **variant** produced by
    # ``derive_variant.py`` satisfies it the moment it is activated, so a
    # parameter set that has never emitted a single prospective signal could
    # become a strategy's paper line tomorrow — which is not what D10 meant by
    # "prospective evidence first". Deliberately **not** fixed here: adding a
    # condition would decide, in code, a question that is Everton's (D10 names
    # the seven conditions, and this is an eighth). Written down rather than
    # silently accepted; see ``.claude/state/notes-T3.26.md`` §T3.26c.
    strategy = resolve_strategy(key, version, row.code_ref, registry)
    if strategy is None:
        raise Refused(
            f"this build cannot bind {key} {version} to code: neither the registry nor its "
            f"frozen code_ref ({row.code_ref}) names a module it carries"
        )
    code_ref = version_code_ref(strategy_module(strategy))
    if row.code_ref != code_ref:
        raise Refused(
            f"{key} {version} is frozen at code_ref {row.code_ref} but this build is {code_ref}: "
            "a paper line runs the very code the research coorte ran; supersede first or "
            "deploy the matching build"
        )
    schema: dict[str, Any] = dict(row.parameters_schema or {})
    params: dict[str, Any] = dict(row.default_parameters or {})
    report = validate_parameters(schema, params)
    if not report.ok:
        raise Refused(
            f"the frozen parameters of {key} {version} do not match its own schema: "
            + "; ".join(report.errors)
        )
    existing = await conn.scalar(
        text(
            "SELECT version FROM strategy_versions WHERE strategy_id = :strategy_id "
            "AND purpose = :purpose AND status <> 'deprecated' ORDER BY version LIMIT 1"
        ),
        {"strategy_id": row.strategy_id, "purpose": PURPOSE_PAPER},
    )
    if existing is not None:
        raise Refused(
            f"{key} already has a paper line that is not deprecated ({existing}); one paper "
            "coorte per strategy — deprecate it before deriving another"
        )
    successor = await next_free_version(conn, row.strategy_id)
    if dry_run:
        return (
            f"would derive {key} {successor} (purpose {PURPOSE_PAPER}, draft, not activated) "
            f"from {version} at code_ref {code_ref} ({len(params)} parameters copied)"
        )
    await conn.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version, status, "
            "parameters_schema, default_parameters, code_ref, params_format, changelog, "
            "activated_at, purpose) VALUES (gen_random_uuid(), :strategy_id, :version, 'draft', "
            "CAST(:schema AS jsonb), CAST(:params AS jsonb), :code_ref, :params_format, "
            ":changelog, NULL, :purpose)"
        ),
        {
            "strategy_id": row.strategy_id,
            "version": successor,
            "schema": json.dumps(schema, separators=(",", ":"), sort_keys=True),
            "params": json.dumps(params, separators=(",", ":"), sort_keys=True),
            "code_ref": code_ref,
            "params_format": row.params_format,
            "changelog": f"paper line of {version} (D10, T3.15): {changelog}",
            "purpose": PURPOSE_PAPER,
        },
    )
    await record_event(
        conn,
        "info",
        "strategy_version_paper_line_derived",
        f"{key} {successor} derived from {version} with purpose={PURPOSE_PAPER} "
        f"code_ref={code_ref}, draft, not activated: {changelog}",
    )
    return (
        f"derived {key} {successor} (purpose {PURPOSE_PAPER}, draft, not activated) "
        f"from {version} at code_ref {code_ref}"
    )
