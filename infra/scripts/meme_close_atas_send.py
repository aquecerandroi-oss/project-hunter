"""The money-moving half of ``meme_close_atas.py --apply`` (T4.77): one
batch of ``CloseAccount`` instructions built by us (no Jupiter), verified,
simulated with the wallet's post-state, signed once, audited **before** the
broadcast, sent, confirmed — the discipline of ``meme_spot_swap_send.py``
(T4.73b) applied to a transaction whose only effect is rent flowing back to
the wallet.

Order, and why it is this order:

1. build (``meme_close_atas_plan.build_batch_message``) → verify
   (``meme_close_atas_verify``) on the compiled message: anything but
   ComputeBudget + ``CloseAccount`` to the wallet is refused by name, and the
   signer has not been asked for anything yet;
2. ``simulateTransaction`` of the **unsigned** bytes (``sigVerify=false``)
   with ``accounts=(wallet,)``: the simulated wallet balance must grow by at
   least ``Σ rent − (base fee + priority fee)`` or the batch is refused
   (``simulation_lamports_short``) — a close that does not refund us is not a
   close we send;
3. sign once; the signature is ``b58(ed25519 bytes)`` (the Solana tx id) and
   the ``system_events`` row ``close_atas_submitted`` carrying it is
   **committed before** ``sendTransaction`` — an RPC that relays and then
   times out can never leave a broadcast without a trail;
4. confirm, ``CONFIRM_ATTEMPTS × CONFIRM_INTERVAL_S``; still pending, or an
   unreadable status, or an exception from the send ⇒ ``submitted`` (exit
   66 upstream: reconcile by the printed signature); a verdict — success
   **or** error — only counts at ``confirmed``/``finalized`` (Astra, T4.77
   review: an error seen at ``processed`` may sit on a fork that is dropped;
   until the chosen commitment says so the batch stays ``submitted``);
   landed ⇒ ``confirmed`` with ``lamports_recovered`` read from **this
   transaction's** ``meta.postBalances[0] − meta.preBalances[0]``
   (``getTransaction``, the wallet is account 0 as the payer) — never from
   two live balance reads, which a concurrent deposit or buy would
   contaminate; a meta that cannot be read after ``TX_META_ATTEMPTS`` leaves
   the batch ``submitted`` (``confirmed_recovery_unmeasured``): a number this
   process did not measure is not written as recovered.

Each audit row is committed on its own (commit-as-you-go, T4.73b finding 3).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Protocol, cast

from meme_close_atas_plan import TokenAccountRow, build_batch_message
from meme_close_atas_verify import CloseAtasRefused, verify_close_atas_message
from meme_ops_db import record_event

from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.solana_codec import (
    b58encode,
    serialize_message,
    serialize_transaction,
)
from hunter_exchanges.pumpfun.tx_rpc import SimulationResult

__all__ = [
    "BASE_FEE_LAMPORTS",
    "COMPONENT",
    "CONFIRM_ATTEMPTS",
    "CONFIRM_INTERVAL_S",
    "TX_META_ATTEMPTS",
    "BatchResult",
    "classify_status",
    "result_json",
    "run_batch",
    "transaction_wallet_delta",
]

logger = get_logger(__name__)

COMPONENT = "meme_close_atas"
CONFIRM_ATTEMPTS = 20
CONFIRM_INTERVAL_S = 1.0
TX_META_ATTEMPTS = 3
BASE_FEE_LAMPORTS = 5_000  # one signature
_SETTLED = ("confirmed", "finalized")
LAMPORTS = Decimal(1_000_000_000)


class Rpc(Protocol):
    def get_latest_blockhash(self, *, commitment: str = "confirmed") -> tuple[str, int]: ...
    def call(self, method: str, params: list[Any]) -> Any: ...
    def simulate_transaction(
        self, transaction: bytes, /, *, sig_verify: bool, accounts: tuple[str, ...]
    ) -> SimulationResult: ...
    def send_transaction(self, transaction: bytes, /) -> str: ...
    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]: ...
    def get_transaction(
        self, signature: str, *, commitment: str = "confirmed"
    ) -> dict[str, Any] | None: ...


class Signer(Protocol):
    @property
    def pubkey(self) -> str: ...
    def sign(self, message: bytes, /) -> bytes: ...


@dataclass(frozen=True, slots=True)
class BatchResult:
    """``status``: ``refused`` | ``submitted`` (sent, not confirmed within
    the wait — reconcile by ``signature``) | ``failed`` | ``confirmed``.
    ``n_closed`` and ``lamports_recovered`` are ``0`` unless ``confirmed``;
    ``lamports_recovered`` is the wallet's measured delta, net of fees."""

    status: str
    signature: str | None
    n_closed: int
    lamports_recovered: int
    expected_rent: int
    reason: str | None = None


