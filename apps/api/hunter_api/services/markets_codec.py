"""Defensive decoding of raw Redis hot-state values for markets.

Split out of ``services/markets.py`` (post-review fix pass on T1.4, fix F1)
to keep that module under CLAUDE.md's 350-line file budget once the
defensive-decoding fixes were added -- the Redis field contract itself is
still documented verbatim in ``schemas/markets.py``'s module docstring, this
module just implements the "never raise on a corrupted value" rule.

**Every function here treats a corrupted or hostile input as absent data,
never as an exception.** A single malformed trade or book level is dropped
individually; a value that fails to decode as a msgpack map at all comes
back ``None``. The caller (``services/markets.py``) is what turns "absent"
into the honest ``degraded``/``unavailable`` aggregate -- this module's job
stops at "decoded, or safely nothing".
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import msgpack
from pydantic import ValidationError

from hunter_api.schemas.markets import BookLevelOut, FundingKind, OrderBookOut, TradeOut
from hunter_core.domain.types import ensure_utc

_UNPACK_MAX_BUFFER_SIZE = 64 * 1024
"""Hot-state values are tiny (top-20 book levels, one trade) -- 64 KiB is
generous headroom over anything legitimate. A corrupted or hostile blob
larger than this is rejected by ``Unpacker.feed`` before this process spends
memory inflating it (F1)."""

_FUNDING_KINDS: frozenset[str] = frozenset({"estimated", "realized"})


def decode_hash(raw: dict[bytes, bytes]) -> dict[str, str]:
    """(G7) ``errors="replace"`` on both key and value: a corrupted or
    hostile hash field must decode to *something* (U+FFFD in place of the bad
    bytes) rather than raise ``UnicodeDecodeError`` past this boundary. The
    replaced string then simply fails whatever parser reads it next
    (``to_decimal``/``to_timestamp`` return ``None`` for garbage) -- the same
    "absent, never an exception" rule this whole module already applies to
    every other kind of corruption.
    """
    return {
        key.decode(errors="replace"): value.decode(errors="replace") for key, value in raw.items()
    }


def to_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def to_funding_kind(value: str | None) -> FundingKind | None:
    """(G10) ``mkt:*:deriv``'s ``funding_kind`` is a plain Redis hash string
    written by a trusted worker but not schema-enforced at the transport --
    an unrecognized value (a worker bug, or some future third kind this API
    does not document yet) is dropped to ``None`` rather than passed through
    typed as ``FundingKind`` when it demonstrably isn't one of its two
    values. ``None`` here is the same "unknown" the field already reads as
    when it was never written at all -- an honest choice, not a silent
    pass-through.
    """
    if value in _FUNDING_KINDS:
        return cast("FundingKind", value)
    return None


def to_timestamp(value: object | None) -> datetime | None:
    """(G7) ``value`` is typed loosely because it can come straight off a
    decoded msgpack map (``dict[str, Any]``) -- a payload carrying ``ts`` as
    an int (or any other non-``str``) must read absent, not raise
    ``TypeError`` out of ``datetime.fromisoformat`` (which only ever declares
    ``ValueError`` for a malformed *string*, not a wrong-typed argument).
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def unpack(raw: bytes) -> dict[str, Any] | None:
    """Defensive decode (F1): a corrupted or hostile Redis value must never
    raise past this boundary -- only the component/market it belongs to
    degrades, never the whole request. Returns ``None`` for anything that
    does not decode to a msgpack *map* -- a JSON string, a bare list, a
    truncated payload, or a blob larger than ``_UNPACK_MAX_BUFFER_SIZE`` --
    rather than letting any of those raise into the caller.
    """
    try:
        # msgpack ships no inline type stubs, so `Unpacker`, `.feed` and
        # `.unpack` all come back `Unknown` to pyright's strict mode --
        # suppressed rather than worked around.
        unpacker = msgpack.Unpacker(  # type: ignore[reportUnknownVariableType, reportUnknownMemberType]
            max_buffer_size=_UNPACK_MAX_BUFFER_SIZE, raw=False
        )
        unpacker.feed(raw)  # type: ignore[reportUnknownMemberType]
        value = unpacker.unpack()  # type: ignore[reportUnknownMemberType]
    except (msgpack.exceptions.UnpackException, ValueError):
        # (G7) narrowed from a bare `except Exception`: `UnpackException`
        # covers msgpack's own malformed/incomplete/oversized-buffer errors
        # (`OutOfData`, `FormatError`, `StackError`, `BufferFull`);
        # `ValueError` additionally covers `ExtraData`/`UnpackValueError`
        # (both subclass it) and, since this unpacker runs with `raw=False`,
        # a `UnicodeDecodeError` raised while msgpack decodes an embedded
        # string field that is not valid UTF-8 (`UnicodeDecodeError`
        # subclasses `ValueError`). Every one of those means "not
        # decodable" -- absent data, never a 500. Anything else (a
        # programming error) is left to propagate rather than silently
        # becoming absent data too.
        return None
    if not isinstance(value, dict):
        return None
    return cast("dict[str, Any]", value)


