"""Shapes shared by every schema module."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Request bodies reject unknown fields.

    A field the API does not know is a field the client thinks it is setting.
    Silently ignoring ``{"plan": "ENTERPRISE"}`` on an organization update is
    how a client ships a feature that never worked and nobody notices — and,
    less charitably, how a probe learns which fields are ignored rather than
    refused. ``extra="forbid"`` turns both into a 422 naming the field.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CursorPage[ItemT](BaseModel):
    """One page of a cursor-paginated list.

    ``next_cursor`` is ``None`` exactly when there is no further page; clients
    loop until it is, and never construct a cursor themselves.
    """

    items: list[ItemT]
    next_cursor: str | None = None
