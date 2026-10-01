"""T4.74-4 — the pure half of ``spot_send.spot_leg``: the result shape, the
derived order key, the quote sanity check and the post-simulation balance
invariant. No network, no database, no signer — testable by a table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

from hunter_exchanges.pumpfun.rent import rent_funded_by
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID, associated_token_address

if TYPE_CHECKING:
    from hunter_exchanges.jupiter import JupiterQuote

__all__ = [
    "ATA_RENT_MAX_LAMPORTS",
    "ATA_RENT_SOURCE",
    "BASE_FEE_LAMPORTS",
    "SIMULATION_MARGIN_LAMPORTS",
    "LegResult",
    "TxFill",
    "check_simulated_leg",
    "entry_spend",
    "fee_allowance_lamports",
    "fill_from_transaction",
    "quote_mismatch",
    "spot_client_order_id",
    "stored_fill_rent",
]

ATA_RENT_MAX_LAMPORTS: Final = 2_039_280
"""A **ceiling**, never the amount paid: the pre-reduction rent-exempt minimum of a
165-byte token account ((165 + 128) × 6 960). Only the simulation's allowance
uses it (looser by 550 840 lamports per ATA than today's 1 488 440 — it never
refuses a legitimate buy). What a buy actually locked is read from its own
transaction (``TxFill.ata_rent_lamports``) — KB-0171: the constant made
``sol_spent`` 550 840 lamports short and ``pnl_sol`` as much too high."""
ATA_RENT_SOURCE: Final = "tx_meta_ata_balance"
"""``fill.ata_rent_source`` of a fill whose rent was read from its own transaction.
A stored fill without it predates KB-0171 and carries the old constant."""
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
    created it (kept out of ``sol_spent``), ``None`` when unreadable (KB-0171)."""

    status: str
    reason: str | None
    signature: str | None
    filled_atoms: int
    sol_delta_lamports: int
    quote: JupiterQuote | None
    ata_rent_lamports: int | None = 0
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
        retained * ATA_RENT_MAX_LAMPORTS
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
    account of the mint before/after.
    ``ata_rent_lamports`` (KB-0171): the lamports this transaction added to the
    wallet's ATA of the mint it created — ``0`` when none was created, ``None``
    when one was created but the meta does not let the deposit be read."""

    sol_delta_lamports: int
    token_before_atoms: int
    token_after_atoms: int
    network_fee_lamports: int
    ata_rent_lamports: int | None = 0

    @property
    def token_delta_atoms(self) -> int:
        return self.token_after_atoms - self.token_before_atoms


def entry_spend(sol_delta_lamports: int, ata_rent_lamports: int | None) -> tuple[int, int, str]:
    """``(sol_spent, ata_rent, source)`` of a confirmed buy — the one rule of the
    executor's two openers and of ``infra/scripts/spot_fix_ata_rent.py``. The
    rent read from the transaction is a deposit, kept out of the spend; an
    unknown rent is **folded into** the spend (a pessimistic PnL, never an
    optimistic one) and named; a rent larger than the outflow is a contradiction,
    folded as well (the T4.74-4 rule)."""
    outflow = -sol_delta_lamports
    if ata_rent_lamports is None:
        return outflow, 0, "signature_delta_rent_unknown"
    spent = outflow - ata_rent_lamports
    if spent <= 0:
        return outflow, 0, "signature_delta_rent_folded"
    return spent, ata_rent_lamports, "signature_delta_minus_rent"


def stored_fill_rent(fill: dict[str, Any]) -> int | None:
    """The rent of a **stored** buy fill (the reconcile's late open and orphan
    repair): trusted only with :data:`ATA_RENT_SOURCE`; a legacy fill that says
    it locked rent carries the old constant — unknown, never believed (Astra,
    design review). A legacy ``0``/absent rent is a reused ATA: ``0``."""
    raw = fill.get("ata_rent_lamports")
    if fill.get("ata_rent_source") == ATA_RENT_SOURCE:
        return None if raw is None else int(raw)
    return 0 if not raw else None


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _key(value: Any) -> Any:
    return _obj(value).get("pubkey") if isinstance(value, dict) else value


def _all_keys(tx: dict[str, Any], meta: dict[str, Any]) -> list[Any]:
    """Static keys, then ``loadedAddresses`` writable, then readonly — the order
    ``accountIndex`` and ``pre/postBalances`` index (``encoding: json``; under
    ``jsonParsed`` the static list already carries the loaded ones)."""
    static = [
        _key(k) for k in _seq(_obj(_obj(tx.get("transaction")).get("message")).get("accountKeys"))
    ]
    loaded = _obj(meta.get("loadedAddresses"))
    return static + _seq(loaded.get("writable")) + _seq(loaded.get("readonly"))


def _index(entry: dict[str, Any]) -> int | None:
    value = entry.get("accountIndex")
    return value if type(value) is int else None  # never a bool, a list, a string


def _created_rent(
    tx: dict[str, Any], keys: list[Any], created: list[dict[str, Any]], wallet: str, mint: str
) -> int | None:
    """The lamports the transaction deposited in each token account it created,
    **proven paid by the wallet** (Astra, diff review): the account must be the
    wallet's own ATA of ``mint`` and an inner ``system::createAccount`` whose
    source is the wallet must have funded it with exactly its integral balance
    delta (``pumpfun.rent.rent_funded_by``, the repo's one reader of it). A
    pre-funded address (topped up by transfer, no ``createAccount``), a deposit
    from anyone else, or any unreadable piece: ``None``."""
    meta = _obj(tx.get("meta"))
    pre, post = _seq(meta.get("preBalances")), _seq(meta.get("postBalances"))
    funded = rent_funded_by(tx, [str(k) for k in keys], wallet)
    total, seen = 0, set[int]()
    for entry in created:
        index = _index(entry)
        if index is None or index in seen or not (0 <= index < min(len(pre), len(post), len(keys))):
            return None
        seen.add(index)
        program = str(entry.get("programId") or TOKEN_PROGRAM_ID)
        try:
            ata = associated_token_address(wallet, mint, token_program=program)
        except (TypeError, ValueError, KeyError):
            return None
        lo, hi = pre[index], post[index]
        if keys[index] != ata or type(lo) is not int or type(hi) is not int:
            return None
        delta = hi - lo
        if delta <= 0 or funded.get(ata) != delta:
            return None
        total += delta
    return total


def fill_from_transaction(tx: dict[str, Any], *, wallet: str, mint: str) -> TxFill | None:
    """``None`` when the meta is missing, errored, or does not name the wallet as
    the fee payer — the caller keeps the row ``submitted_unconfirmed``, never guesses."""
    meta = _obj(tx.get("meta"))
    if not meta or meta.get("err") is not None:
        return None
    keys = _all_keys(tx, meta)
    if not keys or keys[0] != wallet:
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
    before, after = 0, 0
    pre_indexes = {_index(_obj(e)) for e in _seq(meta.get("preTokenBalances"))} - {None}
    created: list[dict[str, Any]] = []
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
                before += units
                continue
            after += units
            index = _index(entry)
            if index is None or index not in pre_indexes:
                created.append(entry)  # by account, not "the mint was unseen" (Astra)
    rent = _created_rent(tx, keys, created, wallet, mint) if created else 0
    return TxFill(sol_delta, before, after, fee, rent)
