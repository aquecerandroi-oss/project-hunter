"""Wave 0 of "seguir carteiras que ganham de verdade" — the pure half of the program-wide probe:
how one ``logsSubscribe`` notification's log lines become events (no IO, no clock).

What it does and does not claim (docs/design/seguir-carteiras-lucrativas.md §2):

* ``Program data:`` lines are attributed by the **invoke stack the log narrates** to the program
  that emitted them (``Program X invoke [n]`` ... ``Program X success|failed``), never by the
  subscription they arrived on: a tx that touches both programs is delivered on both.
* The identity of an event is ``(signature, program, ordinal)`` where the ordinal counts the
  event lines of that program inside the transaction.
* Decoding uses the **committed** decoders: ``decode_trade_event`` (T4.8e, tail included) for the
  pump ``TradeEvent`` and ``decode_sell_event`` (T4.8e) for the PumpSwap ``SellEvent``. The
  PumpSwap ``BuyEvent`` has no decoder yet (wave 1a): it is **counted raw**, and its wallet/pool
  are read at offsets inferred from the ``SellEvent`` layout (13 ``u64`` after the timestamp, then
  ``pool``, ``user``) — an *inference* checked only against three real events, reported under its
  own field and used for the wallet count alone, never for money.
"""

from __future__ import annotations

import base64
import re
import struct
from collections import Counter
from dataclasses import dataclass
from typing import Any, Final, cast

from wallet_tape_probe_names import AMM_EVENTS, PUMP_EVENTS

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.solana_codec import b58decode, b58encode
from hunter_exchanges.pumpfun.trade_event import EVENT_CPI_TAG, TradeEvent, decode_trade_event
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import SellEvent, decode_sell_event

PUMP: Final = PUMP_PROGRAM_ID
AMM: Final = PUMPSWAP_PROGRAM_ID

_DATA = "Program data: "
_IX = "Program log: Instruction: "
_INVOKE = re.compile(r"^Program (\w+) invoke \[(\d+)\]$")
_RETURN = re.compile(r"^Program (\w+) (?:success|failed)")


# Discriminators read from the programs' own IDLs (.claude/state/tmp/pump_*_idl_*.json, 2026-09).
_NAMES: Final[dict[tuple[str, str], str]] = {
    **{(PUMP, k): v for k, v in PUMP_EVENTS.items()},
    **{(AMM, k): v for k, v in AMM_EVENTS.items()},
}
LIQUIDITY_EVENTS: Final = frozenset({"DepositEvent", "WithdrawEvent", "CreatePoolEvent"})
SWAP_INSTRUCTIONS: Final = frozenset({"Buy", "Sell", "BuyExactQuoteIn", "SellExactBaseIn"})
LIQUIDITY_INSTRUCTIONS: Final = frozenset({"Deposit", "Withdraw", "CreatePool"})
_BUY_EVENT_POOL_OFFSET: Final = 8 + 8 + 13 * 8  # disc + timestamp + 13 u64 (SellEvent analogue)


@dataclass(frozen=True, slots=True)
class LogEvent:
    program: str
    ordinal: int
    disc: bytes
    payload: bytes


@dataclass(frozen=True, slots=True)
class NotifFacts:
    invoked: frozenset[str]
    truncated: bool
    events: tuple[LogEvent, ...]
    instructions: tuple[tuple[str, str], ...]
    foreign_data: dict[str, int]
    bad_b64: int


@dataclass(frozen=True, slots=True)
class Decoded:
    name: str
    kind: str  # swap | create | liquidity | other
    ok: bool | None  # True decoded, False failed, None not attempted (no committed decoder)
    reason: str | None = None
    side: str | None = None
    wallet: str | None = None  # from a committed decoder only
    key: str | None = None  # mint (pump) or pool (PumpSwap)
    sol_lamports: int | None = None
    token_amount: int | None = None
    fee_lamports: int | None = None
    event_ts: int | None = None
    layout: str | None = None
    reserves: tuple[int, ...] = ()
    inferred_wallet: str | None = None  # BuyEvent only: offset inference, not a decoder
    inferred_pool: str | None = None
    quote_unverified: bool = False
    """PumpSwap sells: the log line has no accounts, so the pool's quote mint is unknown and
    ``sol_lamports`` is atoms of the QUOTE token (lamports only when it is WSOL). Wave 1b found WSOL-base
    pools, whose quote leg is another token, to be a large share of the sells."""


def event_name(program: str, disc: bytes) -> str:
    return _NAMES.get((program, disc.hex()), f"unknown:{disc.hex()}")


