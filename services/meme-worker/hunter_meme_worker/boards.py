"""The board collector: four ``/ws/trenches`` streams become one row per mint per
board per closed minute, an exposure interval per listing, and the tracker's
priority hints. Pure except for the runner at the bottom.

**Exposure** (A4.0g, ``docs/plans/T4-CANTOS.md`` §2): a listing starts at the
``serverTs`` of the first message that showed the mint and ends either at the
``remove`` patch that took it off (``left_board_at``) or — when the mint is
absent from the snapshot a reconnect/resync brought — as **censored**: the
socket was down, and a disappearance nobody watched is not an exit. A mint
that vanishes between two snapshots of one live session (``movers`` re-sends
snapshots) left the board, and the row says so.

**The minute** is bucketed by *our* ``received_at`` (``minute_end`` = the
closed minute a message fell in), the same clock the features fold uses for
non-anticipation; ``observed_at`` of a row is the board's last ``serverTs`` in
that minute — the board still listed the mint then — and ``mint_updated_at``
the ``serverTs`` of the last patch that touched the mint itself. A board that
sent nothing in a minute produces no rows for it: not observed is not "still
there".

**What feeds the tracker**: an entry with ``program == "pump"`` and
``quote_asset == "SOL"`` on ``new``/``graduating`` becomes a tracked mint (with
the site's own ``age`` turned into ``created_at`` and ``dev_wallet`` as
``creator``, both labelled ``trenches_ws`` on the token row) — the discovery the
adendo asked for: ``graduating`` mints get polled before the rest.

**What feeds the completion signals** (T4.2d, ``graduation.py``): a ``gd`` on
any tracked board is ``pool_created_at`` with the entry's own source; the
first presence of a pump/SOL mint on the ``graduated`` board is
``graduated_board_seen_at`` (the board's ``serverTs``) — written for every
such entry, tracked or not, because the matrix wants the cohort the boards
see, and **never** added to the poll budget: a graduated curve is static.
:meth:`BoardCollector.ingest` returns every first sighting so ``wiring.run_board``
can count what the discovery socket cannot see (the ``new`` board's
non-``pump`` programs — the declared blindness of item 3).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_meme_worker.features_tape import HoldersObservation
from hunter_meme_worker.graduation import CompletionSignals, earliest_completion
from hunter_meme_worker.repo import TokenRow
from hunter_meme_worker.repo_boards import BoardMinuteRow, board_minute_row
from hunter_meme_worker.tracker import TrackedMint

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.board_models import NormalizedBoardEntry
    from hunter_exchanges.pumpfun.trenches_state import BoardEvent
    from hunter_meme_worker.tracker import MintTracker

TRACKED_BOARDS = frozenset({"new", "graduating"})
GRADUATED_BOARD = "graduated"
HOLDERS_HISTORY = 8
"""Readings kept per mint so the fold can pick the newest one *received by* the
minute's close even when a newer one arrived in the seconds before the fold."""


def minute_end_of(received_at: datetime) -> datetime:
    """The closed minute a message belongs to: ``12:00:30`` → ``12:01:00``."""
    return received_at.replace(second=0, microsecond=0) + timedelta(minutes=1)


def _created_at(entry: NormalizedBoardEntry) -> datetime | None:
    """``serverTs − age``: the site's own counter, declared as such on the row."""
    return entry.observed_at - timedelta(seconds=entry.age_s) if entry.age_s is not None else None


@dataclass
class Presence:
    """One mint on one board, from first sighting to exit."""

    entry: NormalizedBoardEntry
    first_seen_at: datetime
    last_seen_at: datetime
    position: int
    bucket: datetime
    patches: int = 0
    left_at: datetime | None = None
    censored: bool = False


@dataclass
class BoardMirror:
    """What the collector knows about one board's stream."""

    board: str
    presences: dict[str, Presence] = field(default_factory=dict[str, Presence])
    bucket: datetime | None = None
    bucket_observed_at: datetime | None = None
    bucket_received_at: datetime | None = None
    session_key: int | None = None
    version: int | None = None


