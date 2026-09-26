"""T4.95 (EXP-M25): ``recuo_ctrl_v1/1`` — the immediate-entry control of
``recuo_v1/1`` (``0065``) — can never change what the desk reads, the same two
subtractions T4.91 made for the arm (``test_event_gate_pullback_review``):

- its paper bets are subtracted from the desk's pedigree read — the control
  enters on decisions the real desk **refused** (122 of 171 in R79), so its
  bets make the creator watcher stamp ``creator_sold_seen_at`` on mints the
  desk never held; counted, they would change ``operator/5``'s
  ``creator_repeat_dumper`` refusals;
- its open bets never pin a mint in the tracker — a pin keeps folding
  ``meme_features_1m`` rows (``creator_sold`` among them, the pedigree source no
  id can subtract) and narrows the tracker's cap for everyone.

And the pair itself, through the real event lane (Astra, T4.95 diff review):
one evaluation arms the arm and proposes the control at the same ``t0``.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hunter_core.db.session import role_session
from hunter_meme_worker import lab_repo_fast
from hunter_meme_worker.entry_pullback import PULLBACK_CONTROL_RULE_SET_ID
from hunter_meme_worker.event_gate_eval import evaluate_mint
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.lab_repo_fast import pedigree_for
from hunter_meme_worker.tracker_pins import pinned_mints

from .test_event_gate_integration import (
    WORKER,
    _lab,
    _patch_holders,
    _prime_state,
    _radar,
    _rt,
    _seed_caches,
)
from .test_event_gate_pullback_integration import T0
from .test_lab_fast import _plant_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, async_sessionmaker

OPERATOR_5 = "01994d00-6c1a-7000-8000-000000000011"
CREATED = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

_APPROVED = text(
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, decision, "
    "  decided_by, decided_at) VALUES (:id, :mint, :rs, 'operator', 'approved', "
    "  now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = text(
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params, creator_sold_seen_at, creator_sold_fraction) VALUES (:id, :p, "
    "  :rs, :mint, 'paper', :entry_at, '{}'::jsonb, 0.07, '{}'::jsonb, :seen, :fraction)"
)


async def _bet(
    connection: AsyncConnection, mint: str, rule_set: str, *, seen: datetime | None = None
) -> None:
    proposal = str(uuid4())
    await connection.execute(_APPROVED, {"id": proposal, "mint": mint, "rs": rule_set})
    await connection.execute(
        _A_BET,
        {
            "id": str(uuid4()),
            "p": proposal,
            "rs": rule_set,
            "mint": mint,
            "entry_at": (seen or CREATED) - timedelta(seconds=30),
            "seen": seen,
            "fraction": None if seen is None else 0.5,
        },
    )


def test_the_desks_pedigree_names_the_control_in_both_subqueries() -> None:
    sql = str(lab_repo_fast._PEDIGREE)
    assert sql.count("pb.rule_set_id <> :pullback_control_rule_set_id") == 1
    assert sql.count("pb2.rule_set_id <> :pullback_control_rule_set_id") == 1
    assert PULLBACK_CONTROL_RULE_SET_ID == "01994d00-6c1a-7000-8000-00000000001e", "0065's own id"


@pytest.mark.integration
async def test_a_creator_sale_only_the_control_witnessed_never_reaches_the_desk(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """Behaviour, not text: the same witnessed sale counts once when a desk
    bet saw it and zero times when only the control's bet did."""
    tag = uuid4().hex[:8]
    creator, prior, new = f"C_{tag}", f"PRIOR_{tag}", f"NEW_{tag}"
    await _plant_token(
        db_session_factory,
        prior,
        created_at=CREATED - timedelta(hours=2),
        creator=creator,
        symbol=f"P{tag[:4]}",
    )
    await _plant_token(db_session_factory, new, created_at=CREATED, creator=creator, symbol="NW")
    seen = CREATED - timedelta(hours=1)
    counts: list[int | None] = []
    for witnesses in ((PULLBACK_CONTROL_RULE_SET_ID,), (PULLBACK_CONTROL_RULE_SET_ID, OPERATOR_5)):
        async with db_engine.connect() as connection:
            transaction = await connection.begin()
            try:
                for rule_set in witnesses:
                    await _bet(connection, prior, rule_set, seen=seen)
                session = AsyncSession(bind=connection)
                pedigree = await pedigree_for(session, [new])
                await session.close()
            finally:
                await transaction.rollback()
        counts.append(pedigree[new].creator_prior_dump_count)
    assert counts == [0, 1], "the control's witness is subtracted; the desk's is not"


