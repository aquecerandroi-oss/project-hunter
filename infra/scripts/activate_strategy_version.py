"""Activate a Shadow Lab ``strategy_version`` — audited, and refusing on doubt.

    uv run python infra/scripts/activate_strategy_version.py momentum v1 \
        --changelog "S2 operational proof" [--dry-run]
    uv run python infra/scripts/activate_strategy_version.py momentum v1 --supersede \
        --changelog "code_ref per version (MUST-FIX 1)"
    uv run python infra/scripts/activate_strategy_version.py momentum v1 --paper-line \
        --changelog "D10: the paper coorte" [--dry-run]
    uv run python infra/scripts/activate_strategy_version.py breakout v1 --deprecate \
        --changelog "K1: 0 decisions" [--successor v2] [--dry-run]

``--deprecate`` (T3.39) sets ``status = 'deprecated'`` on an ``active`` row —
the audited path for a version whose successor is a *parameter* variant
(``derive_variant.py``), or that has no successor at all: ``--supersede``
refuses both, on purpose, because it exists for a *code* change. ``status`` is
the one field the freeze trigger leaves mutable, so nothing frozen moves.
Refuses a ``purpose = 'live'`` row outright, and a ``purpose = 'paper'`` row
unless ``--force-paper`` is given *and* it carries no open ``positions`` or
``shadow_episodes`` slot (:mod:`hunter_strategy_worker.deprecate`).

The first activation is irreversible by design (docs/DATABASE.md §16.1): the
``0002_shadow_lab`` trigger freezes ``code_ref``, ``parameters_schema``,
``default_parameters``, ``params_format`` and ``activated_at`` for good. So this
script writes the definitive values **in the same statement** that sets
``activated_at``, and refuses — loudly, with a non-zero exit — if any of the
prerequisites is not met:

- ``0002_shadow_lab`` applied (``shadow_episodes``, ``shadow_outbox``,
  ``signal_outcomes.tracking_state``);
- this build carries the code for ``(key, version)`` in
  ``hunter_core.strategies.registry``;
- ``default_parameters`` validate against the version's ``parameters_schema``;
- the per-version ``code_ref`` digest can be computed
  (:mod:`hunter_strategy_worker.code_ref`, one resolution, no second answer).

``--supersede`` is the only way to move an *already frozen* version onto a new
digest: it retires the old row (``deprecated`` + a ``changelog`` saying why) and
creates ``version + 1`` carrying the **frozen row's own** ``parameters_schema``,
``default_parameters``, ``params_format`` and ``purpose``, with the new
``code_ref``, both in one transaction. Copying from the row rather than
recomputing from code is the point: the successor continues the frozen
experiment, not today's code — a paper line's successor stays ``purpose =
'paper'``, never the schema default. Retiring the origin carries the same two
structural refusals as ``--deprecate`` (T3.39b review, ALTA-2): ``purpose =
'live'`` is never touched, and ``purpose = 'paper'`` needs ``--force-paper``
*and* a clean ``positions``/``shadow_episodes`` check.

``--paper-line`` (T3.15, D10) derives the coorte that may reach the paper wallet
from a **frozen** ``research_only`` version: a *new* draft row, next free
``v<n>``, with that row's own content byte for byte and ``purpose = 'paper'``;
the source is untouched and nothing is activated (``paper_line.py``). A row that
already carries **its own content** (a paper line, or a research variant of
``infra/scripts/derive_variant.py``, T3.26) is activated by
:mod:`hunter_strategy_worker.activate_derived` — only ``status``, ``activated_at``
and ``changelog`` move; the plain research path would rewrite its parameters
from *today's* code and freeze the wrong experiment (review T3.15-risk).

Recognising such a row has **two** layers, because the first one can be erased:
``carries_own_content`` reads ``purpose`` and the deriving tool's phrase in the
``changelog`` (a column no trigger freezes), and
``refuse_rewriting_own_content`` refuses structurally — a draft whose
``default_parameters`` are non-empty and are not this code's own set is never
rewritten, whatever its changelog says (review T3.26-risk, A1).

Every run writes a ``system_events`` row — activation, refusal or an unexpected
failure alike (T3.15c): an experiment whose start nobody can date is not one.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler), like
``infra/scripts/seed.py``. Shared checks in :mod:`hunter_strategy_worker.activation_db`;
``--supersede``, ``--paper-line``, derived activation and ``--deprecate`` each live in
their own module (``supersede``/``paper_line``/``activate_derived``/``deprecate``) — the
350-line budget split them out one at a time as each mode was added.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

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
    migration_url,
    purpose_column_present,
    record_event,
    record_failure,
)
from hunter_strategy_worker.catalogue import registry_key, resolve_strategy
from hunter_strategy_worker.code_ref import strategy_module, version_code_ref
from hunter_strategy_worker.config import load_config
from hunter_strategy_worker.context_budget import ContextBudgetUnknown, over_ceiling
from hunter_strategy_worker.deprecate import deprecate
from hunter_strategy_worker.paper_line import paper_line
from hunter_strategy_worker.supersede import supersede

__all__ = ["Refused", "activate", "deprecate", "main", "paper_line", "supersede"]


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
) -> str:
    """Run every check and, unless ``dry_run``, activate. Returns a summary line.

    A row already carrying its own content goes to :func:`activate_derived`
    (T3.15-risk item 1) — by its declared marks first
    (:func:`carries_own_content`), and, for a row whose marks were lost,
    structurally (:func:`refuse_rewriting_own_content`, T3.26-risk A1).
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
            conn, key, version, changelog, row, code_ref=code_ref, dry_run=dry_run
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
    )
    return (
        f"activated {key} {version} (purpose {row.purpose}) at {activated[0].isoformat()} "
        f"with code_ref {code_ref}"
    )


