"""Keyset cursor for ``GET /meme/tokens`` (T4.3).

Not ``repositories/base.py``'s ``encode_cursor``/``decode_cursor``: those are
fixed to ``(created_at: datetime, id: uuid.UUID)``, and a mint's sort value is
one of three different types (``mcap``/``progress`` are ``Decimal``, ``age``
is a ``datetime``) with a text primary key (``mint``), not a UUID. This mirrors
the same "opaque base64, not a secret" contract on a shape that fits here.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import status

from hunter_api.errors import HunterError
from hunter_core.domain.types import ensure_utc

__all__ = [
    "MAX_CURSOR_LENGTH",
    "SORT_COLUMNS",
    "InvalidMemeCursorError",
    "decode_token_cursor",
    "encode_token_cursor",
]

MAX_CURSOR_LENGTH = 128
SORT_COLUMNS: dict[str, str] = {
    "mcap": "mcap_sol",
    "age": "token_created_at",
    "progress": "curve_progress_pct",
}
"""Column names as they read in ``meme_radar_features_v1``
(``.claude/state/notes-T4.2.md`` §"contrato" §6) -- ``age`` sorts by the
view's ``token_created_at`` (the ``meme_tokens.created_at`` this radar
observed, aliased so the view's own ``end_time``/``mint`` are never
shadowed), not a bare ``created_at``."""


class InvalidMemeCursorError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-meme-cursor",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The pagination cursor is not valid.",
        )


def encode_token_cursor(sort: str, sort_value: Decimal | datetime | None, mint: str) -> str:
    """``sort`` names which column ``sort_value`` belongs to (so decoding
    knows which type to parse back); ``mint`` is the stable tiebreaker for
    equal or ``NULL`` sort values."""
    raw_value = "" if sort_value is None else str(sort_value)
    raw = f"{sort}|{raw_value}|{mint}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_token_cursor(cursor: str | None) -> tuple[Decimal | datetime | None, str] | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidMemeCursorError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        sort, raw_value, mint = raw.split("|", 2)
        if sort not in SORT_COLUMNS or not mint:
            raise InvalidMemeCursorError
        if raw_value == "":
            return None, mint
        value: Decimal | datetime = (
            ensure_utc(datetime.fromisoformat(raw_value)) if sort == "age" else Decimal(raw_value)
        )
        return value, mint
    except (ValueError, binascii.Error, UnicodeDecodeError, InvalidOperation):
        raise InvalidMemeCursorError from None