class BoardCollector:
    """Applies :class:`BoardEvent` s; hands closed-minute rows to the fold."""

    def __init__(self, tracker: MintTracker, *, boards: tuple[str, ...]) -> None:
        self._tracker = tracker
        self.mirrors: dict[str, BoardMirror] = {board: BoardMirror(board) for board in boards}
        self._closed: list[BoardMinuteRow] = []
        self._readings: dict[str, deque[HoldersObservation]] = {}
        self.pending_tokens: dict[str, TokenRow] = {}
        self.events: int = 0

    # ----------------------------------------------------------------- reads
    def readings(self, mint: str) -> list[HoldersObservation]:
        return list(self._readings.get(mint, ()))

    def listed_on(self, board: str) -> frozenset[str]:
        return frozenset(
            mint for mint, p in self.mirrors[board].presences.items() if p.left_at is None
        )

    def take_rows(self) -> list[BoardMinuteRow]:
        rows, self._closed = self._closed, []
        return rows

    # ---------------------------------------------------------------- events
    def ingest(self, event: BoardEvent, *, session_key: int) -> tuple[NormalizedBoardEntry, ...]:
        """Apply one board message; returns the entries seen on this board for
        the first time (a listing). ``session_key`` changes on every reconnect
        or resync of the socket, which is how a missing mint is told apart from
        a removed one."""
        mirror = self.mirrors[event.board]
        bucket = minute_end_of(event.received_at)
        self._roll_bucket(mirror, bucket)
        reconnected = mirror.session_key is not None and mirror.session_key != session_key
        mirror.session_key = session_key
        mirror.version = event.version
        mirror.bucket_observed_at = event.observed_at
        mirror.bucket_received_at = event.received_at
        self.events += 1
        if event.kind == "snapshot":
            for mint in set(mirror.presences) - set(event.positions):
                self._exit(mirror, mint, at=event.observed_at, censored=reconnected)
        for mint in event.removed:
            self._exit(mirror, mint, at=event.observed_at, censored=False)
        listed: list[NormalizedBoardEntry] = []
        for entry in event.entries:
            presence = mirror.presences.get(entry.mint)
            first_sighting = presence is None or presence.left_at is not None
            if first_sighting:
                presence = Presence(
                    entry=entry,
                    first_seen_at=entry.observed_at,
                    last_seen_at=entry.observed_at,
                    position=entry.position,
                    bucket=bucket,
                )
                mirror.presences[entry.mint] = presence
                listed.append(entry)
            assert presence is not None
            presence.entry = entry
            presence.position = entry.position
            presence.patches += 1 if event.kind == "delta" else 0
            self._remember_reading(entry)
            self._learn(entry, listed=first_sighting)
        for mint, position in event.positions.items():
            presence = mirror.presences.get(mint)
            if presence is not None and presence.left_at is None:
                presence.position = position
                presence.last_seen_at = event.observed_at
                presence.bucket = bucket
        return tuple(listed)

    def _roll_bucket(self, mirror: BoardMirror, bucket: datetime) -> None:
        """The first message of a new minute closes the previous one."""
        if mirror.bucket is not None and bucket > mirror.bucket:
            self._emit_minute(mirror, mirror.bucket)
        mirror.bucket = bucket

    def _exit(self, mirror: BoardMirror, mint: str, *, at: datetime, censored: bool) -> None:
        presence = mirror.presences.get(mint)
        if presence is None or presence.left_at is not None:
            return
        presence.left_at = None if censored else at
        presence.censored = censored
        presence.last_seen_at = (
            max(presence.last_seen_at, at) if not censored else presence.last_seen_at
        )
        self._closed.append(self._row(mirror, presence, observed_at=at, received_at=utcnow()))
        del mirror.presences[mint]

    def _row(
        self,
        mirror: BoardMirror,
        presence: Presence,
        *,
        observed_at: datetime,
        received_at: datetime,
    ) -> BoardMinuteRow:
        return board_minute_row(
            presence.entry,
            minute_end=presence.bucket,
            observed_at=observed_at,
            received_at=received_at,
            patches=presence.patches,
            position=presence.position,
            first_seen_in_board_at=presence.first_seen_at,
            last_seen_in_board_at=presence.last_seen_at,
            left_board_at=presence.left_at,
            exposure_censored=presence.censored,
        )

    def _emit_minute(self, mirror: BoardMirror, bucket: datetime) -> None:
        observed_at, received_at = mirror.bucket_observed_at, mirror.bucket_received_at
        if observed_at is None or received_at is None:
            return
        for presence in mirror.presences.values():
            if presence.left_at is not None:
                continue
            row = self._row(mirror, presence, observed_at=observed_at, received_at=received_at)
            self._closed.append(row)
            presence.patches = 0
            presence.bucket = bucket + timedelta(minutes=1)

    def close_minute(self, boundary: datetime) -> list[BoardMinuteRow]:
        """Called by the fold at ``boundary``: every board whose open bucket is
        the closed minute emits its rows now, whether or not a later message
        has arrived to roll it."""
        for mirror in self.mirrors.values():
            if mirror.bucket is not None and mirror.bucket <= boundary:
                self._emit_minute(mirror, mirror.bucket)
                mirror.bucket = None
        return self.take_rows()

    # -------------------------------------------------------------- readings
    def _remember_reading(self, entry: NormalizedBoardEntry) -> None:
        if entry.holders is None and entry.top10_share is None and entry.snipers is None:
            return
        history = self._readings.setdefault(entry.mint, deque(maxlen=HOLDERS_HISTORY))
        history.append(
            HoldersObservation(
                observed_at=entry.observed_at,
                received_at=entry.received_at,
                source=entry.source,
                holders=entry.holders,
                top10_share=entry.top10_share,
                dev_share=entry.dev_share,
                snipers=entry.snipers,
            )
        )

    def _learn(self, entry: NormalizedBoardEntry, *, listed: bool) -> None:
        """A pump/SOL entry teaches the tracker (``new``/``graduating``) or the
        dimension alone (``graduated``); any other program teaches nothing."""
        if not entry.is_pump_curve_on_sol:
            return
        if entry.board == GRADUATED_BOARD:
            if listed and entry.mint not in self.pending_tokens:
                self.pending_tokens[entry.mint] = self._token_row(entry, on_graduated_board=True)
            return
        if entry.board not in TRACKED_BOARDS:
            return
        known = self._tracker.get(entry.mint)
        self._tracker.observe(
            TrackedMint(
                mint=entry.mint,
                first_seen_at=entry.received_at,
                created_at=_created_at(entry),
                creator=entry.dev_wallet,
                board=entry.board,
                complete=entry.graduated_at is not None,
                final_read_pending=entry.graduated_at is not None
                and (known is None or not known.finished),
            )
        )
        if known is None and entry.mint not in self.pending_tokens:
            self.pending_tokens[entry.mint] = self._token_row(entry, on_graduated_board=False)

    @staticmethod
    def _token_row(entry: NormalizedBoardEntry, *, on_graduated_board: bool) -> TokenRow:
        """The identity the board states, plus the completion signals it carries:
        ``gd`` is the pool (with the entry's own source), presence on the
        ``graduated`` board is the board signal (the board's ``serverTs``)."""
        signals = CompletionSignals(
            graduated_board_seen_at=entry.observed_at if on_graduated_board else None,
            pool_created_at=entry.graduated_at,
            pool_created_source=entry.source if entry.graduated_at is not None else None,
        )
        return TokenRow(
            mint=entry.mint,
            first_seen_source=entry.source,
            first_seen_at=entry.received_at,
            last_seen_at=entry.received_at,
            name=entry.name,
            symbol=entry.symbol,
            creator=entry.dev_wallet,
            created_at=_created_at(entry),
            pool="pump",
            graduated_board_seen_at=signals.graduated_board_seen_at,
            pool_created_at=signals.pool_created_at,
            pool_created_source=signals.pool_created_source,
            completed_at=earliest_completion(signals),
        )

    def take_tokens(self) -> list[TokenRow]:
        rows, self.pending_tokens = list(self.pending_tokens.values()), {}
        return rows
