"""Every row the daily close reads — as ``hunter_app`` (``SELECT`` only), from
the Lab's own tables. Nothing here writes; nothing here invents a number.

A bet's "at entry" features are read from the **last closed minute before the
fill** (``meme_features_1m``, ``end_time <= entry_at``, at most 10 minutes
back) — never from a later row; the pedigree counts (``creator_prior_1h``,
``symbol_dup_24h``) count only mints created **before** the bet's mint; both
are ``NULL`` when the token's creation time is unknown, never zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from meme_close_lessons import ClosedBet, day_lessons, leave_top_out
from meme_close_render import CloseInputs, Coverage, ExpAllTime, OperatorDay
from meme_close_stats import PLACES, Sample, block_ci
from meme_diary import day_bounds
from meme_diary_render import SAO_PAULO, WalletTradeLine
from sqlalchemy import text

from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.domain.types import utcnow
from hunter_core.settings import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DB_ROLE = "hunter_app"
TICK_GAP = timedelta(minutes=3)

_CLOSED_BETS = text(
    "SELECT b.mint, r.name || '/' || r.version AS rule_set, r.exp_ref, r.kind, b.entry_at, "
    "       b.exit_at, b.exit ->> 'reason' AS exit_reason, b.r_multiple, b.pnl_sol, "
    "       b.initial_risk_sol, t.created_at, t.pool_created_at, "
    "       p.quote ->> 'curve_progress_pct' AS progress_pct, "
    "       f.snipers, f.top10_share, f.dev_share, "
    "       CASE WHEN t.created_at IS NULL OR t.creator IS NULL THEN NULL ELSE "
    "         (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator = t.creator "
    "            AND t2.mint <> t.mint AND t2.created_at < t.created_at "
    "            AND t2.created_at >= t.created_at - interval '1 hour') END AS creator_prior_1h, "
    "       CASE WHEN t.created_at IS NULL OR t.symbol IS NULL THEN NULL ELSE "
    "         (SELECT count(*) FROM meme_tokens t3 WHERE t3.symbol = t.symbol "
    "            AND t3.mint <> t.mint AND t3.created_at < t.created_at "
    "            AND t3.created_at >= t.created_at - interval '24 hours') END AS symbol_dup_24h "
    "FROM meme_paper_bets b "
    "JOIN meme_rule_sets r ON r.id = b.rule_set_id "
    "LEFT JOIN meme_proposals p ON p.id = b.proposal_id "
    "LEFT JOIN meme_tokens t ON t.mint = b.mint "
    "LEFT JOIN LATERAL (SELECT f.snipers, f.top10_share, f.dev_share FROM meme_features_1m f "
    "  WHERE f.mint = b.mint AND f.end_time <= b.entry_at "
    "    AND f.end_time > b.entry_at - interval '10 minutes' "
    "  ORDER BY f.end_time DESC, f.features_version DESC LIMIT 1) f ON true "
    "WHERE b.status = 'closed' AND b.entry_at >= :day_start AND b.entry_at < :day_end "
    "ORDER BY b.entry_at, b.id"
)
_ACTIVE_SETS = text(
    "SELECT name || '/' || version AS rule_set, exp_ref, kind FROM meme_rule_sets "
    "WHERE status = 'active' ORDER BY name, version"
)
_ALL_TIME = text(
    "SELECT r.name || '/' || r.version AS rule_set, b.mint, b.r_multiple, "
    "       b.exit ->> 'reason' AS exit_reason, "
    "       (b.entry_at AT TIME ZONE 'America/Sao_Paulo')::date AS day_brt "
    "FROM meme_paper_bets b JOIN meme_rule_sets r ON r.id = b.rule_set_id "
    "WHERE r.status = 'active' AND b.status = 'closed' AND b.entry_at < :day_end "
    "ORDER BY b.entry_at, b.id"
)
_COVERAGE = text(
    "SELECT count(*) AS rows, count(*) FILTER (WHERE curve_progress_pct IS NOT NULL) AS with_progress, "
    "       count(*) FILTER (WHERE buys_1m IS NOT NULL) AS with_tape, "
    "       count(*) FILTER (WHERE support_line_sol IS NOT NULL) AS with_line, "
    "       count(*) FILTER (WHERE hype_score IS NOT NULL) AS with_hype, "
    "       count(DISTINCT mint) AS mints, count(DISTINCT end_time) AS minutes "
    "FROM meme_features_1m WHERE end_time > :day_start AND end_time <= :day_end "
    "  AND features_version = (SELECT max(features_version) FROM meme_features_1m "
    "                          WHERE end_time > :day_start AND end_time <= :day_end)"
)
_TICKS = text(
    "SELECT ticked_at, rows_evaluated, refusals FROM meme_lab_ticks "
    "WHERE ticked_at >= :day_start AND ticked_at < :day_end ORDER BY ticked_at"
)
_OPERATOR = text(
    "SELECT p.status, p.origin, p.proposed_at, p.decided_at, b.r_multiple, b.status AS bet_status "
    "FROM meme_proposals p JOIN meme_rule_sets r ON r.id = p.rule_set_id "
    "LEFT JOIN meme_paper_bets b ON b.id = p.bet_id "
    "WHERE r.kind = 'operator' AND p.proposed_at >= :day_start AND p.proposed_at < :day_end "
    "ORDER BY p.proposed_at"
)


def _seconds(later: datetime | None, earlier: datetime | None) -> int | None:
    if later is None or earlier is None:
        return None
    return int((later - earlier).total_seconds())


def _same_slot(created_at: datetime | None, pool_created_at: datetime | None) -> bool | None:
    if created_at is None:
        return None
    return pool_created_at is not None and pool_created_at - created_at <= timedelta(seconds=1)


def _closed_bet(r: Mapping[str, Any]) -> ClosedBet:
    return ClosedBet(
        mint=str(r["mint"]),
        rule_set=str(r["rule_set"]),
        exp_ref=r["exp_ref"],
        kind=str(r["kind"]),
        entry_at=r["entry_at"],
        exit_at=r["exit_at"],
        exit_reason=str(r["exit_reason"] or "desconhecido"),
        r_multiple=Decimal(r["r_multiple"]),
        pnl_sol=Decimal(r["pnl_sol"]),
        initial_risk_sol=Decimal(r["initial_risk_sol"]),
        age_at_entry_s=_seconds(r["entry_at"], r["created_at"]),
        progress_pct=None if r["progress_pct"] is None else Decimal(str(r["progress_pct"])),
        snipers=None if r["snipers"] is None else int(r["snipers"]),
        top10_share=None if r["top10_share"] is None else Decimal(r["top10_share"]),
        dev_share=None if r["dev_share"] is None else Decimal(r["dev_share"]),
        same_slot=_same_slot(r["created_at"], r["pool_created_at"]),
        creator_prior_1h=None if r["creator_prior_1h"] is None else int(r["creator_prior_1h"]),
        symbol_dup_24h=None if r["symbol_dup_24h"] is None else int(r["symbol_dup_24h"]),
    )


def _share(rows: Sequence[Mapping[str, Any]], reasons: set[str]) -> Decimal | None:
    if not rows:
        return None
    hits = sum(1 for r in rows if r["exit_reason"] in reasons)
    return (Decimal(hits * 100) / len(rows)).quantize(PLACES)


def _all_time(
    sets: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]], day: date
) -> list[ExpAllTime]:
    by_set: dict[str, list[Mapping[str, Any]]] = {}
    for r in rows:
        by_set.setdefault(str(r["rule_set"]), []).append(r)
    out: list[ExpAllTime] = []
    for s in sets:
        mine = by_set.get(str(s["rule_set"]), [])
        interval = block_ci(
            Sample(
                blocks=tuple(str(r["day_brt"]) for r in mine),
                values=tuple(Decimal(r["r_multiple"]) for r in mine),
            )
        )
        today = [r for r in mine if r["day_brt"] == day]
        best = max((Decimal(r["r_multiple"]) for r in mine), default=None)
        reasons: dict[str, int] = {}
        for r in today:
            reasons[str(r["exit_reason"])] = reasons.get(str(r["exit_reason"]), 0) + 1
        out.append(
            ExpAllTime(
                rule_set=str(s["rule_set"]),
                exp_ref=s["exp_ref"],
                kind=str(s["kind"]),
                n=interval.n,
                days=interval.blocks,
                mean=interval.mean,
                ci95=interval.ci95,
                total=interval.total,
                target_share=_share(mine, {"target"}),
                dead_or_time_share=_share(mine, {"dead", "time_stop"}),
                best_r=best,
                without_best=None if best is None else interval.total - best,
                today_n=len(today),
                today_total=sum((Decimal(r["r_multiple"]) for r in today), Decimal(0)),
                today_reasons=reasons,
            )
        )
    return out


def _coverage(row: Mapping[str, Any], ticks: Sequence[Mapping[str, Any]]) -> Coverage:
    refusals: dict[str, dict[str, int]] = {}
    gaps = 0
    previous: datetime | None = None
    for t in ticks:
        at: datetime = t["ticked_at"]
        if previous is not None and at - previous > TICK_GAP:
            gaps += 1
        previous = at
        raw = t["refusals"]
        if not isinstance(raw, dict):
            continue
        for rule_set, reasons in cast(dict[str, Any], raw).items():
            if not isinstance(reasons, dict):
                continue
            bucket = refusals.setdefault(str(rule_set), {})
            for reason, count in cast(dict[str, Any], reasons).items():
                bucket[str(reason)] = bucket.get(str(reason), 0) + int(count)
    return Coverage(
        rows=int(row["rows"]),
        with_progress=int(row["with_progress"]),
        with_tape=int(row["with_tape"]),
        with_line=int(row["with_line"]),
        with_hype=int(row["with_hype"]),
        mints=int(row["mints"]),
        minutes=int(row["minutes"]),
        ticks=len(ticks),
        first_tick=ticks[0]["ticked_at"] if ticks else None,
        last_tick=ticks[-1]["ticked_at"] if ticks else None,
        gaps=gaps,
        rows_evaluated=sum(int(t["rows_evaluated"]) for t in ticks),
        refusals=refusals,
    )


def _operator(rows: Sequence[Mapping[str, Any]]) -> OperatorDay:
    by_loop = [r for r in rows if r["origin"] == "rules"]
    decided = [r for r in by_loop if r["status"] not in ("proposed", "expired")]
    return OperatorDay(
        proposed=len(by_loop),
        approved=sum(1 for r in by_loop if r["status"] in ("approved", "filled", "unfilled")),
        rejected=sum(1 for r in by_loop if r["status"] == "rejected"),
        expired=sum(1 for r in by_loop if r["status"] == "expired"),
        filled=sum(1 for r in by_loop if r["status"] == "filled"),
        unfilled=sum(1 for r in by_loop if r["status"] == "unfilled"),
        manual=sum(1 for r in rows if r["origin"] == "operator"),
        latency_s=tuple(
            s for r in decided if (s := _seconds(r["decided_at"], r["proposed_at"])) is not None
        ),
        r_approved=tuple(
            Decimal(r["r_multiple"])
            for r in rows
            if r["bet_status"] == "closed" and r["r_multiple"] is not None
        ),
    )


async def _rows(
    session: AsyncSession, query: Any, params: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    return [dict(r) for r in (await session.execute(query, params)).mappings().all()]


async def gather_close(
    day: date, *, real_observed: Sequence[WalletTradeLine], predictions: Mapping[str, str | None]
) -> CloseInputs:
    day_start, day_end = day_bounds(day)
    window = {"day_start": day_start, "day_end": day_end}
    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    try:
        async with role_session(factory, db_role=DB_ROLE) as session:
            bets = [_closed_bet(r) for r in await _rows(session, _CLOSED_BETS, window)]
            sets = await _rows(session, _ACTIVE_SETS, {})
            all_time = _all_time(sets, await _rows(session, _ALL_TIME, {"day_end": day_end}), day)
            coverage_row = (await session.execute(_COVERAGE, window)).mappings().one()
            ticks = await _rows(session, _TICKS, window)
            operator = _operator(await _rows(session, _OPERATOR, window))
    finally:
        await engine.dispose()
    return CloseInputs(
        day=day,
        generated_at=utcnow().astimezone(SAO_PAULO),
        bets=bets,
        lessons=day_lessons(bets),
        top_out=leave_top_out(bets),
        coverage=_coverage(dict(coverage_row), ticks),
        operator=operator,
        reals=real_observed,
        all_time=all_time,
        predictions=predictions,
    )
