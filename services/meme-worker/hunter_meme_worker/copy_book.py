"""The copy lane's decision, in memory (H-037). **Synchronous on purpose**: the buy/follow path must
be milliseconds (Everton, 2026-10-09), so a leader event is decided against dictionaries — the
frozen leader set, the keys consumed, the day's attempts, the copies held, the gaps, the facts seen —
with no await, no database, no HTTP and no blocking call. Pricing and persistence are the executor's
(``copy_exec.py``); this module says *what* to do and *when we decided it*.

Rules (``docs/design/copiar-carteiras-papel.md`` §3.2/§3.4, pre-registered in EXP-M28):

* **entry** = the first observation of a (leader, mint) pair, if it is a first purchase (position
  before = 0) of at least ``min_trigger_sol``, on the curve, with the (stratum, mint) key free, under
  ``max_attempts_per_leader_day`` and not gapped; an admitted attempt **consumes the key** even if it
  ends unfilled. Every first observation not admitted is a durable ``rejected`` funnel row;
* **exit** = the leader's ``position_after`` at 0 or at ``exit_leader_drop_fraction`` of its peak; our
  own exits (stop, time cap) come from the sweep and the mark pass; a gap censors a leader-driven exit;
* **confirmation**: act on the first trustworthy signal; the chain's verdict (``LeaderConfirmation``, or
  the same fact re-sent) records the delay, and ``divergent``/``failed_tx``/``not_found`` **invalidate**
  the copy by name — it stays in the primary, sold at market (``invalidated``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.types import uuid7
from hunter_meme_worker.copy_confirm import Confirmations, Pending, Seen
from hunter_meme_worker.copy_events import (
    ABAIXO_DO_PISO,
    AFTER_HORIZON,
    ALREADY_OBSERVED,
    BEFORE_T0,
    CO_COMPRA,
    DUPLICATE_SIGNATURE,
    EVIDENCIA_INSUFICIENTE,
    EXIT_INVALIDATED,
    EXIT_LEADER_FULL,
    EXIT_LEADER_PEAK_DROP,
    EXIT_LEADER_TRANSFER,
    EXIT_NOT_TRIGGERED,
    EXIT_TIME_CAP,
    FUNIL_INDISPONIVEL,
    INVALID_DIVERGENT,
    INVALID_NOT_FOUND,
    LACUNA,
    LEADER_GAP_EXIT,
    MULTI_MINT,
    NAO_PRIMEIRA,
    RULE_SET_RETIRED,
    SELL_WITHOUT_ENTRY,
    TETO_ABERTO,
    TETO_DIA,
    UNCONFIRMED_IGNORED,
    UNKNOWN_WALLET,
    VENUE_FORA_DO_ESCOPO,
    CensorEntry,
    CloseIntent,
    ConfirmIntent,
    InvalidateIntent,
    Job,
    LeaderRef,
    OpenIntent,
    RejectEntry,
    leader_ref,
    target_of,
)
from hunter_meme_worker.copy_gaps import GapRegistry
from hunter_meme_worker.copy_position import Decision, Position
from hunter_meme_worker.copy_restore import BookRestore

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.leader_events import LeaderConfirmation, LeaderEvent, LeaderGap
    from hunter_meme_worker.copy_spec import CopySpec

__all__ = ["CopyBook", "Decision", "Position"]

ONE = Decimal(1)


class CopyBook(BookRestore):
    def __init__(self, spec: CopySpec, *, t0: datetime) -> None:
        self._spec = spec
        self._t0 = t0
        self._stratum = {leader.wallet: leader.stratum for leader in spec.leaders}
        self._by_key: dict[str, Position] = {}
        self._by_pair: dict[tuple[str, str], Position] = {}
        self._observed: set[tuple[str, str]] = set()
        self._consumed: set[tuple[str, str]] = set()
        self._attempts: dict[tuple[str, date], int] = {}
        self._occupied: dict[str, int] = {}
        self._end = t0 + timedelta(days=spec.horizon_days)
        self._confirm = Confirmations(spec.confirm_timeout_s)
        self._pool_mints: set[str] = set()
        self.funnel_unavailable = False
        self._gaps = GapRegistry()

    # ---------------------------------------------------------------- reads
    @property
    def open_count(self) -> int:
        return len(self._by_key)

    def position(self, key: str) -> Position | None:
        return self._by_key.get(key)

    def open_positions(self) -> list[Position]:
        return [p for p in self._by_key.values() if p.state == "open"]

    def occupied(self, stratum: str) -> int:
        return self._occupied.get(stratum, 0)

    # ---------------------------------------------------------------- gaps
    def on_gap(self, gap: LeaderGap, now: datetime) -> None:
        self._gaps.add(gap)
        for pos in self._by_key.values():
            affected = gap.wallet is None or gap.wallet == pos.leader
            if (
                affected
                and GapRegistry.overlaps_life(gap, pos.opened_by)
                and pos.gap_reason is None
            ):
                pos.gap_reason = LEADER_GAP_EXIT

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
            if not self._spec.accepting_entries:
                return Decision(skipped=RULE_SET_RETIRED)  # only keeping what is open
            if now >= self._end:
                return Decision(skipped=AFTER_HORIZON)
            if (
                self.funnel_unavailable
            ):  # a funnel write was lost: eligibility is no longer recoverable
                return Decision(skipped=FUNIL_INDISPONIVEL)
        self._confirm.remember(event)
        ref = leader_ref(event, stratum)
        if event.side == "buy":
            return self._on_buy(event, ref, now)
        return self._on_sell(event, ref, now)

    def _repeat(self, event: LeaderEvent, seen: Seen, now: datetime) -> Decision:
        outcome = self._confirm.confirmed(event, seen)
        if outcome is None:
            return Decision(skipped=DUPLICATE_SIGNATURE)
        pending, same = outcome
        if not same:  # the same transaction confirmed with another fact: what we acted on was wrong
            return Decision(jobs=self._invalidate(pending, INVALID_DIVERGENT, now))
        delay = int((event.first_seen_at - pending.first_observed_at).total_seconds() * 1000)
        return Decision(
            jobs=[ConfirmIntent(pending.key, event.signature, pending.kind, max(0, delay))]
        )

    # ---------------------------------------------------------------- entry
    def _on_buy(self, event: LeaderEvent, ref: LeaderRef, now: datetime) -> Decision:
        pair = (event.wallet, event.mint)
        live = self._by_pair.get(pair)
        if live is not None:
            live.peak_atoms = max(live.peak_atoms, event.position_after_atoms)
        if pair in self._observed:
            return Decision(
                skipped=ALREADY_OBSERVED
            )  # only the first observation of a pair is a fact
        self._observed.add(pair)
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
        if self._gaps.covers(event.wallet, event.block_time, event.first_seen_at):
            return LACUNA
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
        if censor is None and self._gaps.covers(
            event.wallet, event.block_time, event.first_seen_at
        ):
            censor = LEADER_GAP_EXIT
        job = self._close(pos, reason, ref, now, censor)
        self._confirm.expect(event, pos.key, "exit", now)
        return Decision(jobs=[job])

    def on_confirmation(self, conf: LeaderConfirmation, now: datetime) -> Decision:
        """The chain's verdict on a fact we acted on. ``confirmed`` records the delay; ``divergent``,
        ``failed_tx`` and ``not_found`` invalidate the copy by that name (it stays in the primary);
        ``rpc_error`` says nothing and leaves the timeout running. Idempotent per fact."""
        if conf.wallet not in self._stratum or conf.status == "rpc_error":
            return Decision(skipped=UNKNOWN_WALLET if conf.wallet not in self._stratum else None)
        found = self._confirm.of_fact(conf.signature, conf.wallet, conf.mint)
        if found is None:
            return Decision(skipped=DUPLICATE_SIGNATURE)
        pending, seen = found
        if conf.status == "confirmed":
            chain = (conf.chain_position_after_atoms, conf.chain_token_delta_atoms)
            same = all(
                c is None or c == s
                for c, s in zip(chain, (seen.position_after, seen.token_delta), strict=True)
            )
            if not same:
                return Decision(jobs=self._invalidate(pending, INVALID_DIVERGENT, now))
            delay = int((conf.confirmed_at - pending.first_observed_at).total_seconds() * 1000)
            return Decision(
                jobs=[ConfirmIntent(pending.key, pending.signature, pending.kind, max(0, delay))]
            )
        return Decision(jobs=self._invalidate(pending, conf.status, now))

    def _close(
        self, pos: Position, reason: str, ref: LeaderRef | None, now: datetime, censor: str | None
    ) -> CloseIntent:
        pos.was, pos.state = pos.state, "closing"
        target = target_of(now, self._spec.execution_latency_ms)
        contaminated = pos.gap_reason if censor is None else None
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

    # ---------------------------------------------------------------- confirmation
    def expired_confirmations(self, now: datetime) -> list[Job]:
        """Events that never confirmed inside the timeout. The copy is **invalidated, not dropped**:
        if still held it is sold at market (``invalidated``) and stays in the primary, and either way
        the named reason is written on it."""
        out: list[Job] = []
        for pending in self._confirm.expired(now):
            out.extend(self._invalidate(pending, INVALID_NOT_FOUND, now))
        return out

    def _invalidate(self, pending: Pending, reason: str, now: datetime) -> list[Job]:
        jobs: list[Job] = []
        pos = self._by_key.get(pending.key)
        if pos is not None and pos.state != "closing":
            jobs.append(self._close(pos, EXIT_INVALIDATED, None, now, None))
        jobs.append(InvalidateIntent(pending.key, pending.signature, pending.kind, reason, now))
        return jobs

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
        """The persistence queue refused ``job``: undo the book's side of the decision."""
        if isinstance(job, OpenIntent):
            self.mark_closed(job.key)
        elif isinstance(job, CloseIntent):
            pos = self._by_key.get(job.key)
            if pos is not None and pos.state == "closing":
                pos.state = pos.was  # a lost exit is retried by the time cap, never forgotten
