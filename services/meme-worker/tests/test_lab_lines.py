# pyright: reportPrivateUsage=false
"""T4.10 against a real Postgres at ``head`` — one file, one container.

What only a database can prove: the ``0026`` seed parses into the two gates;
the line points the fold reads obey ``received_at <= end_time``; and the whole
life of a probe — opened by ``hype_probe_v0`` on a two-minute-old coin, scaled
into a second leg (``leg = 'scale'``, ``parent_bet_id`` = the probe) the minute
``trendline_v0`` is satisfied for the same mint, scaled **once**, and the second
leg sold ``line_broken`` on the snapshot after the second close below the
support line — every step priced on a snapshot strictly after the decision.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_indicators.meme.lines import LinePoint
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.features import CurveObservation, MinuteInputs, build_row
from hunter_meme_worker.features_lines import BoardStanding
from hunter_meme_worker.features_tape import HoldersObservation, TapeMinute
from hunter_meme_worker.lab import LabContext, LabState, lab_tick
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.lab_repo_lines import support_lines_for
from hunter_meme_worker.lines_exit import support_at
from hunter_meme_worker.repo import insert_features, insert_snapshot
from hunter_meme_worker.repo_lines import load_line_points

from .test_lab_persistence import (  # pyright: ignore[reportPrivateUsage]
    FakeQuotes,
    Heartbeats,
    _one,
    _plant_curve,
    _snapshot,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
TRENDLINE_ID = "01994d00-6c1a-7000-8000-000000000003"
HYPE_PROBE_ID = "01994d00-6c1a-7000-8000-000000000004"
CREATED = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
"""A Brasília morning (09:00 BRT) inside the 2026-10 partitions."""

# mcap_sol of a snapshot = virtual_sol / virtual_token × 1e9: "34" / 946e6 → 35,94 SOL.
ABOVE, BELOW_1, BELOW_2, SALE = "34", "28", "27", "26"

SERIES: dict[int, str] = {
    -15: "31",
    -14: "30",
    -13: "29",
    -12: "28",  # low 1
    -11: "30",
    -10: "32",
    -9: "33",
    -8: "31",
    -7: "29",  # low 2 (higher): slope 0,2 SOL/min, support at the close = 30,4
    -6: "31",
    -5: "32",
    -4: "33",
    -3: "34",
    -2: "34.5",
    -1: "35",  # the previous window's high: 36 breaks out
    0: "36",
}


@pytest_asyncio.fixture
async def lab(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[LabContext]:
    yield LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
    )


def _points(end_time: datetime) -> list[LinePoint]:
    return [
        LinePoint(end_time + timedelta(minutes=m), end_time + timedelta(minutes=m), Decimal(v))
        for m, v in SERIES.items()
    ]


def _minute(
    mint: str, end_time: datetime, *, observed_at: datetime, with_line: bool
) -> MinuteInputs:
    """A minute the probe gate likes (hype 0,7, dev 5 %, one sniper, creator not
    a net seller, 10 SOL of volume) — with or without the line."""
    return MinuteInputs(
        mint=mint,
        end_time=end_time,
        created_at=CREATED,
        initial_real_token_reserves=Decimal("793100000") if with_line else None,
        snapshot=CurveObservation(
            observed_at=observed_at,
            source="pumpfun_rest",
            real_token_reserves=Decimal("666100000"),
            mcap_sol=Decimal(36),
            complete=False,
        ),
        holders=HoldersObservation(
            observed_at=end_time - timedelta(seconds=20),
            received_at=end_time - timedelta(seconds=19),
            source="trenches_ws",
            holders=40,
            top10_share=Decimal("0.3"),
            dev_share=Decimal("0.05"),
            snipers=1,
        ),
        tape=TapeMinute(
            buys=15,
            sells=2,
            unique_buyers=10,
            net_sol_flow=Decimal(5),
            volume_sol=Decimal(10),
            creator_sold=False,
            creator_net_seller=False,
        ),
        line_points=_points(end_time) if with_line else [],
        board=BoardStanding(best_position=3, has_social=True),
    )


async def _fold(
    factory: async_sessionmaker[AsyncSession],
    inputs: MinuteInputs,
    *,
    computed_at: datetime | None = None,
) -> None:
    """Insert the minute and pin its ``computed_at`` (T4.98): the column's
    default is the database's wall clock, which these 2026-10 instants do not
    share — the exit reads ``computed_at <= photo``. Default: the fold's measured
    delay, 3 s after the close."""
    async with role_session(factory, db_role=WORKER) as session:
        await insert_features(session, [build_row(inputs)])
    async with factory() as session:  # the owner: hunter_worker only inserts
        await session.execute(
            text(
                "UPDATE meme_features_1m SET computed_at = :at "
                "WHERE mint = :mint AND end_time = :end_time"
            ),
            {
                "at": computed_at or inputs.end_time + timedelta(seconds=3),
                "mint": inputs.mint,
                "end_time": inputs.end_time,
            },
        )
        await session.commit()


async def _bets(factory: async_sessionmaker[AsyncSession], mint: str) -> list[dict[str, Any]]:
    async with role_session(factory, db_role=WORKER) as session:
        rows = await session.execute(
            text(
                "SELECT id::text AS id, rule_set_id::text AS rule_set_id, leg, "
                "  parent_bet_id::text AS parent_bet_id, status, entry, params, exit, entry_at "
                "FROM meme_paper_bets WHERE mint = :mint ORDER BY entry_at, leg"
            ),
            {"mint": mint},
        )
        return [dict(r) for r in rows.mappings()]


# ---- the seed ---------------------------------------------------------------------------


async def test_the_seed_plants_the_two_arms_and_they_parse_into_their_gates(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        specs = {s.id: s for s in await load_active_rule_sets(session)}
    trend, probe = specs[TRENDLINE_ID], specs[HYPE_PROBE_ID]
    assert isinstance(trend, RuleSetSpec) and trend.label == "trendline_v0/1"
    assert trend.exp_ref == "EXP-M2" and trend.kind == "research_only"
    assert trend.gate.min_age_s == 300 and trend.gate.require_higher_lows
    assert trend.gate.require_breakout_15m
    assert trend.gate.max_distance_to_support_pct == Decimal("0.25")
    assert trend.exit_on_line_break and trend.line_break_snapshots == 2
    assert (trend.size_sol, trend.target_x, trend.trailing_pct, trend.max_hold_s) == (
        Decimal("0.05"),
        Decimal(2),
        Decimal(30),
        900,
    )
    assert probe.label == "hype_probe_v0/1" and probe.exp_ref == "EXP-M3"
    assert probe.scales and probe.scale_gate == "trendline_v0/1"
    assert probe.scale_size_sol == Decimal("0.04") and probe.size_sol == Decimal("0.01")
    assert (probe.gate.min_age_s, probe.gate.max_age_s) == (30, 300)
    assert probe.gate.min_hype_score == Decimal("0.6") and probe.gate.max_snipers == 2
    assert probe.gate.max_dev_share == Decimal("0.10") and probe.gate.dev_share_unknown_allowed
    assert probe.gate.require_progress is False
    assert (probe.target_x, probe.trailing_pct, probe.max_hold_s) == (Decimal(3), Decimal(40), 600)
    assert probe.max_open_positions == 5 and probe.wallet_max_sol == Decimal("2.0")
    assert probe.daily_loss_cap_sol == Decimal("0.20")


# ---- the read the lines make ------------------------------------------------------------


async def test_a_photo_received_after_the_close_is_not_a_line_point(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mint = f"LINE_{uuid4().hex[:8]}"
    end_time = CREATED + timedelta(minutes=10)
    await _plant_curve(
        db_session_factory,
        mint,
        [(end_time - timedelta(minutes=m), ABOVE, "946000000") for m in (16, 15, 8, 0)],
        created_at=CREATED,
    )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await session.execute(
            text(
                "INSERT INTO meme_curve_snapshots (observed_at, received_at, mint, source, "
                "  virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, "
                "  real_token_reserves, total_supply, complete) "
                "VALUES (:observed, :received, :mint, 'solana_rpc', 34, 946000000, 4, "
                "  666100000, 1000000000, false)"
            ),
            {
                "observed": end_time - timedelta(minutes=3),
                "received": end_time + timedelta(seconds=1),
                "mint": mint,
            },
        )
        points = await load_line_points(session, mints=[mint], end_time=end_time)
    observed = sorted(p.observed_at for p in points[mint])
    assert observed == [end_time - timedelta(minutes=15), end_time - timedelta(minutes=8), end_time]
    assert all(p.received_at <= end_time for p in points[mint])
    assert all(p.mcap_sol is not None and p.mcap_sol > 0 for p in points[mint])


# ---- probe → scale → line broken --------------------------------------------------------


MINUTE_B = CREATED + timedelta(minutes=6)
"""The minute the line is born: support 30,4 SOL at the close, slope 0,2 SOL/min."""
TICK_3 = CREATED + timedelta(minutes=11, seconds=30)
FILL_2 = CREATED + timedelta(minutes=7, seconds=40)
"""The scale leg's fill — the first photo after tick 2 — 100 s after ``MINUTE_B``."""