def result_json(result: BatchResult, *, batch_index: int) -> str:
    payload: dict[str, Any] = {"batch": batch_index, **asdict(result)}
    payload["sol_recovered"] = f"{Decimal(result.lamports_recovered) / LAMPORTS:.9f}"
    payload["expected_rent_lamports"] = payload.pop("expected_rent")
    ordered = (
        "batch",
        "status",
        "signature",
        "n_closed",
        "lamports_recovered",
        "sol_recovered",
        "expected_rent_lamports",
        "reason",
    )
    return json.dumps({k: payload[k] for k in ordered})


def _lamports(rpc: Rpc, wallet: str) -> int:
    result = cast(dict[str, Any], rpc.call("getBalance", [wallet, {"commitment": "confirmed"}]))
    return int(cast(int, result["value"]))


async def _audit(conn: Any, *, level: str, event: str, message: str, data: dict[str, Any]) -> None:
    await record_event(
        conn, component=COMPONENT, level=level, event=event, message=message, data=data
    )
    await conn.commit()


async def run_batch(
    conn: Any,
    rpc: Rpc,
    signer: Signer,
    *,
    batch: Sequence[TokenAccountRow],
    reason: str,
    actor: str,
    priority_fee_lamports: int,
) -> BatchResult:
    wallet = signer.pubkey
    accounts = tuple(row.address for row in batch)
    expected_rent = sum(row.lamports for row in batch)
    fee_allowance = BASE_FEE_LAMPORTS + priority_fee_lamports
    base: dict[str, Any] = {
        "actor": actor,
        "reason": reason,
        "wallet": wallet,
        "accounts": list(accounts),
        "mints": [row.mint for row in batch],
        "expected_rent_lamports": expected_rent,
        "priority_fee_lamports": priority_fee_lamports,
    }

    async def refuse(refusal: str) -> BatchResult:
        logger.warning("meme_close_atas_refused", refusal=refusal)
        await _audit(
            conn,
            level="warning",
            event="close_atas_refused",
            message=f"{reason}: refused {refusal}",
            data={**base, "refusal": refusal},
        )
        return BatchResult("refused", None, 0, 0, expected_rent, refusal)

    # --- build and verify; nothing has been signed
    blockhash, _ = rpc.get_latest_blockhash()
    message = build_batch_message(
        wallet=wallet,
        accounts=accounts,
        blockhash=blockhash,
        priority_fee_lamports=priority_fee_lamports,
    )
    try:
        verify_close_atas_message(message, wallet=wallet, allowed_accounts=frozenset(accounts))
    except CloseAtasRefused as exc:
        return await refuse(exc.reason)
    message_bytes = serialize_message(message)
    unsigned = serialize_transaction((bytes(64),), message_bytes)

    # --- simulate the unsigned bytes; the wallet must grow by Σ rent − fees
    lamports_before = _lamports(rpc, wallet)
    try:
        simulation = rpc.simulate_transaction(unsigned, sig_verify=False, accounts=(wallet,))
    except Exception as exc:
        return await refuse(f"simulation_unreadable:{type(exc).__name__}")
    if not simulation.ok:
        return await refuse(f"simulation_failed:{str(simulation.err)[:120]}")
    simulated_after = _simulated_lamports(simulation)
    if simulated_after is None:
        return await refuse("simulation_accounts_unreadable")
    delta = simulated_after - lamports_before
    if delta < expected_rent - fee_allowance:
        return await refuse(f"simulation_lamports_short:{delta}<{expected_rent}-{fee_allowance}")

    # --- sign once; the audit row with the signature is committed BEFORE the broadcast
    signature_bytes = signer.sign(message_bytes)
    signature = b58encode(signature_bytes)
    signed = serialize_transaction((signature_bytes,), message_bytes)
    await _audit(
        conn,
        level="info",
        event="close_atas_submitted",
        message=f"{reason}: submitted {len(accounts)} closes signature={signature}",
        data={**base, "signature": signature, "simulated_delta_lamports": delta},
    )
    try:
        relayed = rpc.send_transaction(signed)
    except Exception as exc:
        logger.error(
            "meme_close_atas_send_unknown", signature=signature, error_type=type(exc).__name__
        )
        return BatchResult("submitted", signature, 0, 0, expected_rent, "send_unknown")
    if relayed != signature:
        logger.warning("meme_close_atas_signature_mismatch", local=signature, rpc=relayed)

    # --- confirm; anything but a clean verdict leaves it submitted
    try:
        verdict = await _confirm(rpc, signature)
    except Exception as exc:
        logger.error(
            "meme_close_atas_confirm_unreadable",
            signature=signature,
            error_type=type(exc).__name__,
        )
        return BatchResult("submitted", signature, 0, 0, expected_rent, "confirm_unreadable")
    if verdict == "failed":
        await _audit(
            conn,
            level="error",
            event="close_atas_failed",
            message=f"{reason}: failed on chain signature={signature}",
            data={**base, "signature": signature},
        )
        return BatchResult("failed", signature, 0, 0, expected_rent, "failed_on_chain")
    if verdict != "confirmed":
        logger.warning("meme_close_atas_confirm_pending", signature=signature)
        return BatchResult("submitted", signature, 0, 0, expected_rent, "confirm_pending")
    recovered = await _measure(rpc, signature, wallet=wallet)
    if recovered is None:
        logger.warning("meme_close_atas_recovery_unmeasured", signature=signature)
        return BatchResult(
            "submitted", signature, 0, 0, expected_rent, "confirmed_recovery_unmeasured"
        )
    short = recovered < expected_rent - fee_allowance
    await _audit(
        conn,
        level="warning" if short else "info",
        event="close_atas_confirmed",
        message=(
            f"{reason}: closed {len(accounts)} accounts, recovered {recovered} lamports "
            f"signature={signature}"
        ),
        data={
            **base,
            "signature": signature,
            "n_closed": len(accounts),
            "lamports_recovered": recovered,
            "measure": "tx_meta",
            "recovered_below_expected": short,
        },
    )
    return BatchResult("confirmed", signature, len(accounts), recovered, expected_rent)


