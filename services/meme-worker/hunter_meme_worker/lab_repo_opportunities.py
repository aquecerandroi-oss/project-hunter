"""The writes and reads of EXP-M26's opportunity record (R1, ``0066``) — as
``hunter_worker``, inside the minute's own transaction (``lab._gate_step``),
never opening one of their own (``lab_repo.py``'s discipline).

**Every step is its own savepoint, and none of them can take the tick down.**
A proposal that fails to insert rolls back to its savepoint and the opportunity
is still recorded, with ``no_proposal_reason = 'insert_failed'`` (design §7 R1:
"a transaction rolled back whole is not enough"). An opportunity whose full row
fails is retried as a **minimal** row (``fidelity = 'write_failed'``) in a second
savepoint: that row is the durable marker that makes a later pass of the same
mint impossible to record as the first. Only when both fail is the pair lost —
counted, logged, and remembered by the process so its next pass is written
``earlier_pass_unrecorded``.

**The first opportunity is decided by the database, not by a prior read.** The
row is inserted ``ON CONFLICT (rule_set_id, mint) DO NOTHING``; ``fidelity`` is
computed in the same statement: any proposal of the same set on the same mint up
to this minute that **this pass did not insert** (``fresh_proposal_id``) was
committed by an earlier run that left no row — an earlier minute, or this very
minute re-evaluated after a restart (Astra, round 2) — so this one is
``earlier_pass_unrecorded``, never a substitute.

**Timeouts do not leak.** ``SET LOCAL`` survives ``RELEASE SAVEPOINT``; the
bounded photo read restores the previous ``statement_timeout`` before leaving
its savepoint (on failure the rollback to the savepoint restores it).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.logging import get_logger
from hunter_meme_worker.db_errors import db_error_fields
from hunter_meme_worker.lab_repo import insert_proposals
from hunter_meme_worker.repo_lines import load_line_points

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.meme.lines import LinePoint
    from hunter_meme_worker.proposals import GateRow, ProposalDraft

__all__ = [
    "LINE_POINTS_TIMEOUT_MS",
    "bounded_line_points",
    "insert_opportunity",
    "insert_proposal_linked",
    "recorded_mints",
]

_logger = get_logger(__name__)

LINE_POINTS_TIMEOUT_MS = 5000
"""Sixteen minutes of photos for the few mints that passed a pure gate for the
first time this minute (``repo_lines``' own read, partition-pruned by
``observed_at``); slower is a database in trouble, and the row is written with
``coverage_status = 'unread'`` rather than the tick dying."""

_RECORDED = text(
    "SELECT mint FROM meme_mature_opportunities "
    "WHERE rule_set_id = CAST(:rule_set_id AS uuid) AND mint = ANY(:mints)"
)
_EXISTING_PROPOSAL = text(
    "SELECT id FROM meme_proposals WHERE rule_set_id = CAST(:rule_set_id AS uuid) "
    "  AND mint = :mint AND features_end_time = :features_end_time AND origin = 'rules'"
)
"""The exact identity of the proposals' idempotence key (``lab_repo._INSERT_PROPOSAL``)."""

_COLUMNS = (
    "id, rule_set_id, mint, evaluated_at, features_end_time, features_version, "
    "features_computed_at, code_ref, age_s, curve_progress_pct, mcap_sol, curve_volume_1m_sol, "
    "participation_pct, creator_net_seller, higher_lows, breakout_15m, distance_to_support_pct, "
    "line_reason, line_points, mcap_slope_15m, mayhem_enabled, mayhem_state, completed_at, "
    "migrated_at, inputs, gate, pedigree, coverage_version, coverage_status, coverage, "
    "proposal_refusals, proposal_id, no_proposal_reason, fidelity, lane_since"
)
_INSERT = text(
    f"INSERT INTO meme_mature_opportunities ({_COLUMNS}) VALUES ("  # noqa: S608 - frozen text  # nosec B608 -- identifiers and fragments are module-level constants, never an argument or a row; values are bound parameters
    "  :id, CAST(:rule_set_id AS uuid), :mint, :evaluated_at, :features_end_time, "
    "  :features_version, :features_computed_at, :code_ref, :age_s, :curve_progress_pct, "
    "  :mcap_sol, :curve_volume_1m_sol, :participation_pct, :creator_net_seller, :higher_lows, "
    "  :breakout_15m, :distance_to_support_pct, :line_reason, :line_points, :mcap_slope_15m, "
    "  :mayhem_enabled, :mayhem_state, :completed_at, :migrated_at, CAST(:inputs AS jsonb), "
    "  CAST(:gate AS jsonb), CAST(:pedigree AS jsonb), :coverage_version, :coverage_status, "
    "  CAST(:coverage AS jsonb), CAST(:proposal_refusals AS text[]), "
    "  CAST(:proposal_id AS uuid), :no_proposal_reason, "
    "  CASE WHEN CAST(:fidelity AS text) IN ('write_failed', 'earlier_pass_unrecorded') "
    "       THEN CAST(:fidelity AS text) "
    "       WHEN EXISTS (SELECT 1 FROM meme_proposals p "
    "                    WHERE p.rule_set_id = CAST(:rule_set_id AS uuid) AND p.mint = :mint "
    "                      AND p.origin = 'rules' AND p.features_end_time <= :features_end_time "
    "                      AND p.id IS DISTINCT FROM CAST(:fresh_proposal_id AS uuid)) "
    "       THEN 'earlier_pass_unrecorded' ELSE CAST(:fidelity AS text) END, "
    "  :lane_since) "
    "ON CONFLICT (rule_set_id, mint) DO NOTHING RETURNING fidelity"
)
_JSON_COLUMNS = ("inputs", "gate", "pedigree", "coverage")
_MINIMAL_KEYS = (
    "id",
    "rule_set_id",
    "mint",
    "evaluated_at",
    "features_end_time",
    "features_version",
    "code_ref",
    "coverage_version",
    "proposal_refusals",
    "proposal_id",
    "no_proposal_reason",
    "lane_since",
    "fresh_proposal_id",
)


