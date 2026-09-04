"""The tenant-repository base and cursor pagination.

ARCHITECTURE.md §9: "Repositorios tenant-scoped: ``TenantRepository(session,
org_id)``; toda query passa por eles" and "Paginacao por cursor em toda lista".

Cursors are keyset cursors over ``(created_at, id)``, not offsets. An offset
re-reads and skips every earlier row, and it silently shifts under inserts —
which for an append-heavy table like ``audit_logs`` means a page-2 request can
show a row page 1 already showed, or skip one entirely. A keyset cursor is
stable and costs one index seek.

The encoding is base64 of ``<iso timestamp>|<uuid>``: opaque enough that
clients do not build cursors by hand, but not a secret — everything in it is
already in the row the client just received.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import status

from hunter_api.errors import HunterError
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_CURSOR_LENGTH = 128


class InvalidCursorError(HunterError):
    """A cursor that did not come from a previous page of this endpoint.

    422 rather than silently restarting from the top: a client that sends a
    corrupted cursor and gets page 1 back cannot tell that from real data, and
    would page forever.
    """

    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-cursor",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The pagination cursor is not valid.",
        )


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{ensure_utc(created_at).isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidCursorError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        timestamp, _, row_id = raw.partition("|")
        return ensure_utc(datetime.fromisoformat(timestamp)), uuid.UUID(row_id)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise InvalidCursorError from None


def clamp_page_size(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(limit, MAX_PAGE_SIZE))


class TenantRepository:
    """Base for every repository that reads or writes a tenant's rows.

    ``organization_id`` is a constructor argument, not a per-call one, so no
    query in a subclass can forget it — and the session it is given is always
    one whose transaction already set ``app.current_org`` to the same id, so
    Postgres refuses anything that slips through anyway.
    """

    def __init__(self, session: AsyncSession, org_id: uuid.UUID) -> None:
        self.session = session
        self.org_id = org_id
