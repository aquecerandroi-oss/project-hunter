"""The copy lane's decision, in memory (H-037). **Synchronous on purpose**: the buy/follow path must
be milliseconds (Everton, 2026-10-09), so a leader event is decided against dictionaries — the
frozen leader set, the keys consumed, the day's attempts, the copies held, the gaps, the facts seen —
with no await, no database, no HTTP and no blocking call. Pricing and persistence are the executor's
(``copy_exec.py``); this module says *what* to do and *when we decided it*.

Rules (``docs/design/copiar-carteiras-papel.md`` §3.2/§3.4, pre-registered in EXP-M28):

* **entry** = the first observation of a (leader, mint) pair, if it is a first purchase (position
  before = 0) of at least ``min_trigger_sol``, on the curve, with the (stratum, mint) key free, under
  ``max_attempts_per_leader_day``, not inside an effective-loss hole and not owed a recomposition; an
  admitted attempt **consumes the key** even if it ends unfilled. Every first observation not admitted
  is a durable ``rejected`` funnel row;
* **exit** = the leader's ``position_after`` at 0 or at ``exit_leader_drop_fraction`` of its peak; our
  own exits (stop, time cap) come from the sweep and the mark pass;
* **holes**: see ``copy_book_gaps.py`` (source-health gaps flag, coverage gaps censor and block);
* **confirmation**: see ``copy_book_confirm.py`` (act on the first trustworthy signal, the chain's
  verdict arrives later).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.types import uuid7
from hunter_meme_worker.copy_book_confirm import BookConfirm
from hunter_meme_worker.copy_book_gaps import BookGaps
from hunter_meme_worker.copy_confirm import Confirmations
from hunter_meme_worker.copy_events import (
    ABAIXO_DO_PISO,
    AFTER_HORIZON,
    ALREADY_OBSERVED,
    BEFORE_T0,
    CO_COMPRA,
    EVIDENCIA_INSUFICIENTE,
    EXIT_LEADER_FULL,
    EXIT_LEADER_PEAK_DROP,
    EXIT_LEADER_TRANSFER,
    EXIT_NOT_TRIGGERED,
    EXIT_TIME_CAP,
    LACUNA,
    LEADER_GAP_EXIT,
    MULTI_MINT,
    NAO_PRIMEIRA,
    NOT_ARMED,
    RECOMPOSICAO_PENDENTE,
    RULE_SET_RETIRED,
    SELL_WITHOUT_ENTRY,
    TETO_ABERTO,
    TETO_DIA,
    UNCONFIRMED_IGNORED,
    UNKNOWN_WALLET,
    VENUE_FORA_DO_ESCOPO,
    CensorEntry,
    CloseIntent,
    Job,
    LeaderRef,
    OpenIntent,
    RejectEntry,
    leader_ref,
    target_of,
)
from hunter_meme_worker.copy_gaps import GapRegistry, Recompositions
from hunter_meme_worker.copy_position import Decision, Position
from hunter_meme_worker.copy_restore import BookRestore

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.leader_events import LeaderEvent
    from hunter_meme_worker.copy_spec import CopySpec

__all__ = ["CopyBook", "Decision", "Position"]

ONE = Decimal(1)


class CopyBook(BookConfirm, BookGaps, BookRestore):
    def __init__(self, spec: CopySpec, *, t0: datetime, armed: bool = True) -> None:
        self._spec = spec
        self._t0 = t0
        self._armed = armed
        self._stratum = {leader.wallet: leader.stratum for leader in spec.leaders}
        self._by_key: dict[str, Position] = {}
        self._by_pair: dict[tuple[str, str], Position] = {}
        self._observed: set[tuple[str, str]] = set()
        self._unlanded: set[tuple[str, str]] = set()
        self._consumed: set[tuple[str, str]] = set()
        self._attempts: dict[tuple[str, date], int] = {}
        self._occupied: dict[str, int] = {}
        self._end = t0 + timedelta(days=spec.horizon_days)
        self._confirm = Confirmations(spec.confirm_timeout_s)
        self._pool_mints: set[str] = set()
        self._gaps = GapRegistry()
        self._recomp = Recompositions(self._stratum, spec.id)
        self._window_seq = 0

    # ---------------------------------------------------------------- reads
    @property
    def open_count(self) -> int:
        return len(self._by_key)

    @property
    def funnel_unavailable(self) -> bool:
        return self._gaps.funnel_open()

    def position(self, key: str) -> Position | None:
        return self._by_key.get(key)

    def open_positions(self) -> list[Position]:
        return [p for p in self._by_key.values() if p.state == "open"]

    def occupied(self, stratum: str) -> int:
        return self._occupied.get(stratum, 0)

    # ---------------------------------------------------------------- events
    def on_event(self, event: LeaderEvent, now: datetime) -> Decision:
        stratum = self._stratum.get(event.wallet)
        if stratum is None:
            return Decision(skipped=UNKNOWN_WALLET, wallet_known=False)
        seen = self._confirm.get(event)
        if seen is not None:
            return self._repeat(event, seen, now)
        if not event.confirmed and not self._spec.act_on_unconfirmed:
            return Decision(skipped=UNCONFIRMED_IGNORED)
        if event.fields_complete_at < self._t0:  # the design's T0 test: the legs were all there
            return Decision(skipped=BEFORE_T0)
        if event.side == "buy":
            if not self._armed:
                return Decision(skipped=NOT_ARMED)  # T0 is the source's first moment up
            if not self._spec.accepting_entries:
                return Decision(skipped=RULE_SET_RETIRED)  # only keeping what is open
            if now >= self._end:
                return Decision(skipped=AFTER_HORIZON)
        self._confirm.remember(event)
        ref = leader_ref(event, stratum)
        if event.side == "buy":
            return self._on_buy(event, ref, now)
        return self._on_sell(event, ref, now)

    # ---------------------------------------------------------------- entry
    def _on_buy(self, event: LeaderEvent, ref: LeaderRef, now: datetime) -> Decision:
        pair = (event.wallet, event.mint)
        live = self._by_pair.get(pair)
        if live is not None:
            if event.position_after_atoms > live.peak_atoms:
                live.peak_atoms = event.position_after_atoms
                self._confirm.expect(
                    event, live.key, "entry", now
                )  # it moved the policy: confirm it
        if pair in self._observed:
            return Decision(skipped=ALREADY_OBSERVED)
        self._observed.add(pair)
        self._unlanded.add(pair)  # observed in memory; durable once its row lands
        reason = self._refusal(event, ref.stratum, now)
        if reason is not None:
            return Decision(jobs=[RejectEntry(event.mint, ref, reason, now)])
        self._consumed.add((ref.stratum, event.mint))
        day = (event.wallet, now.date())
        self._attempts[day] = self._attempts.get(day, 0) + 1
        if self.occupied(ref.stratum) >= self._spec.max_open_per_stratum:
            return Decision(jobs=[CensorEntry(event.mint, ref, TETO_ABERTO, now)])
        pos = Position(
            key=str(uuid7()),
            leader=event.wallet,
            stratum=ref.stratum,
            mint=event.mint,
            opened_by=event.first_seen_at,
            decided_at=now,
            peak_atoms=event.position_after_atoms,
            contam=self._gaps.health_reason(event.wallet, event.block_time, event.first_seen_at),
        )
        self._add(pos)
        self._confirm.expect(event, pos.key, "entry", now)
        target = target_of(now, self._spec.execution_latency_ms)
        return Decision(jobs=[OpenIntent(pos.key, event.mint, ref, now, target)])

    def _refusal(self, event: LeaderEvent, stratum: str, now: datetime) -> str | None:
        """The first admission condition that fails, in the design's order (§3.2), or ``None``."""
        if event.position_after_atoms - event.token_delta_atoms != 0:
            return NAO_PRIMEIRA
        if event.mint in self._pool_mints:  # learned from a read: this mint trades on the pool
            return VENUE_FORA_DO_ESCOPO
        if event.multi_mint:  # one SOL debit is not N debits: no evidence of what this mint cost
            return MULTI_MINT
        if event.sol_delta_lamports is None:  # a missing SOL leg is never a guessed zero
            return EVIDENCIA_INSUFICIENTE
        if -event.sol_delta_lamports < self._spec.min_trigger_lamports:
            return ABAIXO_DO_PISO
        if (stratum, event.mint) in self._consumed:
            return CO_COMPRA
        if (
            self._attempts.get((event.wallet, now.date()), 0)
            >= self._spec.max_attempts_per_leader_day
        ):
            return TETO_DIA
        if self._gaps.blocks_entry(event.wallet, event.block_time, event.first_seen_at, now):
            return LACUNA
        if self.is_blocked(event.wallet):
            return RECOMPOSICAO_PENDENTE
        return None

    def _add(self, pos: Position) -> None:
        self._by_key[pos.key] = pos
        self._by_pair[(pos.leader, pos.mint)] = pos
        self._occupied[pos.stratum] = self._occupied.get(pos.stratum, 0) + 1

    # ---------------------------------------------------------------- exit
    def _on_sell(self, event: LeaderEvent, ref: LeaderRef, now: datetime) -> Decision:
        pos = self._by_pair.get((event.wallet, event.mint))
        if pos is None or pos.state == "closing":
            return Decision(skipped=SELL_WITHOUT_ENTRY)
        after = event.position_after_atoms
        if after == 0:
            reason = EXIT_LEADER_FULL
        elif Decimal(after) <= Decimal(pos.peak_atoms) * (
            ONE - self._spec.exit_leader_drop_fraction
        ):
            reason = EXIT_LEADER_PEAK_DROP
        else:
            return Decision(skipped=EXIT_NOT_TRIGGERED)
        if event.kind == "transfer":  # we measure "the leader reduced", not "the leader sold"
            reason = EXIT_LEADER_TRANSFER
        censor = pos.gap_reason
        if censor is None and self._gaps.blinds(
            event.wallet, event.block_time, event.first_seen_at
        ):
            censor = LEADER_GAP_EXIT
        if pos.contam is None:
            pos.contam = self._gaps.health_reason(
                event.wallet, event.block_time, event.first_seen_at
            )
        job = self._close(pos, reason, ref, now, censor)
        self._confirm.expect(event, pos.key, "exit", now)
        return Decision(jobs=[job])

    def _close(
        self, pos: Position, reason: str, ref: LeaderRef | None, now: datetime, censor: str | None
    ) -> CloseIntent:
        pos.was, pos.state = pos.state, "closing"
        target = target_of(now, self._spec.execution_latency_ms)
        contaminated = pos.contam or (pos.gap_reason if censor is None else None)
        return CloseIntent(pos.key, pos.mint, reason, ref, now, target, censor, contaminated)

    def request_exit(
        self, key: str, reason: str, now: datetime, *, censor: str | None = None
    ) -> CloseIntent | None:
        pos = self._by_key.get(key)
        if pos is None or pos.state != "open":
            return None
        return self._close(pos, reason, None, now, censor)

    def due_time_caps(self, now: datetime) -> list[CloseIntent]:
        cap = timedelta(seconds=self._spec.time_cap_s)
        return [
            self._close(p, EXIT_TIME_CAP, None, now, None)
            for p in self.open_positions()
            if p.entry_at is not None and now - p.entry_at >= cap
        ]

    # ---------------------------------------------------------------- executor callbacks
    def pool_mint_found(self, key: str, leader: str, stratum: str, mint: str, day: date) -> None:
        """The executor found ``mint`` already on the pool: a venue outside the cohort. The attempt is
        refunded (the funnel row is ``rejected``, not an admitted attempt) and the mint is remembered."""
        self._pool_mints.add(mint)
        self._consumed.discard((stratum, mint))
        left = self._attempts.get((leader, day), 0) - 1
        if left > 0:
            self._attempts[(leader, day)] = left
        else:
            self._attempts.pop((leader, day), None)
        self.mark_closed(key)

    def mark_open(self, key: str, *, bet_id: str, entry_at: datetime) -> None:
        pos = self._by_key.get(key)
        if pos is not None and pos.state == "opening":
            pos.state, pos.bet_id, pos.entry_at = "open", bet_id, entry_at
        elif pos is not None:  # a close was already requested while the entry was being priced
            pos.bet_id, pos.entry_at = bet_id, entry_at

    def mark_closed(self, key: str) -> None:
        """The copy is closed (or never was): release its slot. The pair and the key stay consumed."""
        pos = self._by_key.pop(key, None)
        if pos is None:
            return
        self._by_pair.pop((pos.leader, pos.mint), None)
        self._occupied[pos.stratum] = max(0, self._occupied.get(pos.stratum, 0) - 1)

    def rollback(self, job: Job) -> None:
        """A job was refused or could not be persisted: undo the book's side of the decision."""
        if isinstance(job, OpenIntent):
            self.mark_closed(job.key)
        elif isinstance(job, CloseIntent):
            pos = self._by_key.get(job.key)
            if pos is not None and pos.state == "closing":
                pos.state = pos.was  # a lost exit is retried by the time cap, never forgotten
                if (
                    job.leader is not None
                ):  # the leader's own exit was lost: the time cap is another policy
                    pos.contam = pos.contam or "exit_not_persisted"
