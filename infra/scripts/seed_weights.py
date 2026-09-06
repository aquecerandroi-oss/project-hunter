"""``opportunity_weights``: publish the profiles, promote the active one once.

Its own module because it is the only part of the seed that is not a plain
upsert. Two rules make it different, both recorded in DATABASE.md §17.8:

- **a published weight vector is frozen.** Every opportunity records
  ``weights_version``, so rewriting the numbers under an existing name changes
  the meaning of scores already explained by it. Missing versions are inserted;
  existing ones are *verified*, and a divergence stops the seed.
- **``is_active`` is written on exactly one run** in a database's life — the one
  whose ``INSERT`` actually created the release's profile. Which version is live
  is an operational decision (a rollback after a bad tuning), and every deploy
  re-runs this script.
"""

from __future__ import annotations

from typing import Any

from seed_reference import ACTIVE_WEIGHTS_VERSION, OPPORTUNITY_WEIGHTS, PROMOTED_FROM
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from hunter_core.db.models import OpportunityWeights
from hunter_core.domain.types import uuid7


async def _promote_active_weights(conn: AsyncConnection) -> None:
    """Retire the previous profile and activate this release's — DATABASE.md §17.8.

    The partial unique index allows one active version at a time, so
    retire-then-activate is the only order that does not fail the deploy. A live
    version outside :data:`PROMOTED_FROM` is left alone: taking the profile away
    from a running scorer is not a deploy script's decision.
    """
    live: str | None = await conn.scalar(
        text("SELECT version FROM opportunity_weights WHERE is_active")
    )
    if live is not None and live not in PROMOTED_FROM:
        return
    if live is not None:
        await conn.execute(
            text("UPDATE opportunity_weights SET is_active = false WHERE version = :version"),
            {"version": live},
        )
    await conn.execute(
        text("UPDATE opportunity_weights SET is_active = true WHERE version = :version"),
        {"version": ACTIVE_WEIGHTS_VERSION},
    )


async def _refuse_diverging_weights(conn: AsyncConnection, version: str, shipped: Any) -> None:
    """A published weight vector is frozen, like a ``strategy_version`` (§17.8).

    Every opportunity records ``weights_version``, so rewriting the vector under
    that name changes the meaning of scores already explained by it. The seed
    inserts a missing version and *verifies* an existing one. Concrete
    regression closed: T2.4 ratifies v2 with ``components_frozen: true`` and the
    next deploy quietly puts ``false`` back.
    """
    stored = await conn.scalar(
        text("SELECT weights FROM opportunity_weights WHERE version = :version"),
        {"version": version},
    )
    if stored != shipped:
        raise SystemExit(
            f"opportunity_weights {version} in the database differs from the vector this "
            f"release ships, and a published weight version is never rewritten: every "
            f"score naming {version} was produced by the stored one. Publish the new "
            f"numbers as a new version instead."
        )


async def seed_opportunity_weights(conn: AsyncConnection) -> int:
    """Insert missing profiles, verify existing ones, promote the active one once.

    ``is_active`` is written on exactly one run in a database's life: the one
    whose ``INSERT`` created :data:`ACTIVE_WEIGHTS_VERSION`. Deciding from
    ``ON CONFLICT DO NOTHING ... RETURNING`` rather than an earlier ``SELECT``
    makes that race-free — whoever created the row first wins, and this run
    conflicts, returns nothing and promotes nothing.
    """
    created: set[str] = set()
    for version, weights, description in OPPORTUNITY_WEIGHTS:
        statement = insert(OpportunityWeights).values(
            id=uuid7(),
            version=version,
            weights=weights,
            is_active=False,
            description=description,
        )
        result = await conn.execute(
            statement.on_conflict_do_nothing(index_elements=[OpportunityWeights.version]).returning(
                OpportunityWeights.version
            )
        )
        if result.fetchall():
            created.add(version)
        else:
            await _refuse_diverging_weights(conn, version, weights)

    if ACTIVE_WEIGHTS_VERSION in created:
        await _promote_active_weights(conn)

    present = await conn.execute(
        text("SELECT id FROM opportunity_weights WHERE version = ANY(:versions)"),
        {"versions": [version for version, _weights, _description in OPPORTUNITY_WEIGHTS]},
    )
    # Counted from what the database actually holds and lets us see, never from
    # the length of the input tuple - the doctrine ``seed.py::_written`` states.
    return len(present.fetchall())
