"""A followed wallet's :class:`LeaderEvent` from one ``getTransaction`` result (H-037) — pure.

**Whether it is a trade** is decided only by a swap event *attributed to the wallet*: the transaction
is read with the KB-0184 log readers (:func:`read_transaction_logs`: the curve ``TradeEvent`` and the
PumpSwap ``BuyEvent``/``SellEvent``, whose ``user`` is the wallet) and a swap whose ``wallet`` is not the
followed one proves nothing about it — a transfer into the wallet, a program merely named in the
accounts, or the curve's own balance moving are ``not_a_trade``. A transaction whose logs cannot be read
(missing, truncated, undecodable) is ``logs_unreadable``, never assumed to be "no trade".

**The numbers** of the event come from the chain's own balances, not from the decoder: the token delta
and ``position_after`` are the wallet's ``pre``/``postTokenBalances`` summed per mint (an account closed
by the sell is zero after); the SOL delta is the wallet's lamport change as observed (fee and rent
included — the quantity the NATS SOL leg reports). One event per mint: the transaction's net change,
which is the key ``(wallet, signature, mint)`` the copy lane de-duplicates on. The decoder only says
which mint, which side, and the reserves right after the trade (``reserves``, for the "ideal" price).

An event read from the chain is ``confirmed=True``, ``kind="swap"``, ``source="chain"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from hunter_exchanges.pumpfun.leader_events import LeaderEvent, PostReserves
from hunter_exchanges.pumpfun.program_logs import read_transaction_logs
from hunter_exchanges.pumpfun.swap_record import SwapRecord
from hunter_exchanges.pumpfun.wallet_balance import WSOL_MINT

__all__ = ["ChainRead", "leader_events_from_transaction"]


@dataclass(frozen=True, slots=True)
class ChainRead:
    events: tuple[LeaderEvent, ...]
    reason: str | None = None
    """``tx_failed`` | ``not_a_trade`` | ``sign_mismatch`` | ``logs_unreadable`` | ``mint_unresolved``
    (or a read failure named by the caller) when ``events`` is empty for a named cause."""
    reserves: dict[str, PostReserves] = field(default_factory=dict[str, PostReserves])
    """Per mint: the market's reserves right after the wallet's last swap in the transaction."""
    partial: bool = False
    """The logs were only partly readable (a truncated suffix, an undecodable event...): the events
    present are real, but another trade of the wallet may be hidden. The caller records a gap."""


def _obj(value: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def _held(meta: dict[str, Any], label: str, wallet: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for entry_any in _seq(meta.get(label)):
        entry = _obj(entry_any)
        if entry.get("owner") != wallet:
            continue
        try:
            atoms = int(str(_obj(entry.get("uiTokenAmount")).get("amount", "0")))
        except ValueError:
            continue
        mint = str(entry.get("mint", ""))
        out[mint] = out.get(mint, 0) + atoms
    return out


def _lamport_change(tx: dict[str, Any], wallet: str) -> int | None:
    meta = _obj(tx.get("meta"))
    message = _obj(_obj(tx.get("transaction")).get("message"))
    loaded = _obj(meta.get("loadedAddresses"))
    keys = [
        str(_obj(k).get("pubkey", "")) if isinstance(k, dict) else str(k)
        for k in _seq(message.get("accountKeys"))
        + _seq(loaded.get("writable"))
        + _seq(loaded.get("readonly"))
    ]
    try:
        i = keys.index(wallet)
        return int(_seq(meta.get("postBalances"))[i]) - int(_seq(meta.get("preBalances"))[i])
    except (ValueError, IndexError, TypeError):
        return None


def _traded_mint(swap: SwapRecord) -> str | None:
    """The token the swap traded: the curve's mint, or a pool's base mint when the quote is SOL."""
    if swap.venue == "curve":
        return swap.mint
    if swap.base_mint is None or swap.base_mint == WSOL_MINT or swap.quote_is_sol is not True:
        return None
    return swap.base_mint


def leader_events_from_transaction(
    tx: dict[str, Any],
    *,
    wallet: str,
    signature: str,
    first_seen_at: datetime,
    fields_complete_at: datetime,
) -> ChainRead:
    meta = _obj(tx.get("meta"))
    if meta.get("err") is not None:
        return ChainRead((), "tx_failed")
    try:
        read = read_transaction_logs(tx, received_at=first_seen_at)
    except ValueError:
        return ChainRead((), "logs_unreadable")
    mine = [s for s in read.swaps if s.wallet == wallet]
    if not mine:
        return ChainRead((), "logs_unreadable" if read.gap else "not_a_trade")
    lamports = _lamport_change(tx, wallet)
    if lamports is None:
        return ChainRead((), "not_a_trade")
    pre, post = _held(meta, "preTokenBalances", wallet), _held(meta, "postTokenBalances", wallet)
    raw_slot, raw_time = tx.get("slot"), tx.get("blockTime")
    slot = raw_slot if isinstance(raw_slot, int) and raw_slot >= 0 else mine[0].slot
    block_time = (
        datetime.fromtimestamp(raw_time, tz=UTC)
        if isinstance(raw_time, int) and raw_time > 0
        else None
    )
    by_mint: dict[str, list[SwapRecord]] = {}
    unresolved = 0
    for swap in mine:
        mint = _traded_mint(swap)
        if mint is None:
            unresolved += 1
        else:
            by_mint.setdefault(mint, []).append(swap)
    events: list[LeaderEvent] = []
    reserves: dict[str, PostReserves] = {}
    multi = len(by_mint) > 1
    partial = read.gap or unresolved > 0  # a hidden swap may share the SOL debit
    for mint in sorted(by_mint):
        delta = post.get(mint, 0) - pre.get(mint, 0)
        if delta == 0:
            continue
        sides = {s.side for s in by_mint[mint]}
        if len(sides) == 1 and sides != {"buy" if delta > 0 else "sell"}:
            return ChainRead((), "sign_mismatch")
        last = by_mint[mint][-1]
        reserves[mint] = PostReserves(
            venue=last.venue,
            sol_reserves=last.sol_reserves,
            token_reserves=last.token_reserves,
            virtual_quote_reserves=last.virtual_quote_reserves,
            real_sol_reserves=last.real_sol_reserves,
        )
        events.append(
            LeaderEvent(
                wallet=wallet,
                mint=mint,
                side="buy" if delta > 0 else "sell",
                token_delta_atoms=delta,
                sol_delta_lamports=None if multi or partial else lamports,
                position_after_atoms=post.get(mint, 0),
                signature=signature,
                slot=slot,
                block_time=block_time,
                first_seen_at=first_seen_at,
                fields_complete_at=max(fields_complete_at, first_seen_at),
                source="chain",
                confirmed=True,
                multi_mint=multi,
                kind="swap",
            )
        )
    if events:
        return ChainRead(tuple(events), None, reserves, partial=partial)
    return ChainRead((), "mint_unresolved" if unresolved else "not_a_trade")
