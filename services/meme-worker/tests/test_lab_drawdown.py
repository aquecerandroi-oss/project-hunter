# pyright: reportPrivateUsage=false
"""T4.61a against a real Postgres at ``head`` — EXP-M13's guard on the
15-second lane, end to end: the ``0052`` seed parses into ``flow_v2/9`` with
the guard on; a set carrying ``max_recent_drawdown_pct`` refuses a 15-second
row whose curve just lost 82 % of its real SOL (``recent_drawdown``, with the
number and the ceiling on the refusal trail) and proposes on a clean twin;
the read behind it is one bounded query per tick on the partition-local
children of ``ix_meme_curve_snapshots_mint_observed``, never a Seq Scan.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.lab import LabContext, LabState, lab_tick
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.lab_repo_drawdown import _RESERVES, FILL_LOOKBACK_S, reserve_points_for
from hunter_meme_worker.lab_repo_fast import load_fast_gate_rows
from hunter_meme_worker.repo_fast import insert_fast_rows

from .test_lab_fast import CREATED, _fast_row
from .test_lab_persistence import FakeQuotes, Heartbeats, _one, _plant_curve

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
FLOW_V2_ID = "01994d00-6c1a-7000-8000-000000000008"
"""``flow_v2/1`` (``0030``): the flow gate the fixture row of ``test_lab_fast``
already passes — this file's own set is that one plus the guard."""
AFTER_DROP_ID = "01994d00-6c1a-7000-8000-000000000016"
"""``flow_v2/9`` (``0052``, EXP-M13)."""


@pytest_asyncio.fixture
async def lab(db_session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[LabContext]:
    yield LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
    )


async def _guarded_set(engine: AsyncEngine) -> str:
    """``flow_v2/1``'s params plus ``max_recent_drawdown_pct: "0.50"`` (owner write)."""
    rule_set_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "SELECT :id, :name, '1', 'research_only', "
                "  params || '{\"max_recent_drawdown_pct\": \"0.50\"}'::jsonb, code_ref, 'EXP-M13' "
                "FROM meme_rule_sets WHERE id = :seed"
            ),
            {"id": rule_set_id, "name": f"drop_test_{uuid4().hex[:8]}", "seed": FLOW_V2_ID},
        )
    return rule_set_id


def _series(photo: datetime, reals: dict[int, str]) -> list[tuple[datetime, str, str]]:
    """``{seconds before photo: real SOL}`` as ``_plant_curve`` points — the
    fixture's ``_snapshot`` stores ``real = virtual − 30``."""
    return [
        (photo - timedelta(seconds=s), str(Decimal(real) + 30), "946000000")
        for s, real in sorted(reals.items(), reverse=True)
    ]


# ---- the seed ---------------------------------------------------------------------------


