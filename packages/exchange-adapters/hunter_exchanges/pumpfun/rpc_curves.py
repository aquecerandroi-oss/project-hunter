"""The curve of every tracked mint in one read — ``getMultipleAccounts`` over the
``["bonding-curve", mint]`` PDAs, 100 accounts per call, decoded by the IDL
(``decode.py``), stamped with the slot's block time (T4.2f).

**Why a batch, and why the PDA.** The REST poll (``/coins/{mint}``, 60 requests
a minute) cannot photograph 130 tracked curves every minute — production on 12/09
folded 1 267 ``not_polled`` rows in 15 minutes for exactly that reason. The chain
can: one ``getMultipleAccounts`` of 100 curve accounts answered in 467 ms and
34,6 KB (``tests/fixtures/pumpfun/t42f_rpc_curves_batch1_raw.json``, slot
446436963), and the address of a curve is a pure function of its mint — the PDA
derived by ``tx.bonding_curve_address`` matched the REST mirror's own
``bonding_curve`` on 140 of 140 coins in that capture, so a mint discovered by a
board, with no PumpPortal frame and no ``bonding_curve`` on file, is read like
any other.

**``observed_at`` is the block time of the slot the read was served at**, not
the instant the bytes arrived: a ``finalized`` read lags the chain by ~11 s
(block time 13:07:47Z for a response received at 13:07:58Z), and a snapshot
that claimed the later instant would put a state a dozen seconds in the future
of when it was true. ``getBlockTime(slot)`` costs one call per distinct slot; when
it answers ``null`` (or the RPC errs), the reading keeps ``received_at`` as its
``observed_at`` and the batch counts it in ``block_time_missing`` — the row still
carries ``slot`` and ``commitment``, so the instant can be recovered later.

**Refusals are named, never numbers:** ``curve_not_found`` (no account, or one
not owned by the pump program — a coin of another launchpad, or a curve not yet
finalized), ``unsupported_quote`` (a pair quoted in something other than SOL —
23 of the 140 freshest coins of the capture: USDC, the ``pumpCmXq…`` token and
eleven ``Xs…`` mints; ``normalize.UnsupportedQuote``), ``curve_emptied`` (the
curve is ``complete`` and every reserve is zero: ``migrate`` moved it to the
pool — the chain's own migration signal, which the REST mirror never shows
because it keeps the pre-migration numbers), ``malformed`` (bytes the decoder
will not vouch for).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID, decode_bonding_curve_account
from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_exchanges.pumpfun.normalize import UnsupportedQuote, curve_state_from_rpc_account
from hunter_exchanges.pumpfun.tx import bonding_curve_address

__all__ = [
    "ACCOUNTS_PER_CALL",
    "CURVE_EMPTIED",
    "CURVE_NOT_FOUND",
    "MALFORMED",
    "UNSUPPORTED_QUOTE",
    "CurveBatch",
    "curve_addresses",
    "decode_curve_batch",
]

ACCOUNTS_PER_CALL = 100
"""``getMultipleAccounts`` takes up to 100 addresses; one curve account per mint."""
CURVE_NOT_FOUND = "curve_not_found"
UNSUPPORTED_QUOTE = "unsupported_quote"
CURVE_EMPTIED = "curve_emptied"
MALFORMED = "malformed"
FINALIZED = "finalized"


@dataclass(frozen=True, slots=True)
class CurveBatch:
    """One ``get_curve_states`` call: every reading, every refusal by name, and
    what the read cost."""

    states: dict[str, NormalizedCurveState] = field(default_factory=dict[str, NormalizedCurveState])
    refused: dict[str, str] = field(default_factory=dict[str, str])
    slots: tuple[int, ...] = ()
    """The slot each ``getMultipleAccounts`` was served at, in call order."""
    calls: int = 0
    """Every RPC call made, ``getBlockTime`` included — what ``used_60s`` counts."""
    block_time_missing: int = 0
    """Readings whose slot had no block time: ``observed_at = received_at`` there."""


def curve_addresses(mints: Sequence[str]) -> list[tuple[str, str]]:
    """``(mint, bonding_curve)`` for each mint — the PDA, never a guess."""
    return [(mint, bonding_curve_address(mint)) for mint in mints]


def _account_data(account: Any) -> tuple[str, str]:
    data = account["data"]
    if account.get("executable") is not False or data[1] != "base64":
        raise ValueError("invalid account encoding/type")
    return str(data[0]), str(account["owner"])


def decode_curve_batch(
    mints: Sequence[str],
    result: Any,
    *,
    block_time: datetime | None,
    received_at: datetime,
) -> tuple[dict[str, NormalizedCurveState], dict[str, str], int]:
    """One ``getMultipleAccounts`` result (for ``mints``, in order) into readings
    and named refusals. Returns ``(states, refused, slot)``; raises
    :class:`MalformedMessage` when the response as a whole is not one."""
    try:
        slot = result["context"]["slot"]
        if type(slot) is not int or slot < 0:
            raise ValueError("invalid slot")
        raw_values: Any = result["value"]
        if not isinstance(raw_values, list) or len(cast(list[Any], raw_values)) != len(mints):
            raise ValueError("account count")
        values = cast(list[Any], raw_values)
    except (KeyError, TypeError, ValueError):
        raise MalformedMessage("invalid getMultipleAccounts response", exchange="pumpfun") from None
    states: dict[str, NormalizedCurveState] = {}
    refused: dict[str, str] = {}
    observed_at = block_time or received_at
    for mint, account in zip(mints, values, strict=True):
        if account is None:
            refused[mint] = CURVE_NOT_FOUND
            continue
        try:
            data, owner = _account_data(account)
            if owner != PUMP_PROGRAM_ID:
                # The PDA exists but is not a curve (another program's coin, or
                # a funded address): there is no bonding curve for this mint.
                refused[mint] = CURVE_NOT_FOUND
                continue
            decoded = decode_bonding_curve_account(data, owner=owner)
            if decoded.virtual_token_reserves == 0 and decoded.complete:
                refused[mint] = CURVE_EMPTIED
                continue
            state = curve_state_from_rpc_account(mint, decoded)
        except UnsupportedQuote:
            refused[mint] = UNSUPPORTED_QUOTE
            continue
        except (MalformedMessage, KeyError, IndexError, TypeError, ValueError):
            refused[mint] = MALFORMED
            continue
        states[mint] = state.model_copy(
            update={
                "slot": slot,
                "commitment": FINALIZED,
                "observed_at": observed_at,
                "received_at": received_at,
            }
        )
    return states, refused, slot
