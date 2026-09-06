"""Shared plumbing for the T2.6 read models: the radar/opportunities keyset
cursor and the one JSONB path this module assumes about the feature envelope.

**Envelope path assumption (``.claude/state/notes-T2.6.md``).** T2.4/T2.5 (the
opportunity engine and scanner-worker that actually write
``opportunities.feature_snapshot``) are still in flight, so the exact shape of
the envelope is not frozen anywhere yet. What *is* frozen is
``hunter_indicators.features.vector.FeatureVector.as_wire()`` (T2.2, already
merged): ``{"values": {"<key>": {"value": "<decimal string>", ...}, ...},
...}``, with every number serialized as a canonical decimal string, never a
JSON number. This module assumes the envelope nests that vector under a
``"features"`` key — ``feature_snapshot["features"]["values"][key]["value"]``
— rather than flattening it (which would collide with the envelope's own
``as_of``/``baseline_ids``/``regime_id`` keys). ``atr_14_pct``
(``hunter_indicators.features.trend``, the Wilder-14 ATR fraction that also
feeds the EARLY/DEVELOPING/EXTENDED stage classifier) and
``relative_volume_1h`` (``hunter_indicators.features.volume``) are the two
concrete keys this API reads, for the radar's ``volatility`` filter and
``volume`` sort key respectively. If T2.5 lands a different envelope shape,
:func:`feature_value_expr`'s path is the one place to fix.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import sqlalchemy.exc as sa_exc
from fastapi import status
from sqlalchemy import Numeric, cast

from hunter_api.errors import HunterError
from hunter_core.db.models.analysis import Opportunity
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

logger = get_logger(__name__)

MAX_CURSOR_LENGTH = 96

LIKE_ESCAPE = "\\"
"""The ``ESCAPE`` character every ``ILIKE`` in this package is compiled with —
see :func:`like_contains`."""

FEATURE_KEY_VOLATILITY = "atr_14_pct"
FEATURE_KEY_VOLUME = "relative_volume_1h"

# NULLS LAST regardless of sort direction: a market missing a feature reads
# behind every market that has one, whichever way the list is ordered — never
# first, which a naive NULL-as-zero would produce for a "highest first" sort.
_SENTINEL_DESC = Decimal("-999999999")
_SENTINEL_ASC = Decimal("999999999")


class InvalidRadarCursorError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-cursor",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The pagination cursor is not valid.",
        )


def like_contains(value: str) -> str:
    """``value`` as a ``%contains%`` pattern with ``LIKE`` metacharacters escaped.

    Without this, ``?q=%`` matches every symbol in the universe and ``?q=_``
    matches every single-character one: the caller's search box silently turns
    into a wildcard scan of the whole table. Pair with
    ``.ilike(like_contains(q), escape=LIKE_ESCAPE)`` — the backslash has to be
    declared, since Postgres' default escape is also a backslash only by
    convention.
    """
    escaped = value.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


def encode_sort_cursor(value: Decimal, row_id: uuid.UUID) -> str:
    raw = f"{value}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_sort_cursor(cursor: str | None) -> tuple[Decimal, uuid.UUID] | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidRadarCursorError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        value_raw, _, id_raw = raw.partition("|")
        value = Decimal(value_raw)
        row_id = uuid.UUID(id_raw)
    except (ValueError, InvalidOperation, binascii.Error, UnicodeDecodeError):
        raise InvalidRadarCursorError from None
    # ``Decimal("NaN")``/``Decimal("Infinity")`` parse happily and then reach
    # Postgres, where every keyset comparison against them is either an error
    # or (for NaN) silently false — a 500 or an empty page for what is really
    # a malformed cursor.
    if not value.is_finite():
        raise InvalidRadarCursorError
    return value, row_id


def feature_value_expr(key: str) -> ColumnElement[Decimal | None]:
    """``opportunities.feature_snapshot``'s reading of feature ``key``, as a
    nullable ``Numeric`` SQL expression — see the module docstring for the
    assumed path and its two concrete keys.
    """
    raw = Opportunity.feature_snapshot["features"]["values"][key]["value"].astext
    return cast(raw, Numeric)


def sentinel_for(order: str) -> Decimal:
    """The value a ``NULL`` sort key is coalesced to, so it always sorts last."""
    return _SENTINEL_DESC if order == "desc" else _SENTINEL_ASC


class AnalysisDataUnavailableError(HunterError):
    """Postgres unreachable/interrupted while serving radar/opportunities/
    anomalies/regime — the brief's "Postgres fora = 503" (brief-T2.6:13),
    shared by all four routers so the wording/slug stay one thing.

    ``detail`` never repeats the driver's own message: an ``OperationalError``
    from asyncpg can embed the DSN or a hostname.
    """

    def __init__(self) -> None:
        super().__init__(
            type_slug="analysis-data-unavailable",
            title="Service Unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market analysis data is temporarily unavailable.",
        )


@contextlib.asynccontextmanager
async def postgres_failures_as_503() -> AsyncGenerator[None]:
    """Turn a real connection-level Postgres failure into a 503, for the one
    query (or handful of queries) a route makes after its session dependency
    already opened successfully.

    Deliberately narrow: :class:`sqlalchemy.exc.OperationalError` and
    :class:`~sqlalchemy.exc.InterfaceError` are driver/connection failures
    (server gone, timeout, broken pipe), :class:`sqlalchemy.exc.TimeoutError`
    is pool exhaustion (``QueuePool limit of size N overflow M reached``) and a
    bare ``OSError`` is a socket that never became a connection at all
    (``ConnectionRefusedError``, DNS failure) — asyncpg raises those before
    SQLAlchemy has a DBAPI error to wrap them in, which is why
    ``auth/principal.py`` already catches ``OSError`` alongside
    ``OperationalError`` for the same reason. Never
    :class:`sqlalchemy.exc.IntegrityError` or other statement-level errors,
    which are real bugs and must still surface as `500`s, not be mistaken for
    "the database is down".

    ``OSError`` is broad, but the block it guards is a database transaction and
    the in-memory assembly around it: there is no file or network I/O inside it
    other than Postgres.

    ``TimeoutError`` is a plain ``SQLAlchemyError``, not a ``DBAPIError``, so
    it used to fall straight past this translator into the generic 500. It
    says the process ran out of *capacity*, which is what 503 (plus a warning
    log naming it) means — even when the underlying cause is a handler holding
    a connection too long. The invariant that keeps that from being routine is
    in ``routers/radar_common.py``: one connection per request, never two.

    The four T2.6 routers open their session **inside** this context manager
    (``routers/radar_common.py::analysis_scope``) rather than through a
    ``Depends`` that resolves before the body runs, so a Postgres outage that
    fails on the transaction's very first round trip (``SET LOCAL ROLE``) is
    translated here too.
    """
    try:
        yield
    except (
        sa_exc.OperationalError,
        sa_exc.InterfaceError,
        sa_exc.TimeoutError,
        OSError,
    ) as exc:
        logger.warning("analysis_data_postgres_error", error_type=type(exc).__name__)
        raise AnalysisDataUnavailableError from exc
