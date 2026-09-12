"""The in-memory state of one board of ``/ws/trenches``.

The protocol, as measured live on 2026-09-12 (``tests/fixtures/pumpfun/
trenches_*.json``): after ``subscribe`` the server sends one ``snapshot``
(``{type, board, version, serverTs, entries[]}``, ``entries`` in board order) and
then a ``delta`` per change (``{type, board, baseVersion, version, serverTs,
patches[]}``). A patch is ``{op, mint, fields?, idx?}``: ``update`` merges
``fields`` into a known entry, ``add`` inserts a full entry at ``idx``,
``remove`` drops the mint, ``move`` repositions it at ``idx`` (documented by the
site bundle; not seen in the captures, supported the same way).

Sequence rule, and it is a measured one. ``version`` is a **per-board**
counter (``new`` ran 3148610→3148635, ``movers`` 0→25 in the same minute) and
on the ``graduating`` board the deltas received skip versions (snapshot
3137948, then ``baseVersion`` 3137954, 3137976, …): the counter also moves on
changes outside the top-N the subscription shows, and those are simply not
sent. So a delta applies when ``baseVersion >= held`` (a forward gap is
counted in ``BoardEvent.version_gap``) and is refused — :class:`OutOfOrderDelta`,
state untouched, the client resubscribes for a fresh snapshot — when it goes
**backwards** (stale or duplicate), does not advance, or patches a mint the
mirror does not hold (an ``add`` we were never sent: the mirror drifted).
Demanding contiguity would have resynced ``graduating`` eight times in the 30 s
capture and never shown a coin.

Short wire keys are read in ``trenches_entry.py`` and nowhere else: what leaves
is :class:`NormalizedBoardEntry` with long names and ``Decimal`` numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from hunter_exchanges.base import ExchangeError
from hunter_exchanges.pumpfun.board_models import NormalizedBoardEntry
from hunter_exchanges.pumpfun.trenches_entry import EXCHANGE, malformed, parse_entry


class OutOfOrderDelta(ExchangeError):
    """A delta the mirror cannot follow: resubscribe for a snapshot."""

    def __init__(
        self, board: str, *, expected: int, base_version: int, reason: str = "stale_version"
    ) -> None:
        super().__init__(
            f"trenches board {board!r} delta baseVersion {base_version} vs held {expected}: {reason}",
            exchange=EXCHANGE,
            retryable=True,
        )
        self.expected = expected
        self.base_version = base_version
        self.reason = reason


@dataclass(frozen=True, slots=True)
class BoardEvent:
    """What one message did to the board. ``entries`` are the rows the message
    touched (all of them for a snapshot); ``positions`` is every mint on the
    board afterwards, because an ``add`` at index 0 moves every other row."""

    kind: str
    board: str
    version: int
    observed_at: datetime
    received_at: datetime
    entries: tuple[NormalizedBoardEntry, ...]
    removed: tuple[str, ...]
    positions: dict[str, int]
    patch_ops: dict[str, int] = field(default_factory=dict[str, int])
    version_gap: int = 0
    """``baseVersion − held`` when the delta skipped versions we were not sent."""


def _server_ts(payload: dict[str, Any]) -> datetime:
    ts = payload.get("serverTs")
    if not isinstance(ts, int) or isinstance(ts, bool) or ts <= 0:
        raise malformed("message has no serverTs")
    return datetime.fromtimestamp(ts / 1000, tz=UTC)


def _version(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise malformed(f"message has no {key}")
    return value


def _fields(patch: dict[str, Any]) -> dict[str, Any]:
    fields = patch.get("fields")
    if not isinstance(fields, dict):
        raise malformed("patch has no fields object")
    return dict(cast(dict[str, Any], fields))


def _index(patch: dict[str, Any], upper: int) -> int:
    idx = patch.get("idx", upper)
    if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
        raise malformed("patch idx is not a non-negative integer")
    return min(idx, upper)


@dataclass
class BoardState:
    """The mirror of one board: raw entries by mint, the order, the version."""

    board: str
    version: int | None = None
    entries: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    order: list[str] = field(default_factory=list[str])

    @property
    def synced(self) -> bool:
        return self.version is not None

    def positions(self) -> dict[str, int]:
        return {mint: index for index, mint in enumerate(self.order)}

    def apply(self, payload: dict[str, Any], *, received_at: datetime) -> BoardEvent:
        """Apply a decoded message. Raises :class:`MalformedMessage` for a shape
        the protocol does not have and :class:`OutOfOrderDelta` for a delta this
        state cannot follow — in both cases the state is left as it was."""
        kind = payload.get("type")
        if payload.get("board") != self.board:
            raise malformed(f"message for board {payload.get('board')!r}, held {self.board!r}")
        if kind == "snapshot":
            return self._apply_snapshot(payload, received_at)
        if kind == "delta":
            return self._apply_delta(payload, received_at)
        raise malformed(f"unknown message type {kind!r}")

    def _apply_snapshot(self, payload: dict[str, Any], received_at: datetime) -> BoardEvent:
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise malformed("snapshot has no entries list")
        version = _version(payload, "version")
        observed_at = _server_ts(payload)
        entries: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        parsed: list[NormalizedBoardEntry] = []
        for index, raw in enumerate(cast(list[Any], raw_entries)):
            if not isinstance(raw, dict):
                raise malformed("snapshot entry is not an object")
            raw = cast(dict[str, Any], raw)
            entry = parse_entry(
                raw,
                board=self.board,
                position=index,
                version=version,
                observed_at=observed_at,
                received_at=received_at,
            )
            entries[entry.mint] = dict(raw)
            order.append(entry.mint)
            parsed.append(entry)
        removed = tuple(sorted(set(self.order) - set(order)))
        self.entries, self.order, self.version = entries, order, version
        return BoardEvent(
            kind="snapshot",
            board=self.board,
            version=version,
            observed_at=observed_at,
            received_at=received_at,
            entries=tuple(parsed),
            removed=removed,
            positions=self.positions(),
        )

    def _apply_delta(self, payload: dict[str, Any], received_at: datetime) -> BoardEvent:
        base = _version(payload, "baseVersion")
        version = _version(payload, "version")
        patches = payload.get("patches")
        if not isinstance(patches, list):
            raise malformed("delta has no patches list")
        observed_at = _server_ts(payload)
        if self.version is None:
            raise OutOfOrderDelta(self.board, expected=-1, base_version=base, reason="no_snapshot")
        if base < self.version or version <= self.version:
            raise OutOfOrderDelta(self.board, expected=self.version, base_version=base)
        gap = base - self.version
        # Work on copies so a malformed patch in the middle leaves the state whole.
        entries = {mint: dict(fields) for mint, fields in self.entries.items()}
        order = list(self.order)
        touched: list[str] = []
        removed: list[str] = []
        ops: dict[str, int] = {}
        for raw_patch in cast(list[Any], patches):
            if not isinstance(raw_patch, dict):
                raise malformed("patch is not an object")
            patch = cast(dict[str, Any], raw_patch)
            op, mint = patch.get("op"), patch.get("mint")
            if not isinstance(op, str) or not isinstance(mint, str) or not mint:
                raise malformed("patch has no op or mint")
            ops[op] = ops.get(op, 0) + 1
            if op == "update":
                if mint not in entries:
                    raise OutOfOrderDelta(
                        self.board, expected=self.version, base_version=base, reason="unknown_mint"
                    )
                entries[mint].update(_fields(patch))
                touched.append(mint)
            elif op == "add":
                fields = _fields(patch)
                if fields.get("m", mint) != mint:
                    raise malformed("add patch fields name another mint")
                fields["m"] = mint
                entries[mint] = fields
                if mint in order:
                    order.remove(mint)
                order.insert(_index(patch, len(order)), mint)
                touched.append(mint)
            elif op == "remove":
                entries.pop(mint, None)
                if mint in order:
                    order.remove(mint)
                removed.append(mint)
            elif op == "move":
                if mint not in entries:
                    raise OutOfOrderDelta(
                        self.board, expected=self.version, base_version=base, reason="unknown_mint"
                    )
                order.remove(mint)
                order.insert(_index(patch, len(order)), mint)
                touched.append(mint)
            else:
                raise malformed(f"unknown patch op {op!r}")
        self.entries, self.order, self.version = entries, order, version
        positions = self.positions()
        parsed = tuple(
            parse_entry(
                entries[mint],
                board=self.board,
                position=positions[mint],
                version=version,
                observed_at=observed_at,
                received_at=received_at,
            )
            for mint in dict.fromkeys(touched)
            if mint in entries
        )
        return BoardEvent(
            kind="delta",
            board=self.board,
            version=version,
            observed_at=observed_at,
            received_at=received_at,
            entries=parsed,
            removed=tuple(dict.fromkeys(removed)),
            positions=positions,
            patch_ops=ops,
            version_gap=gap,
        )


__all__ = ["BoardEvent", "BoardState", "OutOfOrderDelta", "parse_entry"]
