"""Rebuilding the copy book from the database before the source opens (H-037, design §4.1): the funnel's
pairs, keys and attempts, the copies still open (their leader-driven exit is censored — the worker was
blind), the confirmations still owed, and the durable T0. Split from ``copy_book.py`` for the budget;
:class:`CopyBook` inherits it and owns the state these methods fill."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from hunter_meme_worker.copy_confirm import Confirmations, Pending, Seen
from hunter_meme_worker.copy_events import WORKER_RESTART_GAP
from hunter_meme_worker.copy_position import Position

if TYPE_CHECKING:
    from hunter_meme_worker.copy_spec import CopySpec

__all__ = ["BookRestore"]


class BookRestore:
    _spec: CopySpec
    _t0: datetime
    _end: datetime
    _observed: set[tuple[str, str]]
    _consumed: set[tuple[str, str]]
    _attempts: dict[tuple[str, date], int]
    _confirm: Confirmations

    def _add(self, pos: Position) -> None:
        raise NotImplementedError

    def restore_pair(self, leader: str, mint: str) -> None:
        self._observed.add((leader, mint))

    def restore_consumed(self, stratum: str, mint: str) -> None:
        self._consumed.add((stratum, mint))

    def restore_attempt(self, leader: str, day: date) -> None:
        self._attempts[(leader, day)] = self._attempts.get((leader, day), 0) + 1

    def recover_open(
        self,
        *,
        key: str,
        mint: str,
        leader: str,
        stratum: str,
        bet_id: str,
        entry_at: datetime,
        peak_atoms: int,
    ) -> None:
        """A copy still open in the database when the worker (re)started. The worker was blind for
        an unknown stretch, so its leader-driven exit is censored (``worker_restart_gap``)."""
        self._add(
            Position(
                key=key,
                leader=leader,
                stratum=stratum,
                mint=mint,
                opened_by=entry_at,
                decided_at=entry_at,
                peak_atoms=peak_atoms,
                state="open",
                entry_at=entry_at,
                bet_id=bet_id,
                gap_reason=WORKER_RESTART_GAP,
            )
        )
        self._observed.add((leader, mint))
        self._consumed.add((stratum, mint))

    def restore_pending(
        self,
        key: str,
        signature: str,
        wallet: str,
        mint: str,
        *,
        first_observed_at: datetime,
        position_after: int,
        token_delta: int,
        slot: int,
    ) -> None:
        """A copy opened on an unconfirmed signal that never got its confirmation before a restart:
        the timeout keeps its ORIGINAL deadline (a restart never extends it)."""
        pending = Pending(
            key, signature, "entry", first_observed_at + timedelta(seconds=self._spec.confirm_timeout_s),
            first_observed_at,
        )  # fmt: skip
        self._confirm.restore(
            pending,
            (signature, wallet, mint, "buy"),
            Seen(False, position_after, token_delta, slot),
        )

    @property
    def t0(self) -> datetime:
        return self._t0

    @property
    def horizon_end(self) -> datetime:
        return self._end

    def set_t0(self, t0: datetime) -> None:
        """The durable T0, once read (design §5): entries run from it for ``horizon_days``."""
        self._t0 = t0
        self._end = t0 + timedelta(days=self._spec.horizon_days)