@pytest.mark.integration
async def test_the_controls_open_bets_never_pin_a_mint(db_engine: AsyncEngine) -> None:
    control_mint, desk_mint = f"CTRLPIN_{uuid4().hex[:8]}", f"DESKPIN_{uuid4().hex[:8]}"
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await _bet(connection, control_mint, PULLBACK_CONTROL_RULE_SET_ID)
            await _bet(connection, desk_mint, OPERATOR_5)
            session = AsyncSession(bind=connection)
            pinned = await pinned_mints(session, now=CREATED.replace(year=2000))
            await session.close()
        finally:
            await transaction.rollback()
    assert desk_mint in pinned
    assert control_mint not in pinned


async def _arm_and_control(engine: AsyncEngine, seeded: str) -> tuple[str, str]:
    """``seeded`` becomes a pullback arm; its control is ``0065``'s own copy:
    the arm's document minus the two pullback keys."""
    control = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_rule_sets SET params = params || "
                '\'{"entry_pullback_pct": "5", "entry_pullback_window_s": 60}\'::jsonb '
                "WHERE id = :a"
            ),
            {"a": seeded},
        )
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "SELECT :c, :name, '1', 'research_only', "
                "  params - ARRAY['entry_pullback_pct', 'entry_pullback_window_s']::text[], "
                "  code_ref, 'EXP-M25' FROM meme_rule_sets WHERE id = :a"
            ),
            {"c": control, "name": f"ctrl_test_{uuid4().hex[:8]}", "a": seeded},
        )
    return seeded, control


async def _control_rows(
    factory: async_sessionmaker[AsyncSession], control: str, mint: str
) -> list[tuple[str, datetime, str]]:
    async with role_session(factory, db_role=WORKER) as session:
        rows = await session.execute(
            text(
                "SELECT status, features_end_time, decided_by FROM meme_proposals "
                "WHERE rule_set_id = CAST(:c AS uuid) AND mint = :m"
            ),
            {"c": control, "m": mint},
        )
        return [(str(r[0]), r[1], str(r[2])) for r in rows]


@pytest.mark.integration
@pytest.mark.parametrize("control_already_holds_the_mint", [False, True])
async def test_every_arming_gets_its_control_at_the_same_t0_unless_the_control_holds_the_mint(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    control_already_holds_the_mint: bool,
) -> None:
    """Astra (T4.95 diff review): the pair, through the real event lane — one
    ``evaluate_mint`` arms the arm and proposes the control at the same
    ``features_end_time``, approved by ``rules`` (paper). The exclusion EXP-M25
    counts: a control that already holds the mint (e.g. the 15-second lane got
    there first) proposes nothing at ``t0`` while the arm still arms."""
    mint = f"PAIRC_{uuid4().hex[:10]}"
    lab = _lab(db_session_factory)
    arm, control = await _arm_and_control(
        db_engine, await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
    )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        by_id = {s.id: s for s in await load_active_rule_sets(session)}
    assert by_id[control].entry_pullback is None and by_id[arm].entry_pullback is not None
    assert lab.caches is not None
    lab.caches.specs = (by_id[control], by_id[arm])
    if control_already_holds_the_mint:
        lab.caches.open_mints = {control: frozenset({mint})}
    rt = _rt(_radar(db_session_factory), lab)
    _prime_state(rt, mint, as_of=T0)
    _patch_holders(monkeypatch, mint, T0)
    await evaluate_mint(rt, mint, T0)
    assert rt.pullback.armed == 1, "the arm armed at t0"
    rows = await _control_rows(db_session_factory, control, mint)
    if control_already_holds_the_mint:
        assert rows == [], "no pair at t0 - out of both sides, counted"
    else:
        assert rows == [("approved", T0, "rules")], "the pair: same mint, same t0, paper"
