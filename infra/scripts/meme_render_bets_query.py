"""T4.25 — a exportação: uma leitura só, na VPS, como ``hunter_app``.

:func:`gather_day` roda dentro da imagem publicada (``compose.sh ops``) e só
faz ``SELECT``: as apostas **fechadas** de um dia de Brasília com a fita em
volta de cada uma — ``meme_features_15s``, ``meme_features_1m`` com as colunas
de linha da ``meme_features_v3`` (``docs/DATABASE.md`` §38.1) e as fotografias
cruas de ``meme_curve_snapshots`` — de 10 min antes da entrada a 10 min depois
da saída. Nada é escrito na VPS; o JSONL sai pelo stdout ou por ``--out``.

O modelo do JSONL (e a geometria das linhas) mora em
``meme_render_bets_model.py``, irmão por orçamento de arquivo (350 linhas).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from meme_diary import day_bounds
from meme_render_bets_model import PAD, jsonable
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DB_ROLE = "hunter_app"

_BETS = text(
    "SELECT b.id::text AS bet_id, r.name || '/' || r.version AS rule_set, r.kind, r.exp_ref, "
    "       r.code_ref, r.params AS rule_set_params, b.mint, t.symbol, b.leg, "
    "       b.outcome_quality, b.outcome_quality_reason, b.entry_at, b.exit_at, "
    "       b.entry, b.exit, b.params, b.r_multiple, b.pnl_sol, b.initial_risk_sol, "
    "       b.high_water_x, b.creator_sold_seen_at, b.creator_sold_fraction, "
    "       p.suggested ->> 'manual_plan' AS manual_plan "
    "FROM meme_paper_bets b "
    "JOIN meme_rule_sets r ON r.id = b.rule_set_id "
    "LEFT JOIN meme_tokens t ON t.mint = b.mint "
    "LEFT JOIN meme_proposals p ON p.id = b.proposal_id "
    "WHERE b.status = 'closed' AND b.entry_at >= :day_start AND b.entry_at < :day_end "
    "  AND (CAST(:rule_set AS text) IS NULL OR r.name || '/' || r.version = :rule_set) "
    "  AND (CAST(:with_indeterminate AS boolean) "
    "       OR coalesce(b.outcome_quality, 'measured') = 'measured') "
    "ORDER BY b.entry_at, b.id"
)
"""Only **closed** bets: a bet still open has no exit to draw and no R to name.
``outcome_quality`` travels with the row so an ``indeterminate`` close (T4.16)
can be drawn — labelled as such — without ever being counted as a measurement."""

_FAST = text(
    "SELECT DISTINCT ON (as_of) as_of, mcap_sol FROM meme_features_15s "
    "WHERE mint = :mint AND as_of >= :from_at AND as_of <= :to_at "
    "ORDER BY as_of, features_version DESC"
)
_MINUTES = text(
    "SELECT DISTINCT ON (end_time) end_time, mcap_sol, support_line_sol, support_line_slope, "
    "       high_15m_sol, low_15m_sol, breakout_15m, higher_lows, line_reason "
    "FROM meme_features_1m WHERE mint = :mint AND end_time >= :from_at AND end_time <= :to_at "
    "ORDER BY end_time, features_version DESC"
)
"""``DISTINCT ON`` with the highest ``features_version`` per instant: a mint
folded by two versions in the same minute is one point on the chart, the newest."""

_SNAPSHOTS = text(
    "SELECT observed_at, source, mcap_sol, complete FROM meme_curve_snapshots "
    "WHERE mint = :mint AND observed_at >= :from_at AND observed_at <= :to_at "
    "ORDER BY observed_at, source"
)


async def _series(session: AsyncSession, mint: str, window: Mapping[str, Any]) -> dict[str, Any]:
    params = {"mint": mint, **window}
    fast = (await session.execute(_FAST, params)).all()
    minutes = (await session.execute(_MINUTES, params)).mappings().all()
    snaps = (await session.execute(_SNAPSHOTS, params)).all()
    return {
        "features_15s": [[jsonable(r[0]), jsonable(r[1])] for r in fast],
        "features_1m": [jsonable(dict(m)) for m in minutes],
        "snapshots": [[jsonable(s[0]), s[1], jsonable(s[2]), s[3]] for s in snaps],
    }


def _snapshot_mcap(payload: dict[str, Any]) -> Any:
    """``mcap_sol`` da fotografia que precificou a ponta — ``None`` sem fotografia."""
    snapshot: dict[str, Any] = payload.get("snapshot") or {}
    return snapshot.get("mcap_sol")


async def _record(session: AsyncSession, row: dict[str, Any], day: date) -> dict[str, Any]:
    entry_at, exit_at = row["entry_at"], row["exit_at"]
    window = {"from_at": entry_at - PAD, "to_at": exit_at + PAD}
    entry: dict[str, Any] = row["entry"] or {}
    exit_: dict[str, Any] = row["exit"] or {}
    record: dict[str, Any] = {
        "day": day.isoformat(),
        "exit_reason": exit_.get("reason"),
        "entry_mcap_sol": _snapshot_mcap(entry),
        "exit_mcap_sol": _snapshot_mcap(exit_),
        "sol_spent": entry.get("sol_spent"),
        "window": {"from": jsonable(window["from_at"]), "to": jsonable(window["to_at"])},
    }
    for key, value in row.items():
        if key not in ("entry", "exit"):
            record[key] = jsonable(value)
    record.update(await _series(session, str(row["mint"]), window))
    return record


async def gather_day(
    day: date, *, rule_set: str | None = None, with_indeterminate: bool = False
) -> list[dict[str, Any]]:
    """Every closed bet of the Brasília ``day`` with the tape around it."""
    from hunter_core.db.session import create_engine, create_session_factory, role_session
    from hunter_core.settings import get_settings

    day_start, day_end = day_bounds(day)
    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    out: list[dict[str, Any]] = []
    try:
        async with role_session(factory, db_role=DB_ROLE) as session:
            rows = (
                await session.execute(
                    _BETS,
                    {
                        "day_start": day_start,
                        "day_end": day_end,
                        "rule_set": rule_set,
                        "with_indeterminate": with_indeterminate,
                    },
                )
            ).mappings()
            for row in rows:
                out.append(await _record(session, dict(row), day))
    finally:
        await engine.dispose()
    return out


def write_jsonl(records: Sequence[Mapping[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    path.write_text(body, encoding="utf-8")
    return len(records)
