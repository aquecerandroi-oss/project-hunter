"""Row shapes, mappers and the keyset cursor for ``repositories/meme_desk.py``
(T4.7) — split out so that module stays under the 350-line budget, the same
way ``meme_rows.py``/``meme_cursor.py`` back ``repositories/meme.py``.

Field names follow the frozen contract
(``.claude/state/contrato-T4.6-T4.7-mesa-meme.md`` §Tabelas). JSONB columns
(``quote``/``reasons``/``suggested``/``decision``/``entry``/``exit``/``params``)
are carried as plain ``dict``/``list`` here; ``services/meme_desk_out.py`` is
where their known keys are read, tolerantly, into typed fields.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import status

from hunter_api.errors import HunterError
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping

__all__ = [
    "MAX_DESK_CURSOR_LENGTH",
    "BetRow",
    "CommandRow",
    "CurveQuoteRow",
    "DeskRow",
    "InvalidDeskCursorError",
    "ProposalRow",
    "RuleSetBalanceRow",
    "RuleSetRow",
    "SolUsdQuoteRow",
    "TokenIdentity",
    "bet_from_mapping",
    "command_from_mapping",
    "decode_desk_cursor",
    "encode_desk_cursor",
    "proposal_from_mapping",
    "rule_set_from_mapping",
    "token_from_mapping",
]

MAX_DESK_CURSOR_LENGTH = 160


@dataclass(frozen=True, slots=True)
class RuleSetRow:
    id: uuid.UUID
    name: str
    version: str
    kind: str
    params: dict[str, Any]
    status: str


@dataclass(frozen=True, slots=True)
class ProposalRow:
    id: uuid.UUID
    mint: str
    rule_set_id: uuid.UUID
    origin: str
    status: str
    proposed_at: datetime
    expires_at: datetime
    features_end_time: datetime | None
    quote: dict[str, Any] | None
    reasons: list[Any] | None
    suggested: dict[str, Any] | None
    decision: dict[str, Any] | None
    decided_by: str | None
    decided_at: datetime | None
    bet_id: uuid.UUID | None
    refusal: str | None
    mode: str = "paper"
    """0028 (T4.14): ``paper`` | ``live``; defaulted so every existing caller stays paper."""


@dataclass(frozen=True, slots=True)
class BetRow:
    id: uuid.UUID
    proposal_id: uuid.UUID
    rule_set_id: uuid.UUID
    mint: str
    mode: str
    status: str
    entry_at: datetime
    entry: dict[str, Any]
    initial_risk_sol: Decimal
    params: dict[str, Any]
    exit_at: datetime | None
    exit: dict[str, Any] | None
    pnl_sol: Decimal | None
    r_multiple: Decimal | None
    mark_sol: Decimal | None
    mark_at: datetime | None
    high_water_x: Decimal | None
    sol_usd_at_entry: Decimal | None
    sol_usd_at_exit: Decimal | None
    leg: str = "single"
    parent_bet_id: uuid.UUID | None = None
    """``0026`` (T4.10): defaults so a row mapped without the columns is ``single``."""
    mark_source: str | None = None
    mark_stale_s: int | None = None
    """``0029`` (T4.11): what priced the mark and how stale the tape was; ``None``
    on a row mapped without the columns — never a fabricated ``curve``."""


@dataclass(frozen=True, slots=True)
class CommandRow:
    id: uuid.UUID
    bet_id: uuid.UUID | None
    proposal_id: uuid.UUID | None
    command: str
    issued_by: str
    issued_at: datetime
    applied_at: datetime | None
    result: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class TokenIdentity:
    mint: str
    name: str | None
    symbol: str | None
    creator: str | None
    created_at: datetime | None
    mayhem_enabled: bool | None
    mayhem_state: str | None
    completed_at: datetime | None
    migrated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CurveQuoteRow:
    """The latest ``meme_curve_snapshots`` row of a mint — what a manual
    proposal's ``quote`` is built from."""

    observed_at: datetime
    source: str
    virtual_sol_reserves: Decimal
    virtual_token_reserves: Decimal
    real_token_reserves: Decimal
    mcap_sol: Decimal | None
    complete: bool


@dataclass(frozen=True, slots=True)
class DeskRow:
    """One line of the desk: the proposal plus whatever the joins found.
    ``token``/``rule_set`` are ``None`` only for a dangling reference (the
    contract's FKs are logical for ``mint``); ``bet`` is ``None`` until the
    loop fills the proposal."""

    proposal: ProposalRow
    token: TokenIdentity | None
    bet: BetRow | None
    rule_set: RuleSetRow | None
    rank: int


@dataclass(frozen=True, slots=True)
class RuleSetBalanceRow:
    rule_set: RuleSetRow
    open_sol: Decimal
    realized_today_sol: Decimal
    realized_total_sol: Decimal
    open_bets: int
    closed_today: int


