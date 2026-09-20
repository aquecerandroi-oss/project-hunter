"""T4.74-4 — the pure half of ``spot_send.spot_leg``: the result shape, the
derived order key, the quote sanity check and the post-simulation balance
invariant. No network, no database, no signer — testable by a table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

if TYPE_CHECKING:
    from hunter_exchanges.jupiter import JupiterQuote

__all__ = [
    "ATA_RENT_LAMPORTS",
    "BASE_FEE_LAMPORTS",
    "SIMULATION_MARGIN_LAMPORTS",
    "LegResult",
    "TxFill",
    "check_simulated_leg",
    "fee_allowance_lamports",
    "fill_from_transaction",
    "quote_mismatch",
    "spot_client_order_id",
]

ATA_RENT_LAMPORTS: Final = 2_039_280
"""Rent-exempt minimum of an SPL token account (165 bytes) — what a buy that
creates the token's ATA leaves locked in it (design §4: declared, not PnL)."""
BASE_FEE_LAMPORTS: Final = 5_000
"""One signature's base fee."""
SIMULATION_MARGIN_LAMPORTS: Final = 10_000
"""Slack over the fees the verified transaction can charge — a rounding, not a budget."""


@dataclass(frozen=True, slots=True)
class LegResult:
    """``status``: ``refused`` | ``failed`` | ``submitted_unconfirmed`` | ``confirmed``
    — the row's status as the process left it. ``filled_atoms``: a buy's token
    delta / a sell's lamports landed (net); ``sol_delta_lamports``: wallet after
    − before, read from the chain after ``confirmed`` — both ``0`` unless
    ``confirmed``. ``ata_rent_lamports``: the token ATA's rent when this buy
    created it (kept out of ``sol_spent``)."""

    status: str
    reason: str | None
    signature: str | None
    filled_atoms: int
    sol_delta_lamports: int
    quote: JupiterQuote | None
    ata_rent_lamports: int = 0
    priority_fee_lamports: int | None = None


def spot_client_order_id(subject_id: str, *, side: str, attempt: int = 1) -> str:
    """``spot:buy:<signal_id>`` / ``spot:sell:<position_id>:<attempt>`` — derived,
    never random: a replay of the same signal or attempt is the same key."""
    if side == "buy":
        return f"spot:buy:{subject_id}"
    return f"spot:sell:{subject_id}:{attempt}"


def quote_mismatch(
    quote: JupiterQuote, input_mint: str, output_mint: str, amount: int
) -> str | None:
    """T4.54b fix B: the quote must be for this pair and this amount, with a positive out."""
    if quote.input_mint != input_mint:
        return "quote_mismatch:input_mint"
    if quote.output_mint != output_mint:
        return "quote_mismatch:output_mint"
    if int(quote.in_amount) != amount:
        return "quote_mismatch:in_amount"
    if int(quote.out_amount) <= 0 or int(quote.other_amount_threshold) <= 0:
        return "quote_mismatch:out_amount"
    return None


def fee_allowance_lamports(
    *, ata_creates: int, priority_fee_lamports: int, transient_ata: int = 0
) -> int:
    """What the **verified** transaction may cost beyond the swap itself: the rent
    of every ATA it creates **and keeps** (``transient_ata`` = the wallet's own
    WSOL account Jupiter opens and closes in the same transaction, whose rent
    comes back), the capped priority fee, the base fee and a margin."""
    retained = max(0, ata_creates - max(0, transient_ata))
    return (
        retained * ATA_RENT_LAMPORTS
        + priority_fee_lamports
        + BASE_FEE_LAMPORTS
        + SIMULATION_MARGIN_LAMPORTS
    )


def check_simulated_leg(
    *,
    is_buy: bool,
    sol_before: int,
    sol_after: int,
    token_before: int,
    token_after: int,
    amount_atoms: int,
    min_out: int,
    fee_allowance_lamports: int,
) -> str | None:
    """``equity = cash + positions`` over the **simulated** post-state: a buy may
    spend at most the ticket plus the fees the verified transaction can charge
    and must land at least the quote's minimum; a sell may give at most the lot
    and must land at least the minimum minus those fees."""
    if is_buy:
        if sol_after < sol_before - amount_atoms - fee_allowance_lamports:
            return "simulation_sol_overspent"
        if token_after < token_before + min_out:
            return "simulation_token_short"
        return None
    if token_after < token_before - amount_atoms:
        return "simulation_token_overspent"
    if sol_after < sol_before + min_out - fee_allowance_lamports:
        return "simulation_sol_short"
    return None


@dataclass(frozen=True, slots=True)
class TxFill:
    """What **this signature** did, from ``getTransaction``'s ``meta`` (never the
    wallet's balance before/after, which another transaction can move — Astra,
    review of this diff): the fee payer's lamport delta, the wallet's token
    account of the mint before/after, whether the transaction created it."""

    sol_delta_lamports: int
    token_before_atoms: int
    token_after_atoms: int
    ata_created: bool
    network_fee_lamports: int

    @property
    def token_delta_atoms(self) -> int:
        return self.token_after_atoms - self.token_before_atoms


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def fill_from_transaction(tx: dict[str, Any], *, wallet: str, mint: str) -> TxFill | None:
    """``None`` when the meta is missing, errored, or does not name the wallet as
    the fee payer — the caller keeps the row ``submitted_unconfirmed``, never guesses."""
    meta = _obj(tx.get("meta"))
    if not meta or meta.get("err") is not None:
        return None
    keys = _seq(_obj(_obj(tx.get("transaction")).get("message")).get("accountKeys"))
    payer = keys[0] if keys else None
    payer_key = _obj(payer).get("pubkey") if isinstance(payer, dict) else payer
    if payer_key != wallet:
        return None
    pre, post = _seq(meta.get("preBalances")), _seq(meta.get("postBalances"))
    try:
        sol_delta = int(post[0]) - int(pre[0])
        fee = int(meta.get("fee", 0))
    except (IndexError, TypeError, ValueError):
        return None
    if not all(isinstance(meta.get(k), list) for k in ("preTokenBalances", "postTokenBalances")):
        return (
            None  # Astra: an unreadable list is not an empty one (a "created" ATA out of nothing)
        )
    before, after, seen_before, seen_after = 0, 0, False, False
    for label in ("preTokenBalances", "postTokenBalances"):
        for entry_any in _seq(meta.get(label)):
            entry = _obj(entry_any)
            if entry.get("owner") != wallet or entry.get("mint") != mint:
                continue
            try:
                units = int(str(_obj(entry.get("uiTokenAmount")).get("amount", "0")))
            except (TypeError, ValueError):
                return None
            if label == "preTokenBalances":
                before, seen_before = before + units, True
            else:
                after, seen_after = after + units, True
    return TxFill(sol_delta, before, after, seen_after and not seen_before, fee)
