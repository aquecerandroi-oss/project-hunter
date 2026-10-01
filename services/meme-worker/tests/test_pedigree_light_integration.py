# pyright: reportPrivateUsage=false
"""EXP-M26 F (01/10/2026) against a real Postgres: the minute lane's light pedigree read.

Three things only a database proves: the light statement's *plan* never opens
``meme_features_1m`` or ``meme_paper_bets`` (the heavy subqueries are gone, not merely unread)
while the full statement's plan opens both; the light read returns the same two counts as the
full one and leaves the other two absent; and ``lineage_for`` sends a 15 s lane (the real
desk) to the unchanged full read and an all-``1m``, no-dumper lane (C/L/H) to the light one.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_indicators.meme.pedigree import PEDIGREE_V1, PedigreeFeatures
from hunter_meme_worker.lab_repo_e2b import lineage_for
from hunter_meme_worker.lab_repo_pedigree import (
    _PEDIGREE,
    _PEDIGREE_COUNTS,
    PRIOR_WINDOW_S,
    pedigree_for,
    pedigree_params,
)
from hunter_meme_worker.repo import upsert_token

from .test_lab_fast import (  # pyright: ignore[reportPrivateUsage]
    CREATED,
    WORKER,
    _plant_minute,
    _plant_token,
)
from .test_lab_persistence import _token  # pyright: ignore[reportPrivateUsage]
from .test_proposals import _row, _spec

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def _plant_serial_dumper(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[str, str]:
    """A creator with a prior coin that crashed and sold (outside the 1 h window), a
    clone-ticker neighbour, and the new coin judged. Returns ``(new, creator)``."""
    creator = f"C_{uuid4().hex[:8]}"
    old = f"OLD_{uuid4().hex[:8]}"
    new = f"NEW_{uuid4().hex[:8]}"
    twin = f"TW{uuid4().hex[:8]}"  # unique per test: the container is shared by the whole file
    old_created = CREATED - timedelta(hours=5)
    await _plant_token(factory, old, created_at=old_created, creator=creator, symbol=twin)
    await _plant_token(factory, new, created_at=CREATED, creator=creator, symbol=twin)
    await _plant_minute(
        factory, old, old_created + timedelta(minutes=5), mcap_sol="100", creator_sold=False
    )
    await _plant_minute(
        factory, old, old_created + timedelta(minutes=25), mcap_sol="10", creator_sold=True
    )
    return new, creator


def _relations(plan: Any) -> set[str]:
    """Every ``Relation Name`` in an ``EXPLAIN (FORMAT JSON)`` tree, sub-plans included."""
    found: set[str] = set()
    if isinstance(plan, dict):
        for key, value in plan.items():  # pyright: ignore[reportUnknownVariableType]
            if key == "Relation Name":
                found.add(str(value))  # pyright: ignore[reportUnknownArgumentType]
            else:
                found |= _relations(value)
    elif isinstance(plan, list):
        for item in plan:  # pyright: ignore[reportUnknownVariableType]
            found |= _relations(item)
    return found


async def test_the_light_plan_never_opens_the_heavy_tables_and_the_full_plan_does(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    new, _ = await _plant_serial_dumper(db_session_factory)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        light: Any = (
            await session.execute(
                text(f"EXPLAIN (FORMAT JSON) {_PEDIGREE_COUNTS.text}"),
                pedigree_params([new], PEDIGREE_V1, full=False),
            )
        ).scalar_one()
        full: Any = (
            await session.execute(
                text(f"EXPLAIN (FORMAT JSON) {_PEDIGREE.text}"),
                pedigree_params([new], PEDIGREE_V1, full=True),
            )
        ).scalar_one()
    light_tables, full_tables = _relations(light), _relations(full)
    assert light_tables == {"meme_tokens"}, light_tables
    assert any(t.startswith("meme_features_1m") for t in full_tables), full_tables
    assert "meme_paper_bets" in full_tables, full_tables


async def test_the_light_read_matches_the_full_one_on_the_two_counts_and_omits_the_rest(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    new, _ = await _plant_serial_dumper(db_session_factory)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        full = (await pedigree_for(session, [new]))[new]
        light = (await pedigree_for(session, [new], full=False))[new]
        frozen = (
            (await session.execute(_PEDIGREE, pedigree_params([new], PEDIGREE_V1, full=True)))
            .mappings()
            .one()
        )
    assert full.creator_prior_dump_count == 1 and full.creator_prior_dead_count == 1
    assert (light.creator_prior_mints_1h, light.symbol_dup_24h) == (0, 1)
    assert light == PedigreeFeatures(0, 1, None, None), "absent, never zero"
    assert (light.creator_prior_mints_1h, light.symbol_dup_24h) == (
        full.creator_prior_mints_1h,
        full.symbol_dup_24h,
    )
    # the 15 s read, byte for byte: the frozen statement, run raw, answers what pedigree_for gives
    assert full == PedigreeFeatures(
        creator_prior_mints_1h=int(frozen["creator_prior_mints_1h"]),
        symbol_dup_24h=int(frozen["symbol_dup_24h"]),
        creator_prior_dump_count=int(frozen["creator_prior_dump_count"]),
        creator_prior_dead_count=int(frozen["creator_prior_dead_count"]),
    )
    assert PRIOR_WINDOW_S == 7 * 86_400


async def test_an_unknown_identity_is_still_none_on_the_light_read(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``NULL`` creator/symbol stays ``None`` (``creator_unknown``/``symbol_unknown``), as before."""
    mint = f"NOID_{uuid4().hex[:8]}"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session, replace(_token(mint, created_at=CREATED), creator=None, symbol=None)
        )
        light = (await pedigree_for(session, [mint], full=False))[mint]
    assert light == PedigreeFeatures(None, None, None, None)


async def test_lineage_for_reads_full_on_the_15s_lane_and_light_on_the_mature_minute_lane(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    new, _ = await _plant_serial_dumper(db_session_factory)
    rows = [_row(mint=new)]
    mature = _spec(exp_ref="EXP-M26", pedigree_repeat_dumper=False, clock="1m")
    desk = _spec(clock="15s")
    async with role_session(db_session_factory, db_role=WORKER) as session:
        fast, _ = await lineage_for(session, rows, [desk])
        minute, _ = await lineage_for(session, rows, [mature])
        dumper_minute, _ = await lineage_for(
            session, rows, [mature, _spec(clock="1m", pedigree_repeat_dumper=True)]
        )
    assert fast[new].creator_prior_dump_count == 1 and fast[new].creator_prior_dead_count == 1
    assert minute[new].creator_prior_dump_count is None
    assert minute[new].creator_prior_dead_count is None
    assert (minute[new].creator_prior_mints_1h, minute[new].symbol_dup_24h) == (
        fast[new].creator_prior_mints_1h,
        fast[new].symbol_dup_24h,
    )
    assert dumper_minute[new] == fast[new], "a 1m set that asks for the dumper count gets it"
