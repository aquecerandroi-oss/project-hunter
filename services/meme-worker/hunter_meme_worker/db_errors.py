"""What a failed read logs, so the log says *why* it failed.

SQLAlchemy's asyncpg adapter folds every ``asyncpg.PostgresError`` that has no
closer mapping, ``QueryCanceledError`` (a statement timeout) included, into
its generic ``Error``. ``type(exc.orig).__name__`` then reads ``"Error"`` for
a timeout, a lock wait and a deadlock alike. The SQLSTATE the adapter copies
onto that wrapper (``57014``, ``55P03``, ``40P01`` …) and its message, which
names the asyncpg class, tell them apart (the 24/09/2026
``meme_pedigree_read_failed`` incident).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.exc import DBAPIError

__all__ = ["DETAIL_MAX_CHARS", "db_error_fields"]

DETAIL_MAX_CHARS = 300


def db_error_fields(exc: DBAPIError) -> dict[str, str | None]:
    """``error`` (unchanged, the wrapper's class name), ``sqlstate`` (``None``
    when the driver gave none) and ``detail`` (the message, truncated)."""
    orig = exc.orig
    return {
        "error": type(orig).__name__,
        "sqlstate": getattr(orig, "sqlstate", None),
        "detail": str(orig)[:DETAIL_MAX_CHARS],
    }
