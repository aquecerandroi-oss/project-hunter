"""H-037 task I, guardian findings F1 and F2: a copy bet is evidence and inventory of nobody else.

* F1 - the creator watch stamps ``creator_sold_seen_at`` on every open paper bet, and the
  pedigree's ``creator_prior_dump_count`` reads that stamp as "this creator dumped before". A
  copied leader may hold a coin the desk never watched; the stamp on the copy's bet must not make
  the creator's *next* coin a ``creator_repeat_dumper`` refusal on the real desk.
* F2 - ``tracker_pins`` pinned every open paper bet but the experiments', so up to 2 x 100 copy
  mints would stay tracked (``fold_minute`` keeps writing ``creator_sold``, the tape source of F1)
  and narrow everyone's cap. The copy lane prices from its own chain reads and needs no pin.

Both are proved against a real Postgres with an ordinary twin in the same query (the control).
The exclusion is by ``params.clock = 'copy'``, not by id: the seed does not exist yet.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.lab_repo_pedigree import pedigree_for
from hunter_meme_worker.tracker_pins import pinned_mints

from .test_lab_copy_isolation import (
    _make_copy,  # pyright: ignore[reportPrivateUsage]
    _two_open_bets,  # pyright: ignore[reportPrivateUsage]
    leave_no_open_bet,
)
from .test_lab_persistence import (
    NOW,
    WORKER,
    FakeQuotes,
    Heartbeats,
    _bet_of,  # pyright: ignore[reportPrivateUsage]
    _plant_curve,  # pyright: ignore[reportPrivateUsage]
    _rule_set,  # pyright: ignore[reportPrivateUsage]
    lab,
)

__all__ = ["lab", "leave_no_open_bet"]  # the fixtures travel with their modules

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from hunter_meme_worker.lab import LabContext

pytestmark = pytest.mark.integration


async def _two_bets_with_a_creator_sale(
    ctx: LabContext,
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    tag: str,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """``((copy mint, creator), (control mint, creator))``: each bet's coin has its own creator,
    and the watch has stamped the sale on both bets; then one of the two sets becomes a copy set."""
    (copy_mint, copy_prop), (ctrl_mint, ctrl_prop) = await _two_open_bets(ctx, factory, engine)
    out: list[tuple[str, str]] = []
    for mint, proposal, label in ((copy_mint, copy_prop, "c"), (ctrl_mint, ctrl_prop, "k")):
        creator = f"CRE{label}_{tag}"
        bet = await _bet_of(factory, proposal)
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE meme_tokens SET creator = :creator WHERE mint = :mint"),
                {"creator": creator, "mint": mint},
            )
            await connection.execute(
                text(
                    "UPDATE meme_paper_bets SET creator_sold_seen_at = entry_at + interval '5 seconds', "
                    "  creator_sold_fraction = 0.5 WHERE id = :id"
                ),
                {"id": bet["id"]},
            )
        out.append((mint, creator))
    return (out[0][0], out[0][1]), (out[1][0], out[1][1])


async def test_a_copy_bets_creator_sale_does_not_count_as_a_prior_dump(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    (_cm, copy_creator), (_km, ctrl_creator) = await _two_bets_with_a_creator_sale(
        ctx, db_session_factory, db_engine, "pedigree"
    )
    # the make-copy flip of ``_two_open_bets`` already happened: the first bet is the copy's
    next_coins = {
        copy_creator: f"NEXTC_{copy_creator}"[:40],
        ctrl_creator: f"NEXTK_{ctrl_creator}"[:40],
    }
    for creator, mint in next_coins.items():
        await _plant_curve(
            db_session_factory,
            mint,
            [],
            created_at=NOW,
            creator=creator,
            symbol=f"S{mint[-8:]}",
        )

    async with role_session(db_session_factory, db_role=WORKER) as session:
        read = await pedigree_for(session, list(next_coins.values()))

    assert read[next_coins[ctrl_creator]].creator_prior_dump_count == 1, "the control counts"
    assert read[next_coins[copy_creator]].creator_prior_dump_count == 0, "the copy's stamp does not"


async def test_an_open_copy_bet_pins_no_mint_and_an_ordinary_one_does(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    (copy_mint, _p1), (ctrl_mint, _p2) = await _two_open_bets(ctx, db_session_factory, db_engine)

    async with role_session(db_session_factory, db_role=WORKER) as session:
        pinned = await pinned_mints(session, now=NOW + timedelta(seconds=1))

    assert ctrl_mint in pinned, "the control: an open ordinary bet is still pinned"
    assert copy_mint not in pinned


async def test_a_waiting_copy_proposal_pins_no_mint(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint_ids: dict[str, str] = {}
    for label in ("copyp", "ctrlp"):
        rule_set = await _rule_set(db_engine, f"{label}_{uuid4().hex[:6]}")
        mint = f"{label.upper()}_PIN_{uuid4().hex[:6]}"
        mint_ids[label] = mint
        async with db_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, "
                    "  proposed_at, expires_at, features_end_time) VALUES (:id, :mint, :rs, "
                    "  'rules', 'proposed', :at, :exp, :minute)"
                ),
                {
                    "id": str(uuid4()),
                    "mint": mint,
                    "rs": rule_set,
                    "at": NOW,
                    "exp": NOW + timedelta(seconds=600),
                    "minute": NOW.replace(second=0, microsecond=0) - timedelta(minutes=3),
                },
            )
        if label == "copyp":
            await _make_copy(db_engine, rule_set)

    async with role_session(db_session_factory, db_role=WORKER) as session:
        pinned = await pinned_mints(session, now=NOW + timedelta(seconds=1))

    assert mint_ids["ctrlp"] in pinned and mint_ids["copyp"] not in pinned
