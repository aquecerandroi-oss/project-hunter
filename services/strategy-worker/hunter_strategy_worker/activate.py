"""The plain research activation — ``infra/scripts/activate_strategy_version.py``
with no mode flag.

Pulled out of the script for the 350-line budget, the same reason
``deprecate.py``/``supersede.py``/``paper_line.py``/``activate_derived.py``
were: this is the fifth mode to move. A row already carrying its own content
(a paper line, or a ``derive_variant.py`` variant) goes to
:func:`hunter_strategy_worker.activate_derived.activate_derived` instead — by
its declared marks first, structurally for a row whose marks were lost
(T3.15-risk item 1, T3.26-risk A1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hunter_core.strategies.canonical import PARAMS_FORMAT, canonical_json
from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_strategy_worker.activate_derived import (
    activate_derived,
    carries_own_content,
    refuse_rewriting_own_content,
)
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.activation_db import (
    PURPOSE_LIVE,
    Refused,
    load_row,
    migration_applied,
    note_provenance_data,
    purpose_column_present,
    record_event,
    require_note,
)
from hunter_strategy_worker.catalogue import registry_key, resolve_strategy
from hunter_strategy_worker.code_ref import strategy_module, version_code_ref
from hunter_strategy_worker.config import load_config
from hunter_strategy_worker.context_budget import ContextBudgetUnknown, over_ceiling

__all__ = ["activate"]


def _resolve(
    registry: StrategyRegistry, key: str, version: str, code_ref: str | None = None
) -> Any:
    """The registry first; then, for a row the registry does not name (a derived
    row keeps its source's code under a bumped version label), the module its
    frozen ``code_ref`` points at — as :func:`resolve_strategy` does."""
    code_key = registry_key(key, version)
    try:
        return registry.get(code_key, version)
    except KeyError as exc:
        if code_ref is not None:
            strategy = resolve_strategy(key, version, code_ref, registry)
            if strategy is not None:
                return strategy
        raise Refused(f"this build has no code registered as {code_key} {version}") from exc


def _refuse_unbudgeted_context(strategy: Any, row: Any) -> None:
    """Refuse a version whose 1m window does not fit ``SHADOW_CONTEXT_MAX_MINUTES``.

    T3.54b, and it is a lesson paid for: T3.54 activated two variants whose ATR
    window reached 5820 minutes back on a worker that loads at most a few
    thousand, and they answered ``unavailable: atr_warmup`` on all 5760 bars of
    their replay before anyone could tell why (notes-T3.54 §3.4). The check is
    arithmetic on the frozen parameters — the same function the worker uses —
    so a version that cannot decide is refused *before* it becomes an experiment
    with an empty population.

    Both activation paths pass through here (a derived row carries its own
    ``default_parameters``, which is what it will be evaluated with; a plain row
    is about to be frozen with this build's defaults), and the ceiling read is
    this process's environment: a worker deployed with a lower
    ``SHADOW_CONTEXT_MAX_MINUTES`` than the operator's shell would clamp and say
    so on every envelope, which is why the worker warns instead of going silent.

    Called only for a row not yet activated (T3.54c): an already-activated row
    reaching this function would mean re-running ``activate`` on a version that
    already decided under whatever context it was frozen with — the idempotent
    "nothing to do" reply both activation paths give for that case must stay a
    no-op even if ``SHADOW_CONTEXT_MAX_MINUTES`` has since been lowered under
    it. That case is not silent: the worker clamps and logs
    ``shadow_version_context_truncated`` on every envelope it produces.
    """
    params = dict(row.default_parameters or {}) or dict(strategy.default_parameters)
    try:
        refusal = over_ceiling(strategy, params, ceiling=load_config().context_max_minutes)
    except ContextBudgetUnknown as unsizable:
        raise Refused(str(unsizable)) from unsizable
    if refusal is not None:
        raise Refused(refusal)


async def activate(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    *,
    dry_run: bool,
    registry: StrategyRegistry = DEFAULT_REGISTRY,
    note: str | None = None,
    repo_root: Path | None = None,
) -> str:
    """Run every check and, unless ``dry_run``, activate. Returns a summary line.

    A row already carrying its own content goes to :func:`activate_derived`
    (T3.15-risk item 1) — by its declared marks first
    (:func:`carries_own_content`), and, for a row whose marks were lost,
    structurally (:func:`refuse_rewriting_own_content`, T3.26-risk A1).

    ``note`` (T4.93, "Obsidian primeiro") is required only once every other
    check has passed and a real write is about to happen — never for a
    no-op (already activated) or an earlier refusal.
    """
    if not await migration_applied(conn):
        raise Refused("0002_shadow_lab is not applied: apply the migration before activating")
    if not await purpose_column_present(conn):
        raise Refused("0010_strategy_purpose is not applied: apply the migration before activating")
    row = await load_row(conn, key, version)
    if row is None:
        raise Refused(f"no strategy_version for {key} {version} (run infra/scripts/seed.py first)")
    if row.purpose == PURPOSE_LIVE:
        raise Refused(
            f"{key} {version} carries purpose 'live': live é Fase 4; ENABLE_LIVE_TRADING=false. "
            "Nothing with that label is activated by this script."
        )
    strategy = _resolve(registry, key, version, row.code_ref)
    code_ref = version_code_ref(strategy_module(strategy))
    if row.activated_at is None:
        _refuse_unbudgeted_context(strategy, row)
    if carries_own_content(row):
        return await activate_derived(
            conn,
            key,
            version,
            changelog,
            row,
            code_ref=code_ref,
            dry_run=dry_run,
            note=note,
            repo_root=repo_root,
        )
    schema: dict[str, Any] = json.loads(canonical_json(dict(strategy.parameters_schema)))
    params: dict[str, Any] = json.loads(canonical_json(dict(strategy.default_parameters)))
    if row.activated_at is None:
        refuse_rewriting_own_content(key, version, row, params)
    report = validate_parameters(schema, params)
    if not report.ok:
        raise Refused(
            "default_parameters do not match parameters_schema: " + "; ".join(report.errors)
        )
    if row.activated_at is not None:
        if row.code_ref != code_ref:
            raise Refused(
                f"{key} {version} was activated at {row.activated_at.isoformat()} with "
                f"code_ref {row.code_ref}; this build is {code_ref}. A frozen version is "
                "never re-pointed at new code — publish a new version instead."
            )
        return f"{key} {version} was already activated at {row.activated_at.isoformat()}; nothing to do"
    if dry_run:
        return (
            f"would activate {key} {version} (purpose {row.purpose}) with code_ref {code_ref} "
            f"({len(params)} parameters)"
        )
    proof = require_note(key, version, note, repo_root=repo_root)
    updated = await conn.execute(
        text(
            "UPDATE strategy_versions SET status = 'active', activated_at = now(), "
            "code_ref = :code_ref, parameters_schema = CAST(:schema AS jsonb), "
            "default_parameters = CAST(:params AS jsonb), params_format = :params_format, "
            "changelog = :changelog "
            "WHERE id = :id AND activated_at IS NULL RETURNING activated_at"
        ),
        {
            "code_ref": code_ref,
            "schema": json.dumps(schema, separators=(",", ":"), sort_keys=True),
            "params": canonical_json(params).decode("utf-8"),
            "params_format": PARAMS_FORMAT,
            "changelog": changelog,
            "id": row.id,
        },
    )
    activated = updated.first()
    if activated is None:
        raise Refused(f"{key} {version} was activated concurrently; nothing was written")
    await record_event(
        conn,
        "info",
        "strategy_version_activated",
        f"{key} {version} (purpose {row.purpose}) activated with code_ref={code_ref} "
        f"params_format={PARAMS_FORMAT}: {changelog}",
        data=note_provenance_data(proof),
    )
    return (
        f"activated {key} {version} (purpose {row.purpose}) at {activated[0].isoformat()} "
        f"with code_ref {code_ref}"
    )
