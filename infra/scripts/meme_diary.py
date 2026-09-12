"""Write one day of the meme Lab into the Obsidian diary — report first, then apply.

T4.6, on the format ``obsidian/09-OPERATIONS/Diario-Meme/README.md`` fixed::

    uv run python infra/scripts/meme_diary.py --dry-run                 # today (Brasília), stdout
    uv run python infra/scripts/meme_diary.py --day 2026-09-12 --dry-run
    uv run python infra/scripts/meme_diary.py --day 2026-09-12 --apply  # writes the note

On the VPS this runs inside the published image, like every other ops tool::

    ./compose.sh run --rm ops python infra/scripts/meme_diary.py --dry-run

Reads only, as ``hunter_app`` (``SELECT`` on every ``0022`` table and view), and
``--apply`` writes exactly one file: ``Diario-Meme/<AAAA-MM-DD>.md``. A note that
already exists is **never overwritten**: the archivist completes section 6 by
hand and a datelined record is not rewritten (the folder's own rule). The
loop's heartbeat is read from Redis when reachable so the note can say whether
the loop was alive; Redis being down is written as "sem heartbeat", never as a
quiet loop.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from meme_diary_render import (
    SAO_PAULO,
    BetLine,
    DiaryInputs,
    RuleSetDay,
    render_diary,
)
from meme_diary_wallets import gather_wallets
from sqlalchemy import text

from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.domain.types import utcnow
from hunter_core.settings import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DB_ROLE = "hunter_app"
REPO_ROOT = Path(__file__).resolve().parents[2]
DIARY_DIR = REPO_ROOT / "obsidian" / "09-OPERATIONS" / "Diario-Meme"

_RULE_SETS = text(
    "SELECT id::text AS id, name, version, kind, exp_ref, params, created_at FROM meme_rule_sets "
    "ORDER BY status, name, version"
)
_WALLET_AT = text(
    "SELECT coalesce(sum(pnl_sol) FILTER (WHERE status = 'closed' AND exit_at < :at), 0) AS realized, "
    "       coalesce(sum(initial_risk_sol) FILTER (WHERE entry_at < :at "
    "                AND (exit_at IS NULL OR exit_at >= :at)), 0) AS exposure "
    "FROM meme_paper_bets WHERE rule_set_id = :rule_set_id"
)
_OPEN_AT = text(
    "SELECT mint, initial_risk_sol AS cost_sol, mark_sol FROM meme_paper_bets "
    "WHERE rule_set_id = :rule_set_id AND entry_at < :at AND (exit_at IS NULL OR exit_at >= :at) "
    "ORDER BY entry_at"
)
_DAY_STATS = text(
    "SELECT count(*) AS bets, count(*) FILTER (WHERE status = 'closed') AS closed, "
    "       count(*) FILTER (WHERE status = 'closed' AND pnl_sol > 0) AS wins, "
    "       count(*) FILTER (WHERE exit ->> 'reason' = 'rug_no_snapshot') AS rugs, "
    "       sum(r_multiple) FILTER (WHERE status = 'closed') AS r_day "
    "FROM meme_paper_bets WHERE rule_set_id = :rule_set_id "
    "  AND entry_at >= :day_start AND entry_at < :day_end"
)
_R_TOTAL = text(
    "SELECT sum(r_multiple) AS r_total FROM meme_paper_bets "
    "WHERE rule_set_id = :rule_set_id AND status = 'closed' AND exit_at < :day_end"
)
_CLOSED_SERIES = text(
    "SELECT pnl_sol FROM meme_paper_bets WHERE rule_set_id = :rule_set_id AND status = 'closed' "
    "  AND exit_at >= :since AND exit_at < :day_end ORDER BY exit_at, id"
)
_BETS = text(
    "SELECT b.mint, r.name || '/' || r.version AS rule_set, r.exp_ref, b.entry_at, b.exit_at, "
    "       b.exit ->> 'reason' AS exit_reason, b.r_multiple, b.pnl_sol, b.initial_risk_sol, "
    "       b.sol_usd_at_exit, b.exit -> 'sol_usd' ->> 'source' AS sol_usd_source, "
    "       b.exit -> 'sol_usd' ->> 'observed_at' AS sol_usd_observed_at "
    "FROM meme_paper_bets b JOIN meme_rule_sets r ON r.id = b.rule_set_id "
    "WHERE b.entry_at >= :day_start AND b.entry_at < :day_end ORDER BY b.entry_at"
)
_UNFILLED = text(
    "SELECT refusal, count(*) AS n FROM meme_proposals WHERE status = 'unfilled' "
    "  AND proposed_at >= :day_start AND proposed_at < :day_end GROUP BY refusal"
)
_EXPIRED = text(
    "SELECT count(*) FROM meme_proposals WHERE status = 'expired' "
    "  AND proposed_at >= :day_start AND proposed_at < :day_end"
)
_GAPS = text(
    "SELECT stream || '/' || reason AS key, count(*) AS n FROM meme_ingest_gaps "
    "WHERE gap_start >= :day_start AND gap_start < :day_end GROUP BY stream, reason"
)
_LAST_QUOTE = text(
    "SELECT sol_usd_at_exit AS price, exit -> 'sol_usd' ->> 'source' AS source, "
    "       exit -> 'sol_usd' ->> 'observed_at' AS observed_at "
    "FROM meme_paper_bets WHERE sol_usd_at_exit IS NOT NULL AND exit_at < :day_end "
    "ORDER BY exit_at DESC LIMIT 1"
)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=SAO_PAULO)
    return start, start + timedelta(days=1)


def max_drawdown(pnls: list[Decimal]) -> Decimal | None:
    """Deepest fall of the cumulative PnL below its running high (floored at 0)."""
    if not pnls:
        return None
    cumulative = peak = Decimal(0)
    worst = Decimal(0)
    for pnl in pnls:
        cumulative += pnl
        peak = max(peak, cumulative)
        worst = min(worst, cumulative - peak)
    return -worst


async def _rule_set_day(
    session: AsyncSession, row: Any, *, day_start: datetime, day_end: datetime
) -> RuleSetDay:
    rule_set_id, params = str(row["id"]), row["params"]
    wallet_max = Decimal(str(params["wallet_max_sol"]))
    start = (
        (await session.execute(_WALLET_AT, {"rule_set_id": rule_set_id, "at": day_start}))
        .mappings()
        .one()
    )
    end = (
        (await session.execute(_WALLET_AT, {"rule_set_id": rule_set_id, "at": day_end}))
        .mappings()
        .one()
    )
    stats = (
        (
            await session.execute(
                _DAY_STATS, {"rule_set_id": rule_set_id, "day_start": day_start, "day_end": day_end}
            )
        )
        .mappings()
        .one()
    )
    r_total = await session.scalar(_R_TOTAL, {"rule_set_id": rule_set_id, "day_end": day_end})
    day_series = [
        Decimal(v)
        for v in (
            await session.execute(
                _CLOSED_SERIES, {"rule_set_id": rule_set_id, "since": day_start, "day_end": day_end}
            )
        ).scalars()
    ]
    total_series = [
        Decimal(v)
        for v in (
            await session.execute(
                _CLOSED_SERIES,
                {
                    "rule_set_id": rule_set_id,
                    "since": datetime(2000, 1, 1, tzinfo=SAO_PAULO),
                    "day_end": day_end,
                },
            )
        ).scalars()
    ]
    open_positions = [
        {"mint": r["mint"], "cost_sol": Decimal(r["cost_sol"]), "mark_sol": r["mark_sol"]}
        for r in (
            await session.execute(_OPEN_AT, {"rule_set_id": rule_set_id, "at": day_end})
        ).mappings()
    ]
    realized_day = Decimal(end["realized"]) - Decimal(start["realized"])
    return RuleSetDay(
        name=str(row["name"]),
        version=str(row["version"]),
        kind=str(row["kind"]),
        exp_ref=row["exp_ref"],
        wallet_max_sol=wallet_max,
        balance_start_sol=wallet_max + Decimal(start["realized"]) - Decimal(start["exposure"]),
        balance_end_sol=wallet_max + Decimal(end["realized"]) - Decimal(end["exposure"]),
        realized_day_sol=realized_day,
        realized_total_sol=Decimal(end["realized"]),
        r_day=stats["r_day"],
        r_total=r_total,
        drawdown_day_sol=max_drawdown(day_series),
        drawdown_total_sol=max_drawdown(total_series),
        bets_day=int(stats["bets"]),
        closed_day=int(stats["closed"]),
        wins_day=int(stats["wins"]),
        rugs_day=int(stats["rugs"]),
        open_at_end=open_positions,
    )


async def _read_heartbeat_tick() -> datetime | None:
    """``lab_last_tick_at`` from ``hb:meme:radar``; ``None`` when Redis cannot answer."""
    from hunter_core.redis import create_redis, keys

    redis = create_redis(get_settings())
    try:
        raw = await redis.hget(keys.heartbeat("meme", "radar"), "lab_last_tick_at")  # type: ignore[reportUnknownMemberType]
    except Exception:  # Redis down is "no heartbeat read", written as such
        return None
    finally:
        await redis.aclose()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.decode() if isinstance(raw, bytes) else str(raw))
    except ValueError:
        return None


async def gather(day: date) -> DiaryInputs:
    day_start, day_end = day_bounds(day)
    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    window = {"day_start": day_start, "day_end": day_end}
    try:
        async with role_session(factory, db_role=DB_ROLE) as session:
            rule_rows = (await session.execute(_RULE_SETS)).mappings().all()
            rule_sets = [
                await _rule_set_day(session, r, day_start=day_start, day_end=day_end)
                for r in rule_rows
            ]
            bets = [
                BetLine(
                    mint=str(b["mint"]),
                    rule_set=str(b["rule_set"]),
                    exp_ref=b["exp_ref"],
                    entry_at=b["entry_at"],
                    exit_at=b["exit_at"],
                    exit_reason=b["exit_reason"],
                    r_multiple=b["r_multiple"],
                    pnl_sol=b["pnl_sol"],
                    pnl_usd=None
                    if b["pnl_sol"] is None or b["sol_usd_at_exit"] is None
                    else Decimal(b["pnl_sol"]) * Decimal(b["sol_usd_at_exit"]),
                    sol_usd_source=b["sol_usd_source"],
                    sol_usd_observed_at=b["sol_usd_observed_at"],
                    initial_risk_sol=Decimal(b["initial_risk_sol"]),
                )
                for b in (await session.execute(_BETS, window)).mappings()
            ]
            unfilled = Counter(
                {
                    str(r["refusal"]): int(r["n"])
                    for r in (await session.execute(_UNFILLED, window)).mappings()
                }
            )
            expired = int(await session.scalar(_EXPIRED, window) or 0)
            gaps = Counter(
                {
                    str(r["key"]): int(r["n"])
                    for r in (await session.execute(_GAPS, window)).mappings()
                }
            )
            quote = (await session.execute(_LAST_QUOTE, {"day_end": day_end})).mappings().first()
            clock_start = min((r["created_at"] for r in rule_rows), default=None)
            real_observed = await gather_wallets(session, day_start=day_start, day_end=day_end)
    finally:
        await engine.dispose()
    return DiaryInputs(
        day=day,
        generated_at=utcnow(),
        rule_sets=rule_sets,
        bets=bets,
        unfilled_by_refusal=unfilled,
        expired_proposals=expired,
        gaps_by_stream_reason=gaps,
        sol_usd=None if quote is None else Decimal(quote["price"]),
        sol_usd_source=None if quote is None else quote["source"],
        sol_usd_observed_at=None if quote is None else quote["observed_at"],
        clock_start=None if clock_start is None else clock_start.astimezone(SAO_PAULO).date(),
        lab_last_tick_at=await _read_heartbeat_tick(),
        real_observed=real_observed,
    )


async def _run(args: argparse.Namespace) -> int:
    day = date.fromisoformat(args.day) if args.day else utcnow().astimezone(SAO_PAULO).date()
    inputs = await gather(day)
    note = render_diary(inputs)
    target = DIARY_DIR / f"{day.isoformat()}.md"
    if not args.apply:
        print(note)
        print(f"--- dry-run: nada escrito; --apply gravaria {target.relative_to(REPO_ROOT)}")
        return 0
    if target.exists():
        print(
            f"RECUSADO: {target.relative_to(REPO_ROOT)} já existe (registro datado não se reescreve)",
            file=sys.stderr,
        )
        return 2
    if not any(r.closed_day for r in inputs.rule_sets) and not args.allow_empty:
        print(
            "RECUSADO: nenhuma aposta fechada no dia; use --allow-empty para registrar mesmo assim",
            file=sys.stderr,
        )
        return 3
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(note, encoding="utf-8")
    print(f"gravado: {target.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--day", help="dia em Brasília, AAAA-MM-DD (padrão: hoje)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="imprima a nota, não grave")
    mode.add_argument("--apply", action="store_true", help="grave a nota (recusa se já existir)")
    parser.add_argument(
        "--allow-empty", action="store_true", help="grave mesmo sem aposta fechada no dia"
    )
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
