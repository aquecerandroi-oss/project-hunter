"""Every row the daily ficha reads (T4.92) — as ``hunter_app`` (``SELECT`` only).

Nothing here writes; nothing here invents a number. Real positions are read
per-row (buy/sell fill, decision tape, pedigree) rather than in one giant
join: the daily volume of real trades is a few dozen, and a row-by-row read
is the one that never has to guess which side of a ``LEFT JOIN`` a null came
from — the discipline ``meme_close_queries.py`` already uses for the paper
Lab (``docs/DATABASE.md`` §64's own join is exactly ``t.mint = p.mint AND
t.as_of = p.features_end_time``, used here unmodified).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

from meme_daily_ficha_fills import (
    fees_sol,
    fraction_to_pct,
    rent_refund_sol,
    round_trip_cost_sol,
    sol_from_lamports,
    tape_features,
)
from meme_daily_ficha_types import DayFicha, DecisionFeatures, PaperArm, RealPosition, SpotPosition
from sqlalchemy import text

from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.settings import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["SAO_PAULO", "TICKET_SOL", "day_bounds", "gather_day", "gather_week"]

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
DB_ROLE = "hunter_app"
TICKET_SOL = Decimal("0.07")
"""The mesa real's standard ficket size (``Ficha-2026-09-23-mesa-real.md``);
paper arms whose own ``size_sol`` differs are normalized to this so their
avg-%-per-entry is comparable across rule sets."""


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=SAO_PAULO)
    return start, start + timedelta(days=1)


_POSITIONS = text(
    "SELECT p.mint, t.symbol, r.name || '/' || r.version AS operator, p.entry_at, p.exit_at, "
    "       p.initial_risk_sol AS cost_sol, p.sol_received_lamports, p.pnl_sol, p.high_water_sol, "
    "       p.exit ->> 'reason' AS exit_reason, p.entry_order_id, p.exit_order_id, p.proposal_id, "
    "       pr.features_end_time "
    "FROM meme_live_positions p "
    "JOIN meme_proposals pr ON pr.id = p.proposal_id "
    "JOIN meme_rule_sets r ON r.id = pr.rule_set_id "
    "LEFT JOIN meme_tokens t ON t.mint = p.mint "
    "WHERE p.entry_at >= :day_start AND p.entry_at < :day_end "
    "ORDER BY p.entry_at"
)
_SELL_ATTEMPTS = text(
    "SELECT count(*) FROM meme_live_orders WHERE proposal_id = :proposal_id AND side = 'sell'"
)
_ORDER_FILL = text("SELECT fill FROM meme_live_orders WHERE id = :id")
_TAPE = text("SELECT derived FROM meme_decision_tapes WHERE mint = :mint AND as_of = :as_of")
_SELLERS_IN_A_SLOT = text(
    "SELECT max(n) FROM (SELECT slot, count(DISTINCT trader) AS n FROM meme_trades "
    "  WHERE mint = :mint AND side = 'sell' AND block_time >= :entry_at AND block_time <= :exit_at "
    "  GROUP BY slot) s"
)
_PRIOR_EXIT = text(
    "SELECT max(exit_at) FROM meme_live_positions "
    "WHERE mint = :mint AND exit_at IS NOT NULL AND exit_at < :entry_at"
)
_FEATURES_1M = text(
    "SELECT curve_progress_pct, snipers, dev_share FROM meme_features_1m "
    "WHERE mint = :mint AND end_time <= :anchor AND end_time > :anchor - interval '10 minutes' "
    "ORDER BY end_time DESC, features_version DESC LIMIT 1"
)
_SPOT_POSITIONS = text(
    "SELECT market_symbol, mint, entry_at, exit_at, params, pnl_sol "
    "FROM spot_positions WHERE entry_at >= :day_start AND entry_at < :day_end ORDER BY entry_at"
)
_PAPER_BETS_WINDOW = text(
    "SELECT r.name || '/' || r.version AS rule_set, b.pnl_sol, b.status "
    "FROM meme_paper_bets b JOIN meme_rule_sets r ON r.id = b.rule_set_id "
    "WHERE b.entry_at >= :since AND b.entry_at < :until "
    "ORDER BY r.name, r.version"
)
_CUMULATIVE = text(
    "SELECT sum(pnl_sol) FROM meme_live_positions WHERE status = 'closed' AND exit_at < :day_end"
)


async def _rows(
    session: AsyncSession, query: Any, params: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """``.mappings().all()``, each row turned into a plain ``dict`` — the
    ``meme_close_queries.py`` idiom: ``RowMapping`` does not satisfy
    ``Mapping[str, Any]`` under pyright's invariant generics, and a plain
    dict is also what every call site here already indexes by string key."""
    return [dict(r) for r in (await session.execute(query, params)).mappings().all()]


async def _row(
    session: AsyncSession, query: Any, params: Mapping[str, Any]
) -> dict[str, Any] | None:
    row = (await session.execute(query, params)).mappings().first()
    return None if row is None else dict(row)


async def _fill(session: AsyncSession, order_id: str | None) -> Mapping[str, Any] | None:
    if order_id is None:
        return None
    return await session.scalar(_ORDER_FILL, {"id": order_id})


async def _decision_features(
    session: AsyncSession, *, mint: str, entry_at: datetime, features_end_time: datetime | None
) -> DecisionFeatures:
    # Astra (T4.92 review, HIGH): anchor on the proposal's own decision minute
    # (``features_end_time``, the same instant the tape below joins on) when it
    # is known, never on ``entry_at`` — a fill lands seconds after the gate
    # decided, and a minute that closed in between is evidence the gate never
    # saw, not evidence "at the decision". Falls back to ``entry_at`` only for
    # an ``operator`` proposal, which never names a features minute.
    anchor = entry_at if features_end_time is None else features_end_time
    row = await _row(session, _FEATURES_1M, {"mint": mint, "anchor": anchor})
    progress = fraction_to_pct(
        None
        if row is None or row["curve_progress_pct"] is None
        else Decimal(str(row["curve_progress_pct"]))
    )
    snipers = None if row is None or row["snipers"] is None else int(row["snipers"])
    dev_share = fraction_to_pct(
        None if row is None or row["dev_share"] is None else Decimal(str(row["dev_share"]))
    )
    derived = None
    if features_end_time is not None:
        derived = await session.scalar(_TAPE, {"mint": mint, "as_of": features_end_time})
    buys, sells, unique_buyers, net_flow, bundle_sol, bundle_wallets = tape_features(derived)
    return DecisionFeatures(
        curve_progress_pct=progress,
        snipers=snipers,
        dev_share_pct=dev_share,
        buys_1m=buys,
        sells_1m=sells,
        unique_buyers=unique_buyers,
        net_flow_sol=net_flow,
        creation_bundle_sol=bundle_sol,
        creation_bundle_wallets=bundle_wallets,
    )


async def _real_position(session: AsyncSession, row: Mapping[str, Any]) -> RealPosition:
    entry_fill = await _fill(session, str(row["entry_order_id"]))
    exit_fill = await _fill(
        session, None if row["exit_order_id"] is None else str(row["exit_order_id"])
    )
    entry_fees, exit_fees = fees_sol(entry_fill), fees_sol(exit_fill)
    rent_refund = rent_refund_sol(exit_fill)
    total_fees_sol = (
        None
        if entry_fees is None and exit_fees is None
        else (entry_fees or Decimal(0)) + (exit_fees or Decimal(0))
    )
    sellers = None
    if row["exit_at"] is not None:
        sellers = await session.scalar(
            _SELLERS_IN_A_SLOT,
            {"mint": row["mint"], "entry_at": row["entry_at"], "exit_at": row["exit_at"]},
        )
    prior_exit = await session.scalar(
        _PRIOR_EXIT, {"mint": row["mint"], "entry_at": row["entry_at"]}
    )
    since_prior = None if prior_exit is None else row["entry_at"] - prior_exit
    features = await _decision_features(
        session,
        mint=row["mint"],
        entry_at=row["entry_at"],
        features_end_time=row["features_end_time"],
    )
    return RealPosition(
        mint=row["mint"],
        symbol=row["symbol"],
        operator=row["operator"],
        entry_at=row["entry_at"],
        exit_at=row["exit_at"],
        cost_sol=Decimal(row["cost_sol"]),
        sol_out=sol_from_lamports(row["sol_received_lamports"]),
        pnl_sol=None if row["pnl_sol"] is None else Decimal(row["pnl_sol"]),
        high_water_sol=None if row["high_water_sol"] is None else Decimal(row["high_water_sol"]),
        exit_reason=row["exit_reason"],
        sell_attempts=int(
            await session.scalar(_SELL_ATTEMPTS, {"proposal_id": row["proposal_id"]}) or 0
        ),
        fees_sol=total_fees_sol,
        rent_refund_sol=rent_refund,
        round_trip_cost_sol=round_trip_cost_sol(entry_fees, exit_fees, rent_refund),
        distinct_sellers_one_slot=None if sellers is None else int(sellers),
        since_prior_exit=since_prior,
        features=features,
    )


def _spot_position(row: Mapping[str, Any]) -> SpotPosition:
    params = cast(dict[str, Any], row["params"] or {})
    return SpotPosition(
        market_symbol=row["market_symbol"],
        mint=row["mint"],
        entry_at=row["entry_at"],
        exit_at=row["exit_at"],
        entry_price=None if params.get("ref") is None else Decimal(str(params["ref"])),
        target_price=(
            None if params.get("target1_price") is None else Decimal(str(params["target1_price"]))
        ),
        stop_price=None if params.get("stop_price") is None else Decimal(str(params["stop_price"])),
        pnl_sol=None if row["pnl_sol"] is None else Decimal(row["pnl_sol"]),
    )


def _paper_arms(rows: Sequence[Mapping[str, Any]]) -> list[PaperArm]:
    """One row per rule set with an entry in the window. ``avg_pct_per_ticket``
    normalizes every arm to the mesa real's fixed ``TICKET_SOL`` ticket rather
    than each rule set's own (varying) ``size_sol`` — a deliberate match of the
    existing convention (``obsidian/09-OPERATIONS/Diario/2026-09-25.md``'s own
    "média/entrada" table), verified against three real rule sets on the VPS
    (``recuo_v1/1`` 2,61 %, ``refused_probe_v0/1`` −26,9 %, ``absorb_v0`` ≈ −4 %,
    all to the published decimal) — flagged by Astra's T4.92 review as mixing
    ticket sizes across arms; kept, reconciled against that measurement.
    The denominator is every entry in the window, open or closed (also the
    diary's convention): an arm with **no closed bet yet** would divide zero by
    a nonzero denominator into a false "0 %" — guarded below into "—" instead."""
    by_arm: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_arm.setdefault(str(row["rule_set"]), []).append(row)
    arms: list[PaperArm] = []
    for rule_set, bets in sorted(by_arm.items()):
        entries = len(bets)
        closed = [b for b in bets if b["status"] == "closed" and b["pnl_sol"] is not None]
        wins = sum(1 for b in closed if Decimal(b["pnl_sol"]) > 0)
        pnl_sol = sum((Decimal(b["pnl_sol"]) for b in closed), Decimal(0))
        avg_pct = None if not closed else (pnl_sol / entries) / TICKET_SOL * 100
        arms.append(
            PaperArm(
                rule_set=rule_set,
                entries=entries,
                wins=wins,
                pnl_sol=pnl_sol,
                avg_pct_per_ticket=avg_pct,
            )
        )
    return arms


async def gather_day(day: date) -> DayFicha:
    day_start, day_end = day_bounds(day)
    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    try:
        async with role_session(factory, db_role=DB_ROLE) as session:
            position_rows = await _rows(
                session, _POSITIONS, {"day_start": day_start, "day_end": day_end}
            )
            positions = [await _real_position(session, row) for row in position_rows]
            spot_rows = await _rows(
                session, _SPOT_POSITIONS, {"day_start": day_start, "day_end": day_end}
            )
            spot = [_spot_position(row) for row in spot_rows]
            paper_rows = await _rows(
                session,
                _PAPER_BETS_WINDOW,
                {"since": day_end - timedelta(hours=24), "until": day_end},
            )
            cumulative = await session.scalar(_CUMULATIVE, {"day_end": day_end})
        return DayFicha(
            day=day,
            generated_at=day_end,
            positions=positions,
            spot=spot,
            paper_arms=_paper_arms(paper_rows),
            cumulative_pnl_sol=None if cumulative is None else Decimal(cumulative),
        )
    finally:
        await engine.dispose()


async def gather_week(end_day: date) -> dict[str, list[RealPosition]]:
    """The last 7 Brasília days (ending at ``end_day``, inclusive) of real meme
    positions, for the weekly review's loss-class rollup — one query, not
    seven; ``meme_daily_ficha_render.render_week`` classifies each position
    itself, the same rules the daily ficha uses."""
    start_day = end_day - timedelta(days=6)
    day_start, _ = day_bounds(start_day)
    _, day_end = day_bounds(end_day)
    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    try:
        async with role_session(factory, db_role=DB_ROLE) as session:
            rows = await _rows(session, _POSITIONS, {"day_start": day_start, "day_end": day_end})
            positions = [await _real_position(session, row) for row in rows]
    finally:
        await engine.dispose()
    by_day: dict[str, list[RealPosition]] = {}
    for position in positions:
        key = position.entry_at.astimezone(SAO_PAULO).date().isoformat()
        by_day.setdefault(key, []).append(position)
    return by_day
