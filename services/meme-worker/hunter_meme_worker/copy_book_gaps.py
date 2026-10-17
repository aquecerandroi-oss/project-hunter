"""The coverage half of the copy book (H-037, R2 fix B1/B2): what a hole in the source does to entries, to
copies alive across it, and what must be re-read from the chain before a leader may be copied again.
Split from ``copy_book.py`` for the 350-line budget; :class:`CopyBook` inherits it and owns the state.

* a ``health`` gap (`nats_*`, `chain_*`) only **flags** the copies alive across it (`contam`);
* a ``coverage`` gap flags them *and* censors their leader-driven exit until their position is re-read
  (:meth:`apply_trace`) — and blocks entries while it is open;
* a ``funnel`` gap blocks entries while open, nothing else;
* a closed ``coverage`` / ``funnel`` gap owes each leader a **recomposition** (:meth:`apply_window`): until
  the chain's history of the window has been read, that leader has no new entry. A window that cannot be
  read stays pending and is retried with backoff — never skipped.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_meme_worker.copy_events import (
    EXIT_LEADER_FULL,
    EXIT_LEADER_PEAK_DROP,
    LEADER_GAP_EXIT,
    VISTO_NA_LACUNA,
    CensorEntry,
    CloseIntent,
    Job,
    LeaderRef,
    OpenIntent,
    RecomposeDone,
    RejectEntry,
    window_ref,
)
from hunter_meme_worker.copy_gaps import GapRegistry, Recompositions, Window
from hunter_meme_worker.copy_position import Position

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_exchanges.pumpfun.leader_events import LeaderGap
    from hunter_meme_worker.copy_history import MintTrace, WindowTrace
    from hunter_meme_worker.copy_spec import CopySpec

__all__ = ["BookGaps"]

ONE = Decimal(1)


class BookGaps:
    _spec: CopySpec
    _stratum: dict[str, str]
    _by_key: dict[str, Position]
    _observed: set[tuple[str, str]]
    _unlanded: set[tuple[str, str]]
    _gaps: GapRegistry
    _recomp: Recompositions
    _window_seq: int

    def _close(
        self, pos: Position, reason: str, ref: LeaderRef | None, now: datetime, censor: str | None
    ) -> CloseIntent:
        raise NotImplementedError

    def owe_window(self, gap: LeaderGap, done: frozenset[str]) -> None:
        """Restart: a closed hole whose slices were not all recorded as recomposed is still owed."""
        self._gaps.add(gap)
        self._recomp.request(gap, done)

    def on_gap(self, gap: LeaderGap, now: datetime) -> None:
        kind = self._gaps.add(gap)
        if kind != "funnel":
            for pos in self._by_key.values():
                affected = gap.wallet is None or gap.wallet == pos.leader
                if not (affected and GapRegistry.overlaps_life(gap, pos.opened_by)):
                    continue
                if kind == "health":
                    pos.contam = pos.contam or gap.reason
                elif pos.gap_reason is None:
                    pos.gap_reason = LEADER_GAP_EXIT
        if kind != "health" and gap.end is not None:
            self._recomp.request(gap)

    @property
    def gaps(self) -> GapRegistry:
        return self._gaps

    # ---------------------------------------------------------------- recomposition
    def recompositions_pending(self) -> int:
        return self._recomp.pending()

    def is_blocked(self, wallet: str) -> bool:
        return self._recomp.blocked(wallet)

    def recompositions_due(self, now: datetime) -> list[Window]:
        return self._recomp.due(now)

    def window_failed(self, window: Window, now: datetime) -> None:
        self._recomp.failed(window, now)

    def apply_window(self, window: Window, trace: WindowTrace, now: datetime) -> list[Job]:
        """The chain's history of ``window``. Incomplete = still owed; complete = every mint the leader
        bought in the hole becomes an *observed* pair (so its next buy is not "the first") and a durable
        ``rejected/visto_na_lacuna`` row, and the leader is released."""
        if not trace.complete:
            self._recomp.failed(window, now)
            return []
        stratum = self._stratum.get(window.wallet, "")
        seen: list[RejectEntry] = []
        for mint in sorted(trace.bought_mints):
            pair = (window.wallet, mint)
            if pair in self._observed and pair not in self._unlanded:
                continue  # known AND durable; a pair known only in memory is emitted again
            self._observed.add(pair)
            self._unlanded.add(pair)  # until this window's transaction lands
            self._window_seq += 1
            ref = window_ref(window.wallet, stratum, window.start, window.end, self._window_seq)
            seen.append(RejectEntry(mint, ref, VISTO_NA_LACUNA, now))
        self._recomp.finish(window)
        done = RecomposeDone(
            window.wallet, window.gap_id, window.start, window.end, window.reason, tuple(seen)
        )
        return [done]

    def landed(self, job: Job) -> None:
        """A fact the funnel needed is durable: its (leader, mint) pair no longer depends on memory."""
        if isinstance(job, OpenIntent | RejectEntry | CensorEntry):
            self._unlanded.discard((job.leader.wallet, job.mint))
        elif isinstance(job, RecomposeDone):
            for seen in job.seen:
                self._unlanded.discard((seen.leader.wallet, seen.mint))

    def lift_censor(self, key: str, flag: str) -> None:
        """The leader's position was re-read: the exit is trustworthy again - priced, but flagged."""
        pos = self._by_key.get(key)
        if pos is not None:
            pos.gap_reason = None
            pos.contam = pos.contam or flag

    def apply_trace(
        self, key: str, trace: MintTrace | None, now: datetime, *, reason_flag: str
    ) -> list[Job]:
        """Re-read leader position of a copy alive across a hole or a restart. ``None`` = unreadable: the
        leader-driven exit stays censored by name. Readable: the copy is priced normally from here on,
        flagged ``contaminated``, and exits now if the leader's position already says so."""
        pos = self._by_key.get(key)
        if pos is None or pos.state != "open" or trace is None:
            return []
        pos.peak_atoms = max(pos.peak_atoms, trace.peak_atoms)
        pos.gap_reason = None
        pos.contam = pos.contam or reason_flag
        if trace.current_atoms == 0:
            reason = EXIT_LEADER_FULL
        elif Decimal(trace.current_atoms) <= Decimal(pos.peak_atoms) * (
            ONE - self._spec.exit_leader_drop_fraction
        ):
            reason = EXIT_LEADER_PEAK_DROP
        else:
            return []
        return [self._close(pos, reason, None, now, None)]
