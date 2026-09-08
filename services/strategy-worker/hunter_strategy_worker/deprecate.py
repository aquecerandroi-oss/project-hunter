"""``--deprecate``: retire an ``active`` version through an audited status change.

Pulled out of ``infra/scripts/activate_strategy_version.py`` for the same
reason ``paper_line.py``/``activate_derived.py`` were (T3.39, the 350-line
budget). Until now there was no audited way to retire a version whose
successor is a **parameter** variant (``derive_variant.py``, T3.26) — only
``--supersede`` moves a frozen version forward, and it refuses on purpose when
the successor is not a *code* change ("already frozen against this code").
``--deprecate`` is the missing half: it writes only ``status``/``deprecated_at``/
``changelog`` (the freeze trigger leaves ``status`` mutable, DATABASE.md
§16.1) and never touches ``code_ref``, parameters or the schema.

Two refusals are structural, not configurable:

- ``purpose = 'live'`` is never deprecated by this script — the same rule
  ``activate()`` applies to activation, mirrored here so a live row is never
  written by this tool in either direction (live is Phase 4;
  ``ENABLE_LIVE_TRADING=false``);
- ``purpose = 'paper'`` (the wallet's own coorte) needs ``--force-paper`` *and*
  a clean check of ``positions``/``shadow_episodes`` — retiring the line the
  wallet is actually running is not the same act as retiring an idle research
  row, and the risk-engine-guardian's review of this task named exactly this
  case ("a version being deprecated must never be the paper line with open
  positions").

``--successor`` is purely a note for the audit trail (a parameter variant like
``derive_variant.py`` produces is *not* activated by this tool — it is its own
audited ``activate`` run): when given, the named version must already exist,
so the record never claims a successor that a typo invented.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hunter_core.strategies.canonical import params_hash
from hunter_strategy_worker.activation_db import (
    PURPOSE_LIVE,
    PURPOSE_PAPER,
    Refused,
    load_row,
    migration_applied,
    open_paper_exposure,
    purpose_column_present,
    record_event,
)

__all__ = ["deprecate"]


async def deprecate(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    *,
    dry_run: bool,
    successor: str | None = None,
    force_paper: bool = False,
) -> str:
    """Set ``status = 'deprecated'`` on an ``active`` version. Returns a summary."""
    if not await migration_applied(conn):
        raise Refused("0002_shadow_lab is not applied: apply the migration before deprecating")
    if not await purpose_column_present(conn):
        raise Refused(
            "0010_strategy_purpose is not applied: apply the migration before deprecating"
        )
    row = await load_row(conn, key, version)
    if row is None:
        raise Refused(f"no strategy_version for {key} {version}")
    if row.status != "active":
        raise Refused(f"{key} {version} is {row.status!r}, not active: nothing to deprecate")
    if row.purpose == PURPOSE_LIVE:
        raise Refused(
            f"{key} {version} carries purpose 'live': live é Fase 4; ENABLE_LIVE_TRADING=false. "
            "This script never deprecates a live version either, the same as it never activates one."
        )
    if row.purpose == PURPOSE_PAPER:
        if not force_paper:
            raise Refused(
                f"{key} {version} is the paper line (purpose 'paper'): deprecating it stops "
                "the wallet's own coorte. Pass --force-paper to confirm, and only once its "
                "positions and shadow slots are clear (checked below)."
            )
        exposure = await open_paper_exposure(conn, row.id)
        if exposure:
            raise Refused(
                f"{key} {version} still has skin in the game: {'; '.join(exposure)}. "
                "Close or hand them off before deprecating the paper line."
            )
    if successor is not None and await load_row(conn, key, successor) is None:
        raise Refused(f"successor {key} {successor} does not exist")
    frozen_hash = params_hash(dict(row.default_parameters or {}))
    successor_note = f"successor={key} {successor}" if successor is not None else "successor=none"
    if dry_run:
        return (
            f"would deprecate {key} {version} (purpose {row.purpose}), code_ref {row.code_ref}, "
            f"params_hash {frozen_hash[:12]}, {successor_note}: {changelog}"
        )
    updated = await conn.execute(
        text(
            "UPDATE strategy_versions SET status = 'deprecated', deprecated_at = now(), "
            "changelog = :changelog WHERE id = :id AND status = 'active' "
            "RETURNING deprecated_at"
        ),
        {"changelog": changelog, "id": row.id},
    )
    deprecated = updated.first()
    if deprecated is None:
        raise Refused(f"{key} {version} was changed concurrently; nothing was written")
    await record_event(
        conn,
        "info",
        "strategy_version_deprecated",
        f"{key} {version} (purpose {row.purpose}) deprecated at {deprecated[0].isoformat()}, "
        f"code_ref={row.code_ref} params_hash={frozen_hash} params_format={row.params_format} "
        f"{successor_note}: {changelog}",
    )
    return f"deprecated {key} {version} (purpose {row.purpose}) at {deprecated[0].isoformat()}, {successor_note}"
