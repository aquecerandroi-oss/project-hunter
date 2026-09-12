"""Every read and write the Lab loop makes — as ``hunter_worker``, never as owner.

Each function takes an ``AsyncSession`` opened by ``role_session(...,
db_role="hunter_worker")`` (the ``repo.py`` discipline: nothing here opens its
own transaction). The durable ledger is the tables of ``0022_meme_lab``; the
loop keeps no balance in memory — :func:`wallet_state` derives it from
``meme_paper_bets`` on every call, so a restart is not a reset (MUST-FIX 3).

Idempotence is a schema fact, not a prior read: a proposal is inserted
``ON CONFLICT (rule_set_id, mint, features_end_time) WHERE origin = 'rules' DO
NOTHING``, so a minute re-evaluated after a restart writes nothing twice.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_rows import ApprovedProposal, CommandRow, snapshot_from_row
from hunter_meme_worker.proposals import GateRow, ProposalDraft

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "apply_command",
    "cancel_proposal",
    "expire_proposals",
    "insert_proposals",
    "load_active_rule_sets",
    "load_approved_proposals",
    "load_gate_rows",
    "open_mints_for",
    "pending_commands",
]


_RULE_SETS = text(
    "SELECT id, name, version, kind, params, code_ref, exp_ref, status FROM meme_rule_sets "
    "WHERE status = 'active' ORDER BY name, version"
)

_GATE_ROWS = text(
    "SELECT f.mint, f.end_time, f.curve_progress_pct, f.progress_reason, f.mcap_sol, "
    "       f.creator_net_seller, f.curve_volume_1m_sol, "
    "       f.snapshot_observed_at, f.snapshot_source, "
    "       f.higher_lows, f.breakout_15m, f.distance_to_support_pct, f.line_reason, "
    "       f.hype_score, f.hype_reason, f.dev_share, f.dev_share_reason, f.snipers, "
    "       f.net_sol_flow_1m, f.buys_1m, f.sells_1m, f.unique_buyers, f.tape_reason, "
    "       f.holders, f.holders_reason, prev.holders AS holders_prev, "
    "       prev.curve_progress_pct AS progress_prev, "
    "       t.created_at, t.completed_at, t.migrated_at, t.initial_real_token_reserves, "
    "       t.symbol, "
    "       s.virtual_sol_reserves, s.virtual_token_reserves, s.real_sol_reserves, "
    "       s.real_token_reserves, s.total_supply, s.complete, s.mcap_sol AS snapshot_mcap_sol "
    "FROM meme_features_1m f "
    "JOIN meme_tokens t ON t.mint = f.mint "
    "LEFT JOIN meme_curve_snapshots s ON s.mint = f.mint "
    "  AND s.observed_at = f.snapshot_observed_at AND s.source = f.snapshot_source "
    "LEFT JOIN meme_features_1m prev ON prev.mint = f.mint "
    "  AND prev.features_version = f.features_version "
    "  AND prev.end_time = f.end_time - interval '1 minute' "
    "WHERE f.end_time = :minute AND f.features_version = :version"
)
"""T4.16: the minute before it (``prev``) is what "holders rising" and
"progress rising" are measured against on the minute clock — two consecutive
readings, the study's wording; the partition key is in the join, so the read
touches two minutes and never a month."""

_OPEN_MINTS = text(
    "SELECT mint FROM meme_proposals WHERE rule_set_id = :rule_set_id "
    "  AND status IN ('proposed', 'approved') "
    "UNION SELECT mint FROM meme_paper_bets WHERE rule_set_id = :rule_set_id AND status = 'open'"
)

_INSERT_PROPOSAL = text(
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, expires_at, "
    "  features_end_time, quote, reasons, suggested, decision, decided_by, decided_at) "
    "VALUES (:id, :mint, :rule_set_id, :origin, :status, :proposed_at, :expires_at, "
    "  :features_end_time, CAST(:quote AS jsonb), CAST(:reasons AS jsonb), "
    "  CAST(:suggested AS jsonb), CAST(:decision AS jsonb), :decided_by, :decided_at) "
    "ON CONFLICT (rule_set_id, mint, features_end_time) WHERE origin = 'rules' DO NOTHING "
    "RETURNING id"
)

_EXPIRE = text(
    "UPDATE meme_proposals SET status = 'expired' "
    "WHERE status = 'proposed' AND expires_at <= :now RETURNING id"
)

_APPROVED = text(
    "SELECT p.id, p.mint, p.rule_set_id, p.decision, p.decided_at, t.migrated_at "
    "FROM meme_proposals p LEFT JOIN meme_tokens t ON t.mint = p.mint "
    "WHERE p.status = 'approved' ORDER BY p.decided_at"
)

_PENDING_COMMANDS = text(
    "SELECT id, bet_id, proposal_id, command, issued_by, issued_at FROM meme_operator_commands "
    "WHERE applied_at IS NULL ORDER BY issued_at"
)
_APPLY_COMMAND = text(
    "UPDATE meme_operator_commands SET applied_at = :now, result = CAST(:result AS jsonb) "
    "WHERE id = :id AND applied_at IS NULL"
)
_CANCEL = text(
    "UPDATE meme_proposals SET status = 'rejected', "
    "  decided_by = coalesce(decided_by, :issued_by), decided_at = coalesce(decided_at, :now), "
    "  decision = coalesce(decision, '{}'::jsonb) || CAST(:note AS jsonb) "
    "WHERE id = :id AND status IN ('proposed', 'approved') RETURNING id"
)
_PROPOSAL_STATUS = text("SELECT status FROM meme_proposals WHERE id = :id")


async def load_active_rule_sets(session: AsyncSession) -> list[RuleSetSpec]:
    rows = (await session.execute(_RULE_SETS)).mappings().all()
    return [
        RuleSetSpec.from_params(
            id=str(r["id"]),
            name=str(r["name"]),
            version=str(r["version"]),
            kind=str(r["kind"]),
            exp_ref=r["exp_ref"],
            status=str(r["status"]),
            code_ref=str(r["code_ref"]),
            params=r["params"],
        )
        for r in rows
    ]


async def load_gate_rows(
    session: AsyncSession, *, minute: datetime, features_version: str
) -> list[GateRow]:
    """Every folded row of one closed minute, with its token and its snapshot."""
    rows = (
        await session.execute(_GATE_ROWS, {"minute": minute, "version": features_version})
    ).mappings()
    out: list[GateRow] = []
    for r in rows:
        snapshot = None
        if r["virtual_sol_reserves"] is not None and r["virtual_token_reserves"] > 0:
            snapshot = snapshot_from_row(
                {
                    **dict(r),
                    "observed_at": r["snapshot_observed_at"],
                    "source": r["snapshot_source"],
                }  # type: ignore[arg-type]
            )
        out.append(
            GateRow(
                mint=str(r["mint"]),
                end_time=r["end_time"],
                created_at=r["created_at"],
                curve_progress_pct=r["curve_progress_pct"],
                progress_reason=r["progress_reason"],
                mcap_sol=r["mcap_sol"],
                # T4.2c: the tape (swap-api) fills both; NULL still means "unknown"
                # and the gate refuses it by name (creator_net_seller_unknown /
                # curve_volume_1m_unknown), exactly as before the feed existed.
                creator_sold=r["creator_net_seller"],
                curve_volume_1m_sol=r["curve_volume_1m_sol"],
                completed_at=r["completed_at"],
                migrated_at=r["migrated_at"],
                snapshot=snapshot,
                # T4.10 (``0026``): the line and the hype of the minute, each
                # ``None`` with its reason; the gate refuses by that reason.
                higher_lows=r["higher_lows"],
                breakout_15m=r["breakout_15m"],
                distance_to_support_pct=r["distance_to_support_pct"],
                line_reason=r["line_reason"],
                hype_score=r["hype_score"],
                hype_reason=r["hype_reason"],
                dev_share=r["dev_share"],
                dev_share_reason=r["dev_share_reason"],
                snipers=r["snipers"],
                # T4.16: the flow of the minute and the two trends against the
                # minute before — ``None`` with its reason, refused by name.
                net_sol_flow_1m=r["net_sol_flow_1m"],
                buys_1m=r["buys_1m"],
                sells_1m=r["sells_1m"],
                unique_buyers_1m=r["unique_buyers"],
                tape_reason=r["tape_reason"],
                holders_rising=_rising(r["holders"], r["holders_prev"]),
                holders_reason=_trend_reason(r["holders"], r["holders_prev"], r["holders_reason"]),
                progress_rising=_rising(r["curve_progress_pct"], r["progress_prev"]),
                symbol=None if r["symbol"] is None else str(r["symbol"]),
            )
        )
    return out


def _rising(now: Any, before: Any) -> bool | None:
    return None if now is None or before is None else bool(now > before)


def _trend_reason(now: Any, before: Any, absent: str | None) -> str | None:
    if now is None:
        return absent or "no_holders_reader"
    return "too_few_readings" if before is None else None


async def open_mints_for(session: AsyncSession, rule_set_id: str) -> frozenset[str]:
    rows = await session.execute(_OPEN_MINTS, {"rule_set_id": rule_set_id})
    return frozenset(str(m) for m in rows.scalars().all())


async def insert_proposals(session: AsyncSession, drafts: Sequence[ProposalDraft]) -> int:
    inserted = 0
    for d in drafts:
        result = await session.execute(
            _INSERT_PROPOSAL,
            {
                "id": d.id,
                "mint": d.mint,
                "rule_set_id": d.rule_set_id,
                "origin": d.origin,
                "status": d.status,
                "proposed_at": d.proposed_at,
                "expires_at": d.expires_at,
                "features_end_time": d.features_end_time,
                "quote": json.dumps(d.quote),
                "reasons": json.dumps(d.reasons),
                "suggested": json.dumps(d.suggested),
                "decision": None if d.decision is None else json.dumps(d.decision),
                "decided_by": d.decided_by,
                "decided_at": d.decided_at,
            },
        )
        inserted += len(result.scalars().all())
    return inserted


async def expire_proposals(session: AsyncSession, *, now: datetime) -> int:
    return len((await session.execute(_EXPIRE, {"now": now})).scalars().all())


async def load_approved_proposals(session: AsyncSession) -> list[ApprovedProposal]:
    rows = (await session.execute(_APPROVED)).mappings().all()
    return [
        ApprovedProposal(
            id=str(r["id"]),
            mint=str(r["mint"]),
            rule_set_id=str(r["rule_set_id"]),
            decision=dict(r["decision"] or {}),
            decided_at=r["decided_at"],
            migrated=r["migrated_at"] is not None,
        )
        for r in rows
    ]


async def pending_commands(session: AsyncSession) -> list[CommandRow]:
    return [
        CommandRow(
            id=str(r["id"]),
            bet_id=None if r["bet_id"] is None else str(r["bet_id"]),
            proposal_id=None if r["proposal_id"] is None else str(r["proposal_id"]),
            command=str(r["command"]),
            issued_by=str(r["issued_by"]),
            issued_at=r["issued_at"],
        )
        for r in (await session.execute(_PENDING_COMMANDS)).mappings()
    ]


async def apply_command(
    session: AsyncSession, command_id: str, *, now: datetime, result: dict[str, Any]
) -> None:
    await session.execute(
        _APPLY_COMMAND, {"id": command_id, "now": now, "result": json.dumps(result)}
    )


async def cancel_proposal(
    session: AsyncSession, command: CommandRow, *, now: datetime
) -> dict[str, Any]:
    """A pending or approved-but-unfilled proposal becomes ``rejected``; else refused by name."""
    assert command.proposal_id is not None
    note = json.dumps({"cancelled_by": command.issued_by, "command_id": command.id})
    cancelled = (
        (
            await session.execute(
                _CANCEL,
                {
                    "id": command.proposal_id,
                    "issued_by": command.issued_by,
                    "now": now,
                    "note": note,
                },
            )
        )
        .scalars()
        .all()
    )
    if cancelled:
        return {"status": "applied", "proposal_status": "rejected"}
    current = await session.scalar(_PROPOSAL_STATUS, {"id": command.proposal_id})
    return {"status": "refused", "refusal": f"proposal_{current or 'missing'}"}