def _simulated_lamports(simulation: SimulationResult) -> int | None:
    accounts = simulation.accounts
    if len(accounts) != 1 or accounts[0] is None:
        return None
    try:
        return int(accounts[0]["lamports"])
    except (KeyError, TypeError, ValueError):
        return None


def classify_status(status: dict[str, Any] | None) -> str:
    """``confirmed`` | ``failed`` only once the chain has settled the signature
    at ``confirmed``/``finalized``; anything seen at ``processed`` (even an
    error) is still ``pending``."""
    if status is None or status.get("confirmationStatus") not in _SETTLED:
        return "pending"
    return "failed" if status.get("err") is not None else "confirmed"


async def _confirm(rpc: Rpc, signature: str) -> str:
    verdict = "pending"
    for _ in range(CONFIRM_ATTEMPTS):
        statuses = rpc.get_signature_statuses([signature])
        verdict = classify_status(statuses[0] if statuses else None)
        if verdict != "pending":
            break
        await asyncio.sleep(CONFIRM_INTERVAL_S)
    return verdict


def transaction_wallet_delta(payload: dict[str, Any] | None, *, wallet: str) -> int | None:
    """``postBalances[0] − preBalances[0]`` of a ``getTransaction`` payload
    whose first account key is the wallet; ``None`` for anything else."""
    if payload is None:
        return None
    try:
        keys = payload["transaction"]["message"]["accountKeys"]
        first = keys[0]["pubkey"] if isinstance(keys[0], dict) else keys[0]
        if first != wallet:
            return None
        meta = payload["meta"]
        if meta.get("err") is not None:
            return None
        return int(meta["postBalances"][0]) - int(meta["preBalances"][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


async def _measure(rpc: Rpc, signature: str, *, wallet: str) -> int | None:
    for attempt in range(TX_META_ATTEMPTS):
        try:
            delta = transaction_wallet_delta(rpc.get_transaction(signature), wallet=wallet)
        except Exception as exc:
            logger.warning("meme_close_atas_meta_unreadable", error_type=type(exc).__name__)
            delta = None
        if delta is not None:
            return delta
        if attempt + 1 < TX_META_ATTEMPTS:
            await asyncio.sleep(CONFIRM_INTERVAL_S)
    return None
