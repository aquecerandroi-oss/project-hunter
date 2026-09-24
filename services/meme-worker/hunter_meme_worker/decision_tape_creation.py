"""The creation-slot bundle of the decision tape (T4.89b) — how much SOL
wallets other than the creator bought in the mint's own creation slot, and
the creator's own buy in that same slot, both kept past the 60 s tape window.

**Why (H-015, ``obsidian/11-KNOWLEDGE/Fila de Hipoteses.md``).** R76/KB-0156
found, exploratorily, that the SOL bought in the creation slot separates the
coordinated dump (AUC 0.675) from the rest — but only on the population that
found it, so it can only be judged on decisions recorded from here on. A
decision made minutes after birth has usually already evicted the creation
slot's own fills from the 60 s deque; this block is read from
:class:`~hunter_meme_worker.event_wallets.WalletLedger`'s own running sum
instead (fed by ``push``'s existing creation-slot branch, T4.89b), which
never expires within the subscription's lifetime.

**Reused, not reinvented, but SOL-only.** The completeness of the number is
the wallet ledger's own "since birth" proof (``ledger.reason`` in
:mod:`hunter_meme_worker.decision_tape`'s ``_holders``) — conservative, not
exact: a coverage gap or an overflowed wallet count *may* have lost a fill
inside the creation slot specifically, so ``sol``/``wallets`` are ``None``
with that same reason rather than risk an undercount presented as final.
:data:`~hunter_meme_worker.event_wallets.TOKENS_UNKNOWN` is the one ledger
reason this block ignores: it says a *token* amount is missing somewhere,
never a SOL amount, so it cannot make the SOL-only ``sol``/``wallets`` here
wrong (Astra, T4.89b review). The creator's own buy is a fact of the
``create`` frame, not of the subscription's coverage since — it is reported
whenever the frame carried it, independent of every one of these reasons.

**``creation_slot`` is inferred, never proven — said so, out loud.** It is
:attr:`~hunter_meme_worker.event_state.MintEventState.crowd`'s
``create_slot``, the slot of the *first trade the subscription received*, not
necessarily the ``create`` transaction's own slot (the create frame carries no
slot). ``reason`` only ever speaks to the *ledger*'s completeness; it is never
``null`` to mean "this slot is correct" — ``slot_source`` says how the slot was
obtained (currently the only way: :data:`FIRST_TRADE_SEEN`), so a reader never
mistakes a complete ledger for a proven slot. ``early_slots`` and
``create_signature`` (below) are how research gets the real one, without an
RPC call on this hot path (Coordinator decision, T4.89b, Astra's HIGH):
resolve ``create_signature``'s slot over RPC, retrospectively — a chain fact
that predates the decision, so reading it back in later is not look-ahead —
and read the ``early_slots`` entry that matches, instead of trusting the
inference.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_meme_worker.event_wallets import TOKENS_UNKNOWN

if TYPE_CHECKING:
    from hunter_meme_worker.event_state import MintEventState
    from hunter_meme_worker.event_wallets import WalletLedger

__all__ = ["CREATION_SLOT_UNKNOWN", "FIRST_TRADE_SEEN", "creation_bundle_json"]

CREATION_SLOT_UNKNOWN = "creation_slot_unknown"
"""The mint was not subscribed at its own creation (T4.70's
``subscribe_at_create``): ``crowd.create_slot`` was never learned, so there is
no slot to count buyers in — the periodic sync's own safe fallback."""
FIRST_TRADE_SEEN = "first_trade_seen"
"""The only way ``creation_slot`` is currently obtained: the slot of the first
trade the subscription received (T4.70) — never a proven creation-tx slot."""


def _sol(lamports: int) -> str:
    return format(Decimal(lamports).scaleb(-9).normalize(), "f")


def _early_slots_json(ledger: WalletLedger) -> list[dict[str, Any]]:
    return [
        {
            "slot": agg.slot,
            "sol_others": _sol(agg.sol_others),
            "wallets_others": len(agg.wallets_others),
            "creator_sol": _sol(agg.creator_sol),
        }
        for agg in ledger.early_slots.values()
    ]


def creation_bundle_json(state: MintEventState, *, ledger_reason: str | None) -> dict[str, Any]:
    """The ``derived.creation_bundle`` block (H-015).

    ``ledger_reason`` is the wallet ledger's own reconciliation reason (the
    same one already computed for ``derived.ledger`` — never recomputed here).
    """
    slot = state.crowd.create_slot
    ledger = state.wallets
    if slot is None:
        reason = CREATION_SLOT_UNKNOWN
    elif ledger_reason == TOKENS_UNKNOWN:
        reason = None  # a missing token amount never taints a SOL-only sum
    else:
        reason = ledger_reason
    complete = reason is None
    return {
        "creation_slot": slot,
        "slot_source": None if slot is None else FIRST_TRADE_SEEN,
        "sol": _sol(ledger.creation_block_lamports) if complete else None,
        "wallets": len(ledger.creation_block_wallets) if complete else None,
        "creator_buy_sol": (
            None
            if ledger.creator_initial_buy_lamports is None
            else _sol(ledger.creator_initial_buy_lamports)
        ),
        "create_signature": ledger.create_signature,
        "early_slots": _early_slots_json(ledger),
        "reason": reason,
    }
