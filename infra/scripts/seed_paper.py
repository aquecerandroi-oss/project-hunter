"""``paper_v1``: the virtual wallet's system preset — RISK_ENGINE.md §2.

Its own module for the reason ``seed_weights`` has one: this is not a plain
upsert. The three generic presets (``conservative``/``balanced``/``aggressive``)
are refreshed in place by ``seed.py`` because they are defaults nobody has
committed money to. ``paper_v1`` is different on both counts:

- **every number in it is Everton's**, written in the directive of 2026-09-06,
  and the contract says any change of value is a question to him
  (``docs/plans/M3.md`` → "Perguntas ao Everton antes de alterar qualquer
  limite"). A deploy that silently rewrote one would be exactly the change the
  contract forbids, made by nobody;
- it is a **template**, not a live profile. Organizations copy a system preset
  at onboarding (DATABASE.md §15.4), and an audited limit edit (§2.1) happens on
  the copy. So freezing the system row costs an operator nothing.

Its count is added to the ``risk_profiles`` total rather than reported under a
key of its own: every key of the seed's report is a *table name*, and
``test_schema_seed_and_partitions`` compares the report against the row counts
those tables actually hold.

Therefore the ``opportunity_weights`` rule of §17.8 applies: insert when missing,
*verify* when present, stop the seed on divergence with the instruction. Running
it twice rewrites nothing — the test compares ``xmin``, not row counts.
"""

from __future__ import annotations

from typing import Any

from seed_reference import PAPER_V1_LIMITS, PAPER_V1_NAME
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from hunter_core.db.models import RiskProfile
from hunter_core.domain.enums import RiskPreset
from hunter_core.domain.types import uuid7


def _differences(stored: dict[str, Any], shipped: dict[str, Any]) -> list[str]:
    """Keys whose value differs, plus keys missing on either side."""
    return sorted(
        key
        for key in set(stored) | set(shipped)
        if stored.get(key, "<absent>") != shipped.get(key, "<absent>")
    )


async def _refuse_diverging_preset(conn: AsyncConnection, shipped: dict[str, Any]) -> None:
    """A published ``paper_v1`` is frozen; a divergence stops the seed."""
    stored: dict[str, Any] | None = await conn.scalar(
        select(RiskProfile.limits).where(
            RiskProfile.organization_id.is_(None), RiskProfile.preset == RiskPreset.PAPER_V1
        )
    )
    if stored is None:
        return  # deleted between the insert and this read; the next run inserts it
    drift = _differences(stored, shipped)
    if drift:
        raise SystemExit(
            f"risk_profiles preset paper_v1 in the database differs from the directive "
            f"this build ships, on: {', '.join(drift)}. Every limit in paper_v1 is "
            f"Everton's, and RISK_ENGINE.md §2 makes changing one a question to him, not "
            f"a deploy. Reconcile the database (or the directive) deliberately; the seed "
            f"will not overwrite it."
        )


async def seed_paper_preset(conn: AsyncConnection) -> int:
    """Insert ``paper_v1`` when missing, verify it when present. Returns rows held.

    The count comes from the ``RETURNING`` of the insert or from a read of the
    database, never from a constant: a row a policy filtered away has to make the
    number go down (DATABASE.md §15.6, the ``risk_profiles`` bug).
    """
    limits: dict[str, Any] = dict(PAPER_V1_LIMITS)
    statement = insert(RiskProfile).values(
        id=uuid7(),
        organization_id=None,
        name=PAPER_V1_NAME,
        preset=RiskPreset.PAPER_V1,
        limits=limits,
    )
    result = await conn.execute(
        statement.on_conflict_do_nothing(
            index_elements=[RiskProfile.preset],
            index_where=RiskProfile.organization_id.is_(None),
        ).returning(RiskProfile.id)
    )
    if result.fetchall():
        return 1
    await _refuse_diverging_preset(conn, limits)
    present = await conn.execute(
        select(RiskProfile.id).where(
            RiskProfile.organization_id.is_(None), RiskProfile.preset == RiskPreset.PAPER_V1
        )
    )
    return len(present.fetchall())