async def _probe_then_scale(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    *,
    minute_b_computed_at: datetime | None = None,
) -> str:
    """A probe opened at 2 min, scaled the minute the line is born; the mint.
    The scale leg (``exit_on_line_break``) fills at ``FILL_2``."""
    async with db_session_factory() as session:
        # The T4.98 cases leave their bets open on purpose, and the container is
        # the session's: retire this file's leftovers, or the set's
        # ``max_open_positions`` (5) refuses the next probe. Closed flat (0 SOL),
        # so no cap's loss sum moves.
        await session.execute(
            text(
                "UPDATE meme_paper_bets SET status = 'closed', "
                "  exit_at = entry_at + interval '1 second', "
                "  exit = jsonb_build_object('reason', 'sell_now'), pnl_sol = 0, r_multiple = 0 "
                "WHERE mint LIKE 'PROBE\\_%' AND status = 'open'"
            )
        )
        await session.commit()
    mint = f"PROBE_{uuid4().hex[:8]}"
    minute_a, minute_b = CREATED + timedelta(minutes=2), MINUTE_B
    photo_a, photo_b = minute_a - timedelta(seconds=20), minute_b - timedelta(seconds=20)
    tick_1, tick_2 = (CREATED + timedelta(minutes=m, seconds=30) for m in (3, 7))
    fill_1, fill_2 = tick_1 + timedelta(seconds=10), FILL_2
    await _plant_curve(
        db_session_factory,
        mint,
        [
            (photo_a, ABOVE, "946000000"),
            (fill_1, ABOVE, "946000000"),  # the probe's fill: first after tick 1
            (photo_b, ABOVE, "946000000"),
            (fill_2, ABOVE, "946000000"),  # the second leg's fill: first after tick 2
        ],
        created_at=CREATED,
        # T4.16 (EXP-M6): pedigree_exclusions is on by default (both sets never
        # opt out) — an unknown creator/symbol refuses every proposal by name
        # before the gate is even read. Unique per test run, never colliding
        # with another mint's pedigree window.
        creator=f"C_{mint}",
        symbol=mint,
    )
    await _fold(db_session_factory, _minute(mint, minute_a, observed_at=photo_a, with_line=False))

    report = await lab_tick(lab, now=tick_1)
    assert report.fills.filled >= 1
    bets = await _bets(db_session_factory, mint)
    probes = [b for b in bets if b["rule_set_id"] == HYPE_PROBE_ID]
    assert [(b["leg"], b["parent_bet_id"], b["status"]) for b in probes] == [
        ("probe", None, "open")
    ]
    probe = probes[0]
    assert probe["entry_at"] == fill_1 and probe["entry"]["sol_spent"] == "0.01"
    assert probe["params"]["exit_on_line_break"] is False
    assert lab.state.refusals["trendline_v0"].get("age_below_min", 0) >= 1, "no line at 2 min"

    await _fold(
        db_session_factory,
        _minute(mint, minute_b, observed_at=photo_b, with_line=True),
        computed_at=minute_b_computed_at,
    )
    line = await _one(
        db_session_factory,
        "SELECT support_line_sol, support_line_slope, higher_lows, breakout_15m, "
        "  distance_to_support_pct, hype_score FROM meme_features_1m "
        "WHERE mint = :mint AND end_time = :end_time",
        mint=mint,
        end_time=minute_b,
    )
    assert line["support_line_sol"] == Decimal("30.4") and line["higher_lows"] is True
    assert line["breakout_15m"] is True and line["hype_score"] == Decimal("0.7")

    report = await lab_tick(lab, now=tick_2)
    assert report.fills.filled >= 1
    bets = await _bets(db_session_factory, mint)
    legs = [
        (b["leg"], b["parent_bet_id"], b["status"])
        for b in bets
        if b["rule_set_id"] == HYPE_PROBE_ID
    ]
    assert legs == [("probe", None, "open"), ("scale", probe["id"], "open")]
    # ``hype_probe_v0/2`` (``0030``, EXP-M5 arm 2 — same numbers, an added
    # flow condition) is active too and this curve satisfies it as well: a
    # second, independent probe/scale pair on the same mint under a sibling
    # rule set is the comparison doing its job, not a bug — but ``bets``
    # carries both, so every lookup below must stay pinned to our own set.
    scale = next(b for b in bets if b["leg"] == "scale" and b["rule_set_id"] == HYPE_PROBE_ID)
    assert scale["entry_at"] == fill_2 and scale["entry"]["sol_spent"] == "0.04"
    assert scale["entry"]["parent_bet_id"] == probe["id"]
    assert scale["params"]["exit_on_line_break"] is True
    assert scale["params"]["max_hold_s"] == 900 and scale["params"]["target_x"] == "2"
    assert lab.state.refusals["hype_probe_v0"].get("already_open", 0) >= 1, "no second probe"
    return mint