async def _run(args: argparse.Namespace) -> int:
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        try:
            async with engine.connect() as conn, conn.begin():
                if getattr(args, "deprecate", False):
                    message = await deprecate(
                        conn,
                        args.strategy,
                        args.version,
                        args.changelog,
                        dry_run=args.dry_run,
                        successor=getattr(args, "successor", None),
                        force_paper=getattr(args, "force_paper", False),
                    )
                elif getattr(args, "supersede", False):
                    message = await supersede(
                        conn,
                        args.strategy,
                        args.version,
                        args.changelog,
                        dry_run=args.dry_run,
                        force_paper=getattr(args, "force_paper", False),
                    )
                else:
                    action = paper_line if args.paper_line else activate
                    message = await action(
                        conn, args.strategy, args.version, args.changelog, dry_run=args.dry_run
                    )
        except Refused as refusal:
            await record_failure(
                engine, "warning", "strategy_version_activation_refused", str(refusal)
            )
            print(f"REFUSED: {refusal}", file=sys.stderr)
            return 1
        except Exception as exc:
            # Every run leaves a system_events row, not only a named refusal
            # (T3.15c, security review T3.15 MEDIUM 5).
            print(f"ERROR: {exc}", file=sys.stderr)
            await record_failure(engine, "error", "strategy_version_activation_error", str(exc))
            raise SystemExit(2) from exc
        print(message)
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strategy", help="strategies.key, e.g. momentum")
    parser.add_argument("version", help="strategy_versions.version, e.g. v1")
    parser.add_argument("--changelog", required=True, help="why this version is being activated")
    parser.add_argument("--dry-run", action="store_true", help="run every check, write nothing")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--supersede",
        action="store_true",
        help="retire this frozen version and activate version+1 with the current code_ref",
    )
    mode.add_argument(
        "--paper-line",
        action="store_true",
        help="derive a draft purpose=paper line (next free v<n>) from this frozen research "
        "version; activates nothing (T3.15, D10)",
    )
    mode.add_argument(
        "--deprecate",
        action="store_true",
        help="set status=deprecated on this active version (T3.39); refuses purpose=live, and "
        "refuses purpose=paper without --force-paper and a clean positions/shadow_episodes check",
    )
    parser.add_argument(
        "--successor",
        default=None,
        help="--deprecate only: the version (v<n>) that replaces this one, named in the audit "
        "trail; must already exist",
    )
    parser.add_argument(
        "--force-paper",
        action="store_true",
        help="--deprecate/--supersede only: required to retire a purpose=paper version",
    )
    args = parser.parse_args()
    if args.successor is not None and not args.deprecate:
        parser.error("--successor requires --deprecate")
    if args.force_paper and not (args.deprecate or args.supersede):
        parser.error("--force-paper requires --deprecate or --supersede")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