@dataclass(frozen=True, slots=True)
class SolUsdQuoteRow:
    """The most recent SOL/USD quote the loop observed on any bet (entry or
    exit), with the instant it belongs to — never a live feed this API does
    not have."""

    rate: Decimal
    observed_at: datetime
    source: str | None


class InvalidDeskCursorError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-meme-desk-cursor",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The pagination cursor is not valid.",
        )


def encode_desk_cursor(rank: int, proposed_at: datetime, proposal_id: uuid.UUID) -> str:
    """``rank|iso|uuid`` — the desk orders by a derived rank (open proposals,
    then open bets, then history) before ``proposed_at DESC, id DESC``, so
    the cursor has to carry all three; ``repositories/base.py``'s two-part
    cursor cannot."""
    raw = f"{rank}|{ensure_utc(proposed_at).isoformat()}|{proposal_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_desk_cursor(cursor: str | None) -> tuple[int, datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_DESK_CURSOR_LENGTH:
        raise InvalidDeskCursorError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        rank_text, iso, raw_id = raw.split("|", 2)
        rank = int(rank_text)
        if rank < 0:
            raise InvalidDeskCursorError
        return rank, ensure_utc(datetime.fromisoformat(iso)), uuid.UUID(raw_id)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise InvalidDeskCursorError from None


def _optional(value: datetime | None) -> datetime | None:
    return ensure_utc(value) if value is not None else None


def _dict(value: object) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None  # type: ignore[arg-type]


def _list(value: object) -> list[Any] | None:
    return list(value) if isinstance(value, list) else None  # type: ignore[arg-type]


def rule_set_from_mapping(r: RowMapping) -> RuleSetRow:
    return RuleSetRow(
        id=r["id"],
        name=r["name"],
        version=r["version"],
        kind=r["kind"],
        params=_dict(r["params"]) or {},
        status=r["status"],
    )


def proposal_from_mapping(r: RowMapping) -> ProposalRow:
    return ProposalRow(
        id=r["id"],
        mint=r["mint"],
        rule_set_id=r["rule_set_id"],
        origin=r["origin"],
        status=r["status"],
        proposed_at=ensure_utc(r["proposed_at"]),
        expires_at=ensure_utc(r["expires_at"]),
        features_end_time=_optional(r["features_end_time"]),
        quote=_dict(r["quote"]),
        reasons=_list(r["reasons"]),
        suggested=_dict(r["suggested"]),
        decision=_dict(r["decision"]),
        decided_by=r["decided_by"],
        decided_at=_optional(r["decided_at"]),
        bet_id=r["bet_id"],
        refusal=r["refusal"],
        mode=str(r.get("mode") or "paper"),
    )


def bet_from_mapping(r: RowMapping) -> BetRow:
    return BetRow(
        id=r["id"],
        proposal_id=r["proposal_id"],
        rule_set_id=r["rule_set_id"],
        mint=r["mint"],
        mode=r["mode"],
        status=r["status"],
        entry_at=ensure_utc(r["entry_at"]),
        entry=_dict(r["entry"]) or {},
        initial_risk_sol=r["initial_risk_sol"],
        params=_dict(r["params"]) or {},
        exit_at=_optional(r["exit_at"]),
        exit=_dict(r["exit"]),
        pnl_sol=r["pnl_sol"],
        r_multiple=r["r_multiple"],
        mark_sol=r["mark_sol"],
        mark_at=_optional(r["mark_at"]),
        high_water_x=r["high_water_x"],
        sol_usd_at_entry=r["sol_usd_at_entry"],
        sol_usd_at_exit=r["sol_usd_at_exit"],
        leg=str(r.get("leg") or "single"),
        parent_bet_id=r.get("parent_bet_id"),
        mark_source=None if r.get("mark_source") is None else str(r["mark_source"]),
        mark_stale_s=None if r.get("mark_stale_s") is None else int(r["mark_stale_s"]),
    )


def command_from_mapping(r: RowMapping) -> CommandRow:
    return CommandRow(
        id=r["id"],
        bet_id=r["bet_id"],
        proposal_id=r["proposal_id"],
        command=r["command"],
        issued_by=r["issued_by"],
        issued_at=ensure_utc(r["issued_at"]),
        applied_at=_optional(r["applied_at"]),
        result=_dict(r["result"]),
    )


def token_from_mapping(r: RowMapping) -> TokenIdentity:
    return TokenIdentity(
        mint=r["mint"],
        name=r["name"],
        symbol=r["symbol"],
        creator=r["creator"],
        created_at=_optional(r["created_at"]),
        mayhem_enabled=r["mayhem_enabled"],
        mayhem_state=r["mayhem_state"],
        completed_at=_optional(r["completed_at"]),
        migrated_at=_optional(r["migrated_at"]),
    )