def book_ts(raw: bytes | None) -> datetime | None:
    """The book snapshot's own ``ts``, without decoding its levels."""
    if raw is None:
        return None
    decoded = unpack(raw)
    if decoded is None:
        return None
    return to_timestamp(decoded.get("ts"))


def _parse_book_levels(raw_levels: Any) -> list[BookLevelOut]:
    """One side (``bids``/``asks``) of a decoded book payload. A malformed
    individual level (wrong shape, non-numeric price/qty) is skipped, not
    fatal to the rest of the book (F1) -- the same rule ``parse_trades``
    already applies to a single bad trade.
    """
    levels: list[BookLevelOut] = []
    if not isinstance(raw_levels, list):
        return levels
    for level in cast("list[Any]", raw_levels):
        # (G1) a level is only ever a 2-element sequence of [price, qty] --
        # indexing anything else (a bare string, a 1- or 3-element list, a
        # dict) would either raise or, worse, silently succeed with
        # *fabricated* numbers: indexing a string like "12" at [0]/[1] reads
        # back price=1, qty=2 -- digits that were never in the data. Reject
        # the shape before ever touching `level[0]`/`level[1]`.
        if isinstance(level, str | bytes) or not isinstance(level, list | tuple):
            continue
        # Reset to `Any` after the shape check: pyright narrows the
        # `isinstance(level, list | tuple)` above to `list[Unknown] |
        # tuple[Unknown, ...]`, and indexing that below would report every
        # value as partially unknown even though it is deliberately `Any`
        # here (msgpack-decoded content, validated at the `BookLevelOut`
        # boundary, not before).
        level = cast("list[Any]", level)
        if len(level) != 2:
            continue
        try:
            levels.append(BookLevelOut(price=level[0], qty=level[1]))
        except (TypeError, ValidationError):
            continue
    return levels


def parse_book(raw: bytes | None) -> OrderBookOut | None:
    if raw is None:
        return None
    decoded = unpack(raw)
    if decoded is None:
        # (F1) not a msgpack map at all -- absent, same as the key never
        # having been written, never a 500 for the rest of the response.
        return None
    return OrderBookOut(
        ts=to_timestamp(decoded.get("ts")),
        bids=_parse_book_levels(decoded.get("bids")),
        asks=_parse_book_levels(decoded.get("asks")),
    )


def parse_trades(raw_items: list[bytes]) -> list[TradeOut]:
    """``raw_items`` come from ``LRANGE 0 49`` — the worker ``LPUSH``es each
    new trade (index 0 = newest), so this list is already newest-first and
    needs no reversal. An entry whose ``ts`` cannot be parsed is dropped
    rather than stamped with the read time — a trade time this API cannot
    read is not the same fact as a trade that happened right now. (F1) An
    entry that fails to decode at all, or that decodes but is missing a
    required field (``price``/``qty``/``side``/``trade_id``) or carries an
    invalid value for one, is likewise dropped individually rather than
    raising and losing every other trade in the response.
    """
    trades: list[TradeOut] = []
    for raw in raw_items:
        item = unpack(raw)
        if item is None:
            continue
        ts = to_timestamp(item.get("ts"))
        if ts is None:
            continue
        try:
            trades.append(
                TradeOut(
                    ts=ts,
                    price=item["price"],
                    qty=item["qty"],
                    side=item["side"],
                    trade_id=item["trade_id"],
                )
            )
        except (KeyError, ValidationError):
            continue
    return trades
