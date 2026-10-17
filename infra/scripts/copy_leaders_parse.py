"""Reading one ``/pnl-leaderboard`` view into typed rows (split out of the rule module to
keep it under the file-size budget). Only the allowed numeric fields survive: never names,
bios, images or user ids. A row that cannot be read exactly, or that repeats an address already
seen in the same view, is counted as malformed -- and a view with a malformed row is incomplete
(rule item 11), so the run ends without a selection.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast


class RuleError(ValueError):
    """Bad input to the rule (an invalid or excess ``--include``)."""


class BoardShapeError(RuleError):
    """A leaderboard response without a usable ``entries`` list."""


@dataclass(frozen=True, slots=True)
class BoardRow:
    address: str
    period: str
    sort: str
    position: int
    realized_pnl_sol: Decimal
    unrealized_pnl_sol: Decimal
    buy_spend_sol: Decimal
    positions_count: int
    is_verified: bool | None
    last_refreshed_at_ms: int | None


@dataclass(frozen=True, slots=True)
class ParsedBoard:
    period: str
    sort: str
    rows: tuple[BoardRow, ...]
    malformed: int
    window_start_sec: int | None


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        return None
    return int(value) if value == int(value) else None


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return cast("Mapping[str, Any]", value) if isinstance(value, Mapping) else None


def _row(period: str, sort: str, position: int, value: Any) -> BoardRow | None:
    raw = _mapping(value)
    if raw is None:
        return None
    address = raw.get("walletAddress")
    realized = _decimal(raw.get("realizedPnlSol"))
    unrealized = _decimal(raw.get("unrealizedPnlSol"))
    spend = _decimal(raw.get("buySpendSol"))
    count = _integer(raw.get("positionsCount"))
    if not isinstance(address, str) or not address:
        return None
    if realized is None or unrealized is None or spend is None or count is None:
        return None
    verified = raw.get("isVerified")
    return BoardRow(
        address=address,
        period=period,
        sort=sort,
        position=position,
        realized_pnl_sol=realized,
        unrealized_pnl_sol=unrealized,
        buy_spend_sol=spend,
        positions_count=count,
        is_verified=verified if isinstance(verified, bool) else None,
        last_refreshed_at_ms=_integer(raw.get("lastRefreshedAtMs")),
    )


def parse_board(period: str, sort: str, payload: Any) -> ParsedBoard:
    """Keep only the allowed numeric fields (never names, bios or images)."""
    body = _mapping(payload)
    entries = cast("list[Any]", body.get("entries")) if body is not None else None
    if body is None or not isinstance(entries, list) or not entries:
        raise BoardShapeError(f"{period}:{sort}: no usable 'entries' list in the response")
    rows: list[BoardRow] = []
    seen: set[str] = set()
    malformed = 0
    for index, raw in enumerate(entries, start=1):
        row = _row(period, sort, index, raw)
        if row is None or row.address in seen:  # a repeated address is ambiguous: malformed
            malformed += 1
        else:
            seen.add(row.address)
            rows.append(row)
    window = _integer(body.get("windowStartSec"))
    return ParsedBoard(period, sort, tuple(rows), malformed, window)