async def _break_photos(
    factory: async_sessionmaker[AsyncSession], mint: str, seconds: tuple[int, int, int]
) -> None:
    """Two closes below the line and the sale photo, ``seconds`` after ``FILL_2``.
    The future arrives only now — planted before tick 2 it would have been walked
    in that same tick, which is the engine doing its job, not a bug."""
    async with role_session(factory, db_role=WORKER) as session:
        for second, sol in zip(seconds, (BELOW_1, BELOW_2, SALE), strict=True):
            await insert_snapshot(
                session, _snapshot(mint, FILL_2 + timedelta(seconds=second), sol, "946000000")
            )


async def test_a_probe_scales_once_when_the_line_is_born_and_sells_when_it_breaks(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mint = await _probe_then_scale(lab, db_session_factory)
    fill_2 = FILL_2
    # 29,6 < 30,77 (1st close below, line 110 s old), 28,5 < 30,78 (2nd — the
    # rule, 115 s old: still fresh under the 120 s bound), then the sale.
    await _break_photos(db_session_factory, mint, (10, 15, 25))
    await lab_tick(lab, now=TICK_3)
    bets = await _bets(db_session_factory, mint)
    hype_bets = [b for b in bets if b["rule_set_id"] == HYPE_PROBE_ID]
    assert len(hype_bets) == 2, "a probe scales once"
    scale = next(b for b in hype_bets if b["leg"] == "scale")
    assert scale["status"] == "closed" and scale["exit"]["reason"] == "line_broken"
    assert scale["exit"]["intent_snapshot_at"] == (fill_2 + timedelta(seconds=15)).isoformat()
    assert scale["exit"]["snapshot"]["observed_at"] == (fill_2 + timedelta(seconds=25)).isoformat()
    probe = next(b for b in hype_bets if b["leg"] == "probe")
    assert probe["status"] == "open", "the probe does not watch the line"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        pending = await session.scalar(
            text(
                "SELECT count(*) FROM meme_proposals WHERE mint = :mint "
                "AND rule_set_id = CAST(:rs AS uuid) "
                "AND suggested ->> 'parent_bet_id' IS NOT NULL"
            ),
            {"mint": mint, "rs": HYPE_PROBE_ID},
        )
    assert pending == 1, "exactly one scale proposal was ever written under our own set"


# ---- T4.98 (EXP-M26 L1): a stale, unborn or hidden line never sells --------------------


@pytest.mark.parametrize(
    ("scenario", "seconds"),
    [
        # the same two closes below, 160 and 220 s after the only line: stale
        ("stale_line", (60, 120, 180)),
        # minute B closed at 12:06 but was folded at 12:08:00, after both closes
        ("folded_after_the_photos", (10, 15, 25)),
        # minute 12:07 was folded without a line: the 12:06 line is not projected over it
        ("newer_minute_without_a_line", (10, 15, 25)),
    ],
)
async def test_a_line_the_photo_could_not_trust_never_fires_line_broken(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    scenario: str,
    seconds: tuple[int, int, int],
) -> None:
    late = FILL_2 + timedelta(seconds=20) if scenario == "folded_after_the_photos" else None
    mint = await _probe_then_scale(lab, db_session_factory, minute_b_computed_at=late)
    if scenario == "newer_minute_without_a_line":
        minute_c = MINUTE_B + timedelta(minutes=1)
        photo_c = minute_c - timedelta(seconds=20)
        await _fold(
            db_session_factory, _minute(mint, minute_c, observed_at=photo_c, with_line=False)
        )
    await _break_photos(db_session_factory, mint, seconds)
    await lab_tick(lab, now=TICK_3)
    bets = await _bets(db_session_factory, mint)
    scale = next(b for b in bets if b["leg"] == "scale" and b["rule_set_id"] == HYPE_PROBE_ID)
    assert scale["status"] == "open", f"{scenario}: {scale['exit']}"
    marked = await _one(
        db_session_factory,
        "SELECT mark_at, exit_intent FROM meme_paper_bets WHERE id = CAST(:id AS uuid)",
        id=scale["id"],
    )
    assert marked["exit_intent"] is None
    assert marked["mark_at"] == FILL_2 + timedelta(seconds=seconds[-1]), "every photo was walked"


async def test_a_stale_line_does_not_block_the_other_exits(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Unknown support is neutral: 3 min after the only line, the price more than
    doubles and the scale leg sells ``target`` (``target_x 2``) as it always did."""
    mint = await _probe_then_scale(lab, db_session_factory)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        for second, sol in ((180, "80"), (195, "80")):
            await insert_snapshot(
                session, _snapshot(mint, FILL_2 + timedelta(seconds=second), sol, "946000000")
            )
    await lab_tick(lab, now=TICK_3)
    bets = await _bets(db_session_factory, mint)
    scale = next(b for b in bets if b["leg"] == "scale" and b["rule_set_id"] == HYPE_PROBE_ID)
    assert scale["status"] == "closed" and scale["exit"]["reason"] == "target"
    assert scale["exit"]["intent_snapshot_at"] == (FILL_2 + timedelta(seconds=180)).isoformat()


async def test_the_bet_s_own_bound_reaches_the_loop(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``line_support_max_age_s`` rides in ``meme_paper_bets.params``: a bet
    written with 300 s sells on the 160/220 s-old line a 120 s bet ignores."""
    mint = await _probe_then_scale(lab, db_session_factory)
    async with db_session_factory() as session:  # the owner: the experiment's explicit key
        await session.execute(
            text(
                "UPDATE meme_paper_bets SET params = params || "
                "'{\"line_support_max_age_s\": 300}'::jsonb "
                "WHERE mint = :mint AND leg = 'scale' AND rule_set_id = CAST(:rs AS uuid)"
            ),
            {"mint": mint, "rs": HYPE_PROBE_ID},
        )
        await session.commit()
    await _break_photos(db_session_factory, mint, (60, 120, 180))
    await lab_tick(lab, now=TICK_3)
    bets = await _bets(db_session_factory, mint)
    scale = next(b for b in bets if b["leg"] == "scale" and b["rule_set_id"] == HYPE_PROBE_ID)
    assert scale["params"]["line_support_max_age_s"] == 300
    assert scale["status"] == "closed" and scale["exit"]["reason"] == "line_broken"
    assert scale["exit"]["intent_snapshot_at"] == (FILL_2 + timedelta(seconds=120)).isoformat()


async def test_a_backlog_past_30_minutes_still_reads_the_photo_s_own_minute(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Astra, T4.98 review: with the lineless minutes read too, a ``LIMIT 30``
    covers only 30 minutes — a Lab back from a 40-minute pause would judge the
    old photos with no line. The read is by range: ``[photo − bound, now]``."""
    mint = f"BACKLOG_{uuid4().hex[:8]}"
    await _plant_curve(
        db_session_factory,
        mint,
        [(MINUTE_B - timedelta(seconds=20), ABOVE, "946000000")],
        created_at=CREATED,
    )
    await _fold(
        db_session_factory,
        _minute(mint, MINUTE_B, observed_at=MINUTE_B - timedelta(seconds=20), with_line=True),
    )
    for m in range(1, 41):
        minute = MINUTE_B + timedelta(minutes=m)
        await _fold(
            db_session_factory,
            _minute(mint, minute, observed_at=minute - timedelta(seconds=20), with_line=False),
        )
    photo = MINUTE_B + timedelta(seconds=15)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        lines = await support_lines_for(
            session,
            mint=mint,
            features_version=MemeConfig().features_version,
            since=photo - timedelta(seconds=120),
            until=MINUTE_B + timedelta(minutes=41),
        )
    assert support_at(lines, photo) == Decimal("30.45")
    assert support_at(lines, MINUTE_B + timedelta(minutes=1, seconds=10)) is None, "flat after"
