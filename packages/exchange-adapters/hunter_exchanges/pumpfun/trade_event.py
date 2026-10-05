"""``TradeEvent`` — the fill, as the chain reports it (``docs/RISK_ENGINE_MEME.md`` §9.6): where
it is read from a ``getTransaction`` result or a ``logsSubscribe`` notification.

The byte codec (``TradeEvent``, ``decode_trade_event``, the layouts of 2026-09-12 and
2026-10-02) lives in ``trade_event_codec.py`` — split out in T4.8e for the file-size budget and
re-exported here, which stays the import path.

**Reading logs without going blind (T4.8e).** A ``Program data:`` line that starts with the
``TradeEvent`` discriminator but cannot be decoded is *not* the same as a notification with no
``TradeEvent`` at all (a non-trade instruction on the same PDA): the first is lost data, the
second is normal. :func:`scan_trade_event_logs` reports both facts apart; the research lanes
mark a coverage gap on the first. :func:`trade_events_from_logs` is the events-only view.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from hunter_core.domain.types import utcnow
from hunter_exchanges.pumpfun.curve import raw_lamports_to_sol, raw_subunits_to_tokens
from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_exchanges.pumpfun.solana_codec import b58decode
from hunter_exchanges.pumpfun.trade_event_codec import (
    EVENT_CPI_TAG,
    LAYOUT_HOLDER_REWARDS,
    LAYOUT_PRE_HOLDER_REWARDS,
    LAYOUT_TRAILING_U64,
    TRADE_EVENT_DISCRIMINATOR,
    TradeEvent,
    decode_trade_event,
)

__all__ = [
    "EVENT_CPI_TAG",
    "LAYOUT_HOLDER_REWARDS",
    "LAYOUT_PRE_HOLDER_REWARDS",
    "LAYOUT_TRAILING_U64",
    "TRADE_EVENT_DISCRIMINATOR",
    "TradeEvent",
    "TradeLogScan",
    "decode_trade_event",
    "normalized_curve_trade",
    "scan_trade_event_logs",
    "trade_events_from_logs",
    "trade_events_from_transaction",
]

_LOG_PREFIX = "Program data: "


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _event_payloads(transaction: dict[str, Any], program_id: str) -> Iterable[bytes]:
    """Event bytes from the inner instructions first (structured), then from the logs
    (the same bytes, base64) when the RPC did not return inner instructions."""
    meta = _obj(transaction.get("meta"))
    message = _obj(_obj(transaction.get("transaction")).get("message"))
    keys: list[Any] = _seq(message.get("accountKeys"))
    loaded = _obj(meta.get("loadedAddresses"))
    keys += _seq(loaded.get("writable")) + _seq(loaded.get("readonly"))
    if meta.get("innerInstructions") is not None:
        # Structured path: the program that emitted each event is known.
        for inner in _seq(meta.get("innerInstructions")):
            for ix_any in _seq(_obj(inner).get("instructions")):
                ix = _obj(ix_any)
                index: Any = ix.get("programIdIndex")
                if not isinstance(index, int) or index >= len(keys) or keys[index] != program_id:
                    continue
                data = b58decode(str(ix.get("data", "")))
                if data[:8] == EVENT_CPI_TAG and data[8:16] == TRADE_EVENT_DISCRIMINATOR:
                    yield data
        return
    # Logs-only path (RPC without inner instructions): the discriminator is the
    # only attribution available, so ``program_id`` cannot be enforced here.
    for line in _seq(meta.get("logMessages")):
        if isinstance(line, str) and line.startswith(_LOG_PREFIX):
            try:
                data = base64.b64decode(line[len(_LOG_PREFIX) :], validate=True)
            except ValueError:
                continue
            if data[:8] == TRADE_EVENT_DISCRIMINATOR:
                yield data


def trade_events_from_transaction(
    transaction: dict[str, Any], *, program_id: str
) -> tuple[TradeEvent, ...]:
    """Every ``TradeEvent`` the pump program emitted in a ``getTransaction`` result
    (``encoding: json``). A failed transaction (``meta.err`` set) yields nothing: a
    reverted event is not a fill."""
    if _obj(transaction.get("meta")).get("err") is not None:
        return ()
    return tuple(decode_trade_event(raw) for raw in _event_payloads(transaction, program_id))


@dataclass(frozen=True, slots=True)
class TradeLogScan:
    """What one sequence of log lines held: the decoded events and, apart, the reasons of the
    ``TradeEvent``-shaped lines that could not be decoded (T4.8e)."""

    events: tuple[TradeEvent, ...]
    undecodable: tuple[str, ...] = ()
    """One reason per line that carried the ``TradeEvent`` discriminator and failed to decode
    (unknown trailing length, truncation, a boolean that is not 0/1...)."""

    @property
    def lost(self) -> bool:
        """``True`` when at least one trade was on the wire and could not be read — the
        caller's tape is incomplete and must say so (``mark_gap``), never carry on as if
        the notification had simply held no trade."""
        return bool(self.undecodable)


def scan_trade_event_logs(lines: Sequence[str]) -> TradeLogScan:
    """Every ``TradeEvent`` in one sequence of log lines (T4.52b-1) — typically
    a Solana RPC ``logsSubscribe`` notification's ``value.logs`` — with the lines that
    looked like one and could not be decoded reported apart (T4.8e).

    Unlike :func:`trade_events_from_transaction`'s logs-only fallback, this
    does **not** filter by ``program_id``: the caller already scoped the
    subscription to one mint's bonding-curve PDA via ``mentions``, so any
    ``TradeEvent``-shaped ``Program data:`` line here is that curve's. A notification
    with zero trade events (a non-trade instruction on the same PDA) is a normal, empty
    scan; a line that is not valid base64 or does not start with the discriminator is
    some other event and is not ours to count. Never raises.
    """
    events: list[TradeEvent] = []
    undecodable: list[str] = []
    for line in lines:
        if not line.startswith(_LOG_PREFIX):
            continue
        try:
            data = base64.b64decode(line[len(_LOG_PREFIX) :], validate=True)
        except ValueError:
            continue
        if data[:8] != TRADE_EVENT_DISCRIMINATOR:
            continue
        try:
            events.append(decode_trade_event(data))
        except ValueError as exc:
            undecodable.append(str(exc))
    return TradeLogScan(tuple(events), tuple(undecodable))


def trade_events_from_logs(lines: Sequence[str]) -> tuple[TradeEvent, ...]:
    """The events of :func:`scan_trade_event_logs`, nothing else: an undecodable line
    is dropped here **silently** — callers that feed a tape or an exit must use the scan."""
    return scan_trade_event_logs(lines).events


def normalized_curve_trade(
    event: TradeEvent, *, slot: int, signature: str, received_at: datetime | None = None
) -> NormalizedCurveTrade:
    """``TradeEvent`` + the envelope fields it doesn't carry itself (``slot``,
    ``signature`` — both live on the ``logsSubscribe`` notification, not the
    event body) -> :class:`NormalizedCurveTrade`. Reserves are converted to
    human units at this boundary, like every other model in ``models.py``;
    ``lamports`` is kept raw on purpose (see the model's own docstring).
    """
    now = received_at or utcnow()
    block_time = datetime.fromtimestamp(event.timestamp, tz=UTC) if event.timestamp > 0 else None
    return NormalizedCurveTrade(
        mint=event.mint,
        slot=slot,
        signature=signature,
        trader=event.user,
        side="buy" if event.is_buy else "sell",
        lamports=Decimal(event.sol_amount),
        token_amount=Decimal(event.token_amount),
        virtual_sol_reserves=raw_lamports_to_sol(event.virtual_sol_reserves),
        virtual_token_reserves=raw_subunits_to_tokens(event.virtual_token_reserves),
        real_sol_reserves=raw_lamports_to_sol(event.real_sol_reserves),
        real_token_reserves=raw_subunits_to_tokens(event.real_token_reserves),
        creator=event.creator,
        mayhem=event.mayhem_mode,
        block_time=block_time,
        received_at=now,
        observed_at=now,
    )