def parse_logs(logs: list[str] | tuple[str, ...]) -> NotifFacts:
    """Walk the log lines once; never raises."""
    stack: list[str] = []
    invoked: set[str] = set()
    events: list[LogEvent] = []
    instructions: list[tuple[str, str]] = []
    foreign: dict[str, int] = {}
    ordinals: dict[str, int] = {}
    truncated = False
    bad = 0
    for line in logs:
        if line == "Log truncated":
            truncated = True
        elif line.startswith(_DATA):
            top = stack[-1] if stack else ""
            try:
                payload = base64.b64decode(line[len(_DATA) :], validate=True)
            except ValueError:
                bad += 1
                continue
            if top in (PUMP, AMM) and len(payload) >= 8:
                n = ordinals.get(top, 0)
                ordinals[top] = n + 1
                events.append(LogEvent(top, n, payload[:8], payload))
            else:
                foreign[top or "?"] = foreign.get(top or "?", 0) + 1
        elif line.startswith(_IX):
            if stack:
                instructions.append((stack[-1], line[len(_IX) :]))
        elif m := _INVOKE.match(line):
            del stack[int(m.group(2)) - 1 :]
            stack.append(m.group(1))
            invoked.add(m.group(1))
        elif _RETURN.match(line) and stack:
            stack.pop()
    return NotifFacts(
        frozenset(invoked), truncated, tuple(events), tuple(instructions), foreign, bad
    )


def _from_trade(t: TradeEvent) -> Decoded:
    return Decoded(
        "TradeEvent", "swap", True,
        side="buy" if t.is_buy else "sell", wallet=t.user, key=t.mint,
        sol_lamports=t.sol_amount, token_amount=t.token_amount,
        fee_lamports=t.fee + t.creator_fee + t.cashback, event_ts=t.timestamp, layout=t.layout,
        reserves=(t.virtual_sol_reserves, t.virtual_token_reserves, t.real_sol_reserves,
                  t.real_token_reserves),
    )  # fmt: skip


def _from_sell(s: SellEvent) -> Decoded:
    return Decoded(
        "SellEvent", "swap", True,
        side="sell", wallet=s.user, key=s.pool, sol_lamports=s.net_proceeds,
        token_amount=s.base_amount_in,
        fee_lamports=s.lp_fee + s.protocol_fee + s.coin_creator_fee + s.cashback,
        event_ts=s.timestamp, layout=s.layout,
        reserves=(s.pool_base_token_reserves, s.pool_quote_token_reserves),
        quote_unverified=True,
    )  # fmt: skip


def decode_event(event: LogEvent) -> Decoded:
    """Decode with the committed decoders; anything else is reported raw, never guessed."""
    name = event_name(event.program, event.disc)
    try:
        if name == "TradeEvent":
            return _from_trade(decode_trade_event(event.payload))
        if name == "SellEvent":
            return _from_sell(decode_sell_event(event.payload))
    except (ValueError, struct.error) as exc:
        return Decoded(name, "swap", False, reason=str(exc)[:120])
    if name == "BuyEvent":
        off = _BUY_EVENT_POOL_OFFSET
        ts = struct.unpack("<q", event.payload[8:16])[0] if len(event.payload) >= 16 else None
        pool = wallet = None
        if len(event.payload) >= off + 64:
            pool = b58encode(event.payload[off : off + 32])
            wallet = b58encode(event.payload[off + 32 : off + 64])
        return Decoded(
            name, "swap", None, reason="no_decoder_raw_count_only", side="buy", key=None,
            event_ts=ts, inferred_wallet=wallet, inferred_pool=pool,
        )  # fmt: skip
    if name == "CreateEvent":
        return Decoded(name, "create", None, reason="no_decoder_raw_count_only")
    if name in LIQUIDITY_EVENTS:
        return Decoded(name, "liquidity", None, reason="no_decoder_raw_count_only")
    return Decoded(name, "other", None, reason="not_a_wallet_event")


def pubkey_index(known: set[str]) -> dict[bytes, str]:
    return {b58decode(k): k for k in known}


def find_in_index(payload: bytes, index: dict[bytes, str]) -> set[str]:
    """Which indexed pubkeys occur in ``payload`` at ANY byte offset. Used for the liquidity
    events, whose layout has no committed decoder: the pool is recognised, not parsed."""
    return {
        index[payload[i : i + 32]] for i in range(len(payload) - 31) if payload[i : i + 32] in index
    }


def find_known_pubkeys(payload: bytes, known: set[str]) -> set[str]:
    return find_in_index(payload, pubkey_index(known))


