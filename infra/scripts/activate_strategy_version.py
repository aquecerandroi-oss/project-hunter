"""Activate a Shadow Lab ``strategy_version`` — audited, and refusing on doubt.

    uv run python infra/scripts/activate_strategy_version.py momentum v1 \
        --changelog "S2 operational proof" [--dry-run]
    uv run python infra/scripts/activate_strategy_version.py momentum v1 --supersede \
        --changelog "code_ref per version (MUST-FIX 1)"

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
  (:mod:`hunter_strategy_worker.code_ref`, the same function and the same
  directory the worker uses — one resolution, no second answer).

``--supersede`` is the only way to move an *already frozen* version onto a new
digest: it retires the old row (``deprecated`` + a ``changelog`` saying why) and
creates ``version + 1`` carrying the **frozen row's own** ``parameters_schema``,
``default_parameters`` and ``params_format``, with the new ``code_ref``, both in
one transaction. Copying from the row rather than recomputing from code is the
point: the successor has to continue the experiment that was frozen, not
whatever the code says today.

Every run writes a ``system_events`` row, activation or refusal alike: an
experiment whose start nobody can date is not an experiment.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler), like
``infra/scripts/seed.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from hunter_core.settings import Settings
from hunter_core.strategies.canonical import PARAMS_FORMAT, canonical_json
from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.catalogue import registry_key, resolve_strategy
from hunter_strategy_worker.code_ref import strategy_module, version_code_ref

REQUIRED_TABLES = ("shadow_episodes", "shadow_outbox")
_VERSION_RE = re.compile(r"^v(\d+)$")


class Refused(RuntimeError):
    """A prerequisite failed; nothing was activated."""


async def _migration_applied(conn: AsyncConnection) -> bool:
    for table in REQUIRED_TABLES:
        if await conn.scalar(text("SELECT to_regclass(:name)"), {"name": table}) is None:
            return False
    column = await conn.scalar(
        text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_outcomes' "
            "AND column_name = 'tracking_state'"
        )
    )
    return column is not None


async def _record_event(conn: AsyncConnection, level: str, event: str, message: str) -> None:
    await conn.execute(
        text(
            "INSERT INTO system_events (id, created_at, level, component, event, message) "
            "VALUES (gen_random_uuid(), now(), CAST(:level AS event_severity), "
            "'activate_strategy_version', :event, :message)"
        ),
        {"level": level, "event": event, "message": message[:1000]},
    )


async def _load_row(conn: AsyncConnection, key: str, version: str) -> Any:
    return (
        await conn.execute(
            text(
                "SELECT v.id, v.strategy_id, v.status, v.activated_at, v.code_ref, "
                "v.default_parameters, v.parameters_schema, v.params_format "
                "FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id "
                "WHERE s.key = :key AND v.version = :version"
            ),
            {"key": key, "version": version},
        )
    ).first()


def _resolve(registry: StrategyRegistry, key: str, version: str) -> Any:
    code_key = registry_key(key, version)
    try:
        return registry.get(code_key, version)
    except KeyError as exc:
        raise Refused(f"this build has no code registered as {code_key} {version}") from exc


def _next_version(version: str) -> str:
    """``v1 -> v2``. Anything else is refused rather than guessed at."""
    match = _VERSION_RE.fullmatch(version)
    if match is None:
        raise Refused(f"cannot derive the next version from {version!r}: expected 'v<n>'")
    return f"v{int(match.group(1)) + 1}"


async def activate(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    *,
    dry_run: bool,
    registry: StrategyRegistry = DEFAULT_REGISTRY,
) -> str:
    """Run every check and, unless ``dry_run``, activate. Returns a summary line."""
    if not await _migration_applied(conn):
        raise Refused("0002_shadow_lab is not applied: apply the migration before activating")
    row = await _load_row(conn, key, version)
    if row is None:
        raise Refused(f"no strategy_version for {key} {version} (run infra/scripts/seed.py first)")
    strategy = _resolve(registry, key, version)
    code_ref = version_code_ref(strategy_module(strategy))
    schema: dict[str, Any] = json.loads(canonical_json(dict(strategy.parameters_schema)))
    params: dict[str, Any] = json.loads(canonical_json(dict(strategy.default_parameters)))
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
        return f"would activate {key} {version} with code_ref {code_ref} ({len(params)} parameters)"
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
    await _record_event(
        conn,
        "info",
        "strategy_version_activated",
        f"{key} {version} activated with code_ref={code_ref} params_format={PARAMS_FORMAT}: {changelog}",
    )
    return f"activated {key} {version} at {activated[0].isoformat()} with code_ref {code_ref}"


async def supersede(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    *,
    dry_run: bool,
    registry: StrategyRegistry = DEFAULT_REGISTRY,
) -> str:
    """Retire a frozen version and activate its successor, in one transaction.

    The old row keeps every frozen field — the trigger would refuse anything
    else, and rewriting an experiment's identity is what the freeze exists to
    prevent. What moves to the successor is the experiment *content* read back
    from that row (schema, parameters, ``params_format``), so the only thing
    that actually changes is the ``code_ref`` and the version label.
    """
    if not await _migration_applied(conn):
        raise Refused("0002_shadow_lab is not applied: apply the migration before superseding")
    row = await _load_row(conn, key, version)
    if row is None:
        raise Refused(f"no strategy_version for {key} {version}")
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
    if await _load_row(conn, key, successor) is not None:
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
            "parameters_schema, default_parameters, code_ref, params_format, changelog, "
            "activated_at) VALUES (gen_random_uuid(), :strategy_id, :version, 'active', "
            "CAST(:schema AS jsonb), CAST(:params AS jsonb), :code_ref, :params_format, "
            ":changelog, now())"
        ),
        {
            "strategy_id": row.strategy_id,
            "version": successor,
            "schema": json.dumps(schema, separators=(",", ":"), sort_keys=True),
            "params": json.dumps(params, separators=(",", ":"), sort_keys=True),
            "code_ref": code_ref,
            "params_format": row.params_format,
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
    await _record_event(
        conn,
        "info",
        "strategy_version_superseded",
        f"{key} {version} -> {successor} with code_ref={code_ref}: {changelog}",
    )
    return f"superseded {key} {version} with {successor} at code_ref {code_ref}"


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver (as ``seed.py`` does)."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def _run(args: argparse.Namespace) -> int:
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn, conn.begin():
            action = supersede if args.supersede else activate
            try:
                message = await action(
                    conn, args.strategy, args.version, args.changelog, dry_run=args.dry_run
                )
            except Refused as refusal:
                await _record_event(
                    conn, "warning", "strategy_version_activation_refused", str(refusal)
                )
                print(f"REFUSED: {refusal}", file=sys.stderr)
                return 1
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
    parser.add_argument(
        "--supersede",
        action="store_true",
        help="retire this frozen version and activate version+1 with the current code_ref",
    )
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