async def recorded_mints(
    session: AsyncSession, rule_set_id: str, mints: Sequence[str]
) -> frozenset[str] | None:
    """The mints this set already has a row for (any fidelity); ``None`` when the
    read failed — in its own savepoint, so the minute's transaction survives."""
    if not mints:
        return frozenset()
    try:
        async with session.begin_nested():
            rows = await session.execute(
                _RECORDED, {"rule_set_id": rule_set_id, "mints": list(mints)}
            )
            found = frozenset(str(m) for m in rows.scalars().all())
    except DBAPIError as exc:
        _logger.warning(
            "meme_mature_recorded_read_failed", mints=len(mints), **db_error_fields(exc)
        )
        return None
    return found


async def insert_proposal_linked(
    session: AsyncSession, draft: ProposalDraft
) -> tuple[str | None, str | None]:
    """``(proposal_id, None)`` — inserted now, or the existing one of the same
    idempotence key — or ``(None, reason)``: ``insert_failed``/``not_inserted``."""
    try:
        async with session.begin_nested():
            if await insert_proposals(session, [draft]):
                return draft.id, None
            existing = await session.scalar(
                _EXISTING_PROPOSAL,
                {
                    "rule_set_id": draft.rule_set_id,
                    "mint": draft.mint,
                    "features_end_time": draft.features_end_time,
                },
            )
    except DBAPIError as exc:
        _logger.warning(
            "meme_mature_proposal_insert_failed", mint=draft.mint, **db_error_fields(exc)
        )
        return None, "insert_failed"
    return (str(existing), None) if existing is not None else (None, "not_inserted")


async def bounded_line_points(
    session: AsyncSession, *, mints: Sequence[str], end_time: datetime
) -> dict[str, list[LinePoint]] | None:
    """``repo_lines.load_line_points`` under its own timeout; ``None`` = unread."""
    if not mints:
        return {}
    try:
        async with session.begin_nested():
            prior = await session.scalar(text("SELECT current_setting('statement_timeout')"))
            await session.execute(text(f"SET LOCAL statement_timeout = {LINE_POINTS_TIMEOUT_MS}"))
            points = await load_line_points(session, mints=mints, end_time=end_time)
            await session.execute(
                text("SELECT set_config('statement_timeout', :prior, true)"), {"prior": prior}
            )
    except DBAPIError as exc:
        _logger.warning(
            "meme_mature_line_points_read_failed", mints=len(mints), **db_error_fields(exc)
        )
        return None
    return points


def _bound(values: Mapping[str, Any]) -> dict[str, Any]:
    bound = dict(values)
    for column in _JSON_COLUMNS:
        if column in bound and bound[column] is not None:
            bound[column] = json.dumps(bound[column])
    return bound


def _minimal(values: Mapping[str, Any], error: str) -> dict[str, Any]:
    kept = {key: values[key] for key in _MINIMAL_KEYS}
    nulls = {col.strip(): None for col in _COLUMNS.split(",") if col.strip() not in kept}
    return {
        **nulls,
        **kept,
        "inputs": {"write_failed": error},
        "gate": [],
        "coverage_status": "unread",
        "coverage": {"version": values["coverage_version"], "write_failed": error},
        "fidelity": "write_failed",
    }


async def _insert(session: AsyncSession, values: Mapping[str, Any]) -> str | None:
    async with session.begin_nested():
        return await session.scalar(_INSERT, _bound(values))


async def insert_opportunity(session: AsyncSession, values: Mapping[str, Any]) -> str:
    """``inserted:<fidelity>``, ``already_recorded``, or ``failed`` (both the
    full row and its minimal marker were refused)."""
    try:
        fidelity = await _insert(session, values)
    except DBAPIError as exc:
        fields = db_error_fields(exc)
        _logger.warning("meme_mature_opportunity_write_failed", mint=values["mint"], **fields)
        try:
            error = str(fields.get("sqlstate") or fields.get("error"))
            fidelity = await _insert(session, _minimal(values, error))
        except DBAPIError as again:
            _logger.error(
                "meme_mature_opportunity_marker_failed",
                mint=values["mint"],
                **db_error_fields(again),
            )
            return "failed"
    return "already_recorded" if fidelity is None else f"inserted:{fidelity}"


async def linked_proposal(session: AsyncSession, rule_set_id: str, row: GateRow) -> str | None:
    """The proposal of this set, mint and minute (the exact idempotence key), when an
    earlier run committed it — the link a lost row owes; ``None`` if there is none or
    the read failed (savepoint: the minute's transaction survives)."""
    try:
        async with session.begin_nested():
            found = await session.scalar(
                _EXISTING_PROPOSAL,
                {"rule_set_id": rule_set_id, "mint": row.mint, "features_end_time": row.end_time},
            )
    except DBAPIError as exc:
        _logger.warning("meme_mature_link_read_failed", mint=row.mint, **db_error_fields(exc))
        return None
    return None if found is None else str(found)