_PROG_LABEL: Final = {PUMP: "pump", AMM: "pAMM"}


def log_event_counts(facts: NotifFacts) -> Counter[str]:
    return Counter(
        f"{_PROG_LABEL[e.program]}.{event_name(e.program, e.disc)}" for e in facts.events
    )


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def inner_event_counts(tx: dict[str, Any]) -> Counter[str]:
    """The same count taken from a ``getTransaction`` result's inner instructions (the self-CPI
    ``emit_cpi`` data: event tag + discriminator + body) — what the live sampler compares to the logs."""
    meta = _obj(tx.get("meta"))
    keys: list[Any] = _seq(_obj(_obj(tx.get("transaction")).get("message")).get("accountKeys"))
    loaded = _obj(meta.get("loadedAddresses"))
    keys += _seq(loaded.get("writable")) + _seq(loaded.get("readonly"))
    out: Counter[str] = Counter()
    for inner in _seq(meta.get("innerInstructions")):
        for ix_any in _seq(_obj(inner).get("instructions")):
            ix = _obj(ix_any)
            idx: Any = ix.get("programIdIndex")
            if not isinstance(idx, int) or idx >= len(keys) or keys[idx] not in _PROG_LABEL:
                continue
            data = b58decode(str(ix.get("data", "")))
            if data[:8] == EVENT_CPI_TAG and len(data) >= 16:
                out[f"{_PROG_LABEL[keys[idx]]}.{event_name(keys[idx], data[8:16])}"] += 1
    return out


def block_view(block: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """A ``getBlock`` (``transactionDetails: full``) seen per program: the transactions that MENTION it
    (account keys + address-lookup-table addresses: the ``logsSubscribe mentions`` filter) as
    ``(signature, success)``, the successful ones counted, and the events the program emitted in them
    read from the block's own logs — the websocket-independent truth about the chain's real rate."""
    out: dict[str, dict[str, Any]] = {
        p: {"mentions": [], "success_txs": 0, "events": {}} for p in (PUMP, AMM)
    }
    for tx_any in _seq(block.get("transactions")):
        tx = _obj(tx_any)
        message = _obj(_obj(tx.get("transaction")).get("message"))
        meta = _obj(tx.get("meta"))
        loaded = _obj(meta.get("loadedAddresses"))
        keys = set(_seq(message.get("accountKeys")))
        keys |= set(_seq(loaded.get("writable"))) | set(_seq(loaded.get("readonly")))
        sigs = _seq(_obj(tx.get("transaction")).get("signatures"))
        if not sigs:
            continue
        ok = meta.get("err") is None
        for program in (PUMP, AMM):
            if program not in keys:
                continue
            row = out[program]
            row["mentions"].append((str(sigs[0]), ok))
            if not ok:
                continue
            row["success_txs"] += 1
            for event in parse_logs([str(x) for x in _seq(meta.get("logMessages"))]).events:
                if event.program == program:
                    name = event_name(event.program, event.disc)
                    row["events"][name] = row["events"].get(name, 0) + 1
    return out


def block_mentions(block: dict[str, Any]) -> dict[str, list[tuple[str, bool]]]:
    return {p: v["mentions"] for p, v in block_view(block).items()}


def coverage(
    mentions: dict[str, list[tuple[str, bool]]], received: dict[str, set[str]]
) -> dict[str, dict[str, Any]]:
    """Of the block's mentions, how many does ``received[program]`` (the signatures the websocket has
    delivered for that slot, AT THE MOMENT of the call) hold. Failed transactions are counted apart:
    the filter delivers them too. Judge the same block again later: late is not lost."""
    out: dict[str, dict[str, Any]] = {}
    for program, got in received.items():
        row: dict[str, Any] = {
            "txs": 0, "received": 0, "missed": 0, "missed_failed": 0, "missed_sigs": [],
        }  # fmt: skip
        for sig, ok in mentions.get(program, []):
            row["txs"] += 1
            if sig in got:
                row["received"] += 1
                continue
            row["missed"] += 1
            row["missed_failed"] += not ok
            if len(row["missed_sigs"]) < 20:
                row["missed_sigs"].append(sig)
        out[program] = row
    return out


def audit_block(block: dict[str, Any], received: dict[str, set[str]]) -> dict[str, dict[str, Any]]:
    """``coverage`` plus the block's truth (``success_txs``, ``events``) in one call."""
    view = block_view(block)
    out = coverage({p: v["mentions"] for p, v in view.items()}, received)
    for program, row in out.items():
        row["success_txs"] = view[program]["success_txs"]
        row["events"] = view[program]["events"]
    return out
