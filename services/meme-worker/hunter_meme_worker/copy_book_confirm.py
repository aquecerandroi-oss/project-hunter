"""The confirmation half of the copy book (H-037): what the chain says, late, about a fact we acted on the
instant it was first trustworthy. Split from ``copy_book.py`` for the 350-line budget; :class:`CopyBook`
inherits it and owns the state these methods read.

* ``confirmed`` records the delay (and the ``ideal`` post-trade reserves when the chain sent them);
* ``divergent`` / ``failed_tx`` / ``not_found`` **invalidate** the copy by that name — it stays in the
  primary, sold at market (``invalidated``);
* ``rpc_error`` is its own state (R2 B5): the copy keeps waiting. If the deadline comes and *only*
  ``rpc_error`` ever answered, the copy is flagged ``unverified`` and **kept** — a node that did not answer
  is not a verdict. Silence to the deadline (no answer at all) is still ``not_found``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hunter_meme_worker.copy_confirm import Confirmations, Pending, Seen
from hunter_meme_worker.copy_events import (
    DUPLICATE_SIGNATURE,
    EXIT_INVALIDATED,
    INVALID_DIVERGENT,
    INVALID_NOT_FOUND,
    UNKNOWN_WALLET,
    CloseIntent,
    ConfirmIntent,
    InvalidateIntent,
    Job,
    LeaderRef,
    UnverifiedIntent,
)
from hunter_meme_worker.copy_position import Decision, Position

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_exchanges.pumpfun.leader_events import LeaderConfirmation, LeaderEvent, PostReserves

__all__ = ["BookConfirm"]


def reserves_json(post: PostReserves | None) -> dict[str, Any] | None:
    if post is None:
        return None
    return {
        "venue": post.venue,
        "sol_reserves": post.sol_reserves,
        "token_reserves": post.token_reserves,
        "virtual_quote_reserves": post.virtual_quote_reserves,
        "real_sol_reserves": post.real_sol_reserves,
    }


class BookConfirm:
    _stratum: dict[str, str]
    _by_key: dict[str, Position]
    _confirm: Confirmations

    def _close(
        self, pos: Position, reason: str, ref: LeaderRef | None, now: datetime, censor: str | None
    ) -> CloseIntent:
        raise NotImplementedError

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

    def on_confirmation(self, conf: LeaderConfirmation, now: datetime) -> Decision:
        """The chain's verdict on a fact we acted on. Idempotent per fact."""
        if conf.wallet not in self._stratum:
            return Decision(skipped=UNKNOWN_WALLET)
        if conf.status == "rpc_error":
            self._confirm.note_rpc_error(conf.signature, conf.wallet, conf.mint)
            return Decision()
        found = self._confirm.of_fact(conf.signature, conf.wallet, conf.mint)
        if found is None:
            return Decision(skipped=DUPLICATE_SIGNATURE)
        pending, seen = found
        if conf.status != "confirmed":
            return Decision(jobs=self._invalidate(pending, conf.status, now))
        chain = (conf.chain_position_after_atoms, conf.chain_token_delta_atoms)
        mine = (seen.position_after, seen.token_delta)
        if any(c is not None and c != s for c, s in zip(chain, mine, strict=True)):
            return Decision(jobs=self._invalidate(pending, INVALID_DIVERGENT, now))
        delay = int((conf.confirmed_at - pending.first_observed_at).total_seconds() * 1000)
        return Decision(
            jobs=[
                ConfirmIntent(
                    pending.key,
                    pending.signature,
                    pending.kind,
                    max(0, delay),
                    reserves_json(conf.post_reserves),
                )
            ]
        )

    def expired_confirmations(self, now: datetime) -> list[Job]:
        """Events that never got a verdict inside the timeout (see the module docstring)."""
        out: list[Job] = []
        for pending in self._confirm.expired(now):
            if pending.rpc_only:
                out.append(UnverifiedIntent(pending.key, pending.signature, pending.kind, now))
            else:
                out.extend(self._invalidate(pending, INVALID_NOT_FOUND, now))
        return out

    def _invalidate(self, pending: Pending, reason: str, now: datetime) -> list[Job]:
        jobs: list[Job] = []
        pos = self._by_key.get(pending.key)
        if pos is not None and pos.state != "closing":
            jobs.append(self._close(pos, EXIT_INVALIDATED, None, now, None))
        jobs.append(InvalidateIntent(pending.key, pending.signature, pending.kind, reason, now))
        return jobs