async def test_the_0052_seed_parses_into_flow_v2_9_with_the_guard_on(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        specs = {s.label: s for s in await load_active_rule_sets(session)}
    arm, control = specs["flow_v2/9"], specs["flow_v2/6"]
    assert arm.id == AFTER_DROP_ID and arm.clock == "15s" and arm.exp_ref == "EXP-M13"
    assert arm.kind == "research_only"
    assert arm.gate.max_recent_drawdown_pct == Decimal("0.50")
    assert (arm.gate.recent_drawdown_window_s, arm.gate.recent_drawdown_max_gap_s) == (60, 30)
    assert control.gate.max_recent_drawdown_pct is None, "the control never asks"
    assert arm.pedigree_e2b and control.pedigree_e2b, "both carry E2-b: the base is flow_v2/6"


# ---- the fill on the 15-second row ------------------------------------------------------


async def test_the_15s_rows_carry_the_drawdown_folded_from_their_own_photos(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``load_fast_gate_rows`` fills the three fields from the mint's photos
    known by each row's own instant: a fall of 82 % from a 40 s old peak, a
    clean twin, and a mint with a single photo (``too_few_points``)."""
    fallen, clean, lonely = (f"DD_{k}_{uuid4().hex[:6]}" for k in ("FALL", "CLEAN", "ONE"))
    photo = CREATED + timedelta(seconds=120)
    await _plant_curve(
        db_session_factory,
        fallen,
        _series(photo, {40: "29.6", 25: "5.3", 10: "5.3", 0: "5.3"}),
        created_at=CREATED,
    )
    await _plant_curve(
        db_session_factory,
        clean,
        _series(photo, {40: "4.0", 25: "4.5", 10: "5.0", 0: "5.3"}),
        created_at=CREATED,
    )
    await _plant_curve(db_session_factory, lonely, _series(photo, {0: "5.3"}), created_at=CREATED)
    as_of = photo + timedelta(seconds=2)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_fast_rows(
            session, [_fast_row(m, as_of, photo) for m in (fallen, clean, lonely)]
        )
        rows = {
            row.mint: row
            for row in await load_fast_gate_rows(
                session,
                since=as_of - timedelta(seconds=1),
                until=as_of,
                features_version="meme_features_15s_v1",
            )
            if row.mint in (fallen, clean, lonely)
        }
    assert rows[fallen].recent_drawdown_pct == Decimal("0.820946")
    assert rows[fallen].recent_drawdown_peak_age_s == Decimal("42.000"), "peak at photo − 40 s"
    assert rows[fallen].recent_drawdown_reason is None
    assert rows[clean].recent_drawdown_pct == Decimal("0.000000")
    assert rows[clean].recent_drawdown_peak_age_s == Decimal("2.000"), "the newest is the peak"
    assert (rows[lonely].recent_drawdown_pct, rows[lonely].recent_drawdown_reason) == (
        None,
        "too_few_points",
    )


# ---- the gate: refused after the fall, proposed when clean ------------------------------


async def test_a_guarded_set_refuses_the_post_drop_row_and_proposes_the_clean_one(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    rule_set = await _guarded_set(db_engine)
    fallen, clean = f"GATE_FALL_{uuid4().hex[:6]}", f"GATE_CLEAN_{uuid4().hex[:6]}"
    photo = CREATED + timedelta(seconds=150)
    await _plant_curve(
        db_session_factory,
        fallen,
        _series(photo, {40: "29.6", 25: "5.3", 10: "5.3", 0: "5.3"}),
        created_at=CREATED,
        creator=f"C_{fallen}",
        symbol=f"F{fallen[-4:]}",
    )
    await _plant_curve(
        db_session_factory,
        clean,
        _series(photo, {40: "4.0", 25: "4.5", 10: "5.0", 0: "5.3"}),
        created_at=CREATED,
        creator=f"C_{clean}",
        symbol=f"K{clean[-4:]}",
    )
    as_of = photo + timedelta(seconds=2)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_fast_rows(session, [_fast_row(m, as_of, photo) for m in (fallen, clean)])
    report = await lab_tick(lab, now=as_of + timedelta(seconds=1))
    assert report.proposals >= 1
    name = (
        await _one(
            db_session_factory,
            "SELECT name FROM meme_rule_sets WHERE id = CAST(:rs AS uuid)",
            rs=rule_set,
        )
    )["name"]
    refusals = lab.state.refusals[name]
    # ``>= 1``, not ``== 1``: the tick's backlog window also judges the rows
    # the other tests of this module planted at nearby instants.
    assert refusals.get("recent_drawdown", 0) >= 1, refusals
    proposed = await _one(
        db_session_factory,
        "SELECT count(*) FILTER (WHERE mint = :fallen) AS fallen, "
        "       count(*) FILTER (WHERE mint = :clean) AS clean "
        "FROM meme_proposals WHERE rule_set_id = CAST(:rs AS uuid)",
        fallen=fallen,
        clean=clean,
        rs=rule_set,
    )
    assert (proposed["fallen"], proposed["clean"]) == (0, 1)
    trail = await _one(
        db_session_factory,
        'SELECT refusal, value, "limit" FROM meme_gate_refusals_by_mint '
        "WHERE rule_set_id = CAST(:rs AS uuid) AND mint = :m",
        rs=rule_set,
        m=fallen,
    )
    assert trail["refusal"] == "recent_drawdown", "the near-miss names the one criterion"
    assert trail["value"] == Decimal("0.820946") and trail["limit"] == Decimal("0.5")
    # The same tick judged the seeded arm too: flow_v2/9 read the fall rather than blindness.
    arm_refusals = lab.state.refusals["flow_v2"]
    assert arm_refusals.get("recent_drawdown", 0) >= 1, arm_refusals


# ---- the read: one bounded query per tick, on the index ---------------------------------


async def test_the_reserve_read_is_bounded_by_the_tick_and_served_by_the_index(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint = f"EXPLAIN_{uuid4().hex[:6]}"
    photo = CREATED + timedelta(seconds=120)
    await _plant_curve(
        db_session_factory,
        mint,
        _series(photo, {200: "1.0", 40: "29.6", 0: "5.3"}),
        created_at=CREATED,
    )
    as_of = photo + timedelta(seconds=2)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_fast_rows(session, [_fast_row(mint, as_of, photo)])
        (row,) = [
            r
            for r in await load_fast_gate_rows(
                session,
                since=as_of - timedelta(seconds=1),
                until=as_of,
                features_version="meme_features_15s_v1",
            )
            if r.mint == mint
        ]
        points = await reserve_points_for(session, [row])
    assert points is not None and len(points[mint]) == 2, (
        "the photo 200 s before the instant is outside the 120 s lookback"
    )
    # The plan is declared over a slice the size of a live tick's: 5 000 mints
    # photographed 8 times inside the 120 s lookback (40 000 photos), of which
    # the tick asks for 130 — the pinned/young set. On an empty table the
    # planner would pick the primary key (``observed_at`` first) and filter
    # every mint of the window; with the volume it must take the mint index.
    bulk_base = as_of - timedelta(seconds=FILL_LOOKBACK_S - 5)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_curve_snapshots (observed_at, mint, source, received_at, "
                "  virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, "
                "  real_token_reserves, total_supply, complete) "
                "SELECT CAST(:base AS timestamptz) + (g % 8) * interval '15 seconds', 'BULK_' || (g / 8), "
                "  'pumpfun_rest', CAST(:base AS timestamptz) + (g % 8) * interval '15 seconds', "
                "  40, 900000000, 10, 600000000, 1000000000, false "
                "FROM generate_series(0, 39999) AS g"
            ),
            {"base": bulk_base},
        )
        await connection.execute(text("ANALYZE meme_curve_snapshots"))
    params = {
        "mints": [f"BULK_{i}" for i in range(130)],
        "floor": as_of - timedelta(seconds=FILL_LOOKBACK_S),
        "ceiling": as_of,
    }
    async with db_engine.connect() as connection:
        plan = "\n".join(
            (await connection.execute(text(f"EXPLAIN {_RESERVES.text}"), params)).scalars().all()
        )
        photos = (
            await connection.execute(text("SELECT count(*) FROM meme_curve_snapshots"))
        ).scalar_one()
    assert photos >= 40_000, "the plan must be declared over a table this size, not a fixture"
    assert "mint_observed" in plan, (
        plan
    )  # the partition-local child of the (mint, observed_at) index
    assert "Seq Scan on meme_curve_snapshots" not in plan, plan
    assert "meme_curve_snapshots_2026_11" not in plan, "the ceiling prunes the later partitions"
    notes = Path(__file__).resolve().parents[3] / ".claude" / "state"  # noqa: ASYNC240
    notes.joinpath("notes-T4.61a-explain.txt").write_text(
        f"photos={photos}\nmints=130\nlookback_s={FILL_LOOKBACK_S}\n{plan}", encoding="utf-8"
    )
