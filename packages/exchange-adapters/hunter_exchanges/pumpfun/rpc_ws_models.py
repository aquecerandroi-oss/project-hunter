"""Typed shapes for :class:`hunter_exchanges.pumpfun.rpc_ws.SolanaWsClient`
(T4.52b-1) — transport-level only, no pump.fun domain knowledge (that lives
in ``trade_event.py``/``models.py``): one dataclass per Solana JSON-RPC
subscription notification this package uses (``logsSubscribe``,
``accountSubscribe``, ``slotSubscribe``), plus the client's connection state
and its bookkeeping for a subscription that must survive a reconnect.

Mirrors ``ws.py``'s ``ConnectionState`` in spirit (counters an
``ingestion_gaps`` caller reads) without reusing it: PumpPortal's client is a
fixed two-subscription connection; this one multiplexes an arbitrary,
caller-managed set that changes at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from hunter_exchanges.base import MalformedMessage

__all__ = [
    "AccountNotification",
    "ConnectionState",
    "LogsNotification",
    "Notification",
    "SlotNotification",
    "SubscriptionSpec",
    "parse_account_result",
    "parse_logs_result",
    "parse_notification_envelope",
    "parse_slot_result",
    "store_subscription",
]


@dataclass(frozen=True, slots=True)
class LogsNotification:
    """``logsNotification`` — one transaction mentioning a subscribed address.

    ``subscription_id`` is the caller's own *logical* id (stable across a
    reconnect), never the server's ``subscription`` number, which is
    reassigned every connection."""

    subscription_id: int
    kind: Literal["logs"]
    slot: int
    signature: str
    err: object | None
    logs: tuple[str, ...]
    received_at: datetime


@dataclass(frozen=True, slots=True)
class AccountNotification:
    """``accountNotification`` — the account's full state as of ``slot``."""

    subscription_id: int
    kind: Literal["account"]
    slot: int
    data_base64: str
    encoding: str
    owner: str
    lamports: int
    received_at: datetime


@dataclass(frozen=True, slots=True)
class SlotNotification:
    """``slotNotification`` — the only wall-clock proxy available without
    ``getBlockTime``: ``slot * 0.4s`` (plan-T4.52b.md §3) approximates the lag
    between a subscribed event's slot and now."""

    subscription_id: int
    kind: Literal["slot"]
    slot: int
    parent: int
    root: int
    received_at: datetime


Notification = LogsNotification | AccountNotification | SlotNotification


@dataclass(slots=True)
class SubscriptionSpec:
    """What ``subscribe_*`` asked for, kept so a reconnect can resubscribe the
    whole set under the caller-stable ``logical_id`` even though the server
    hands out a brand new ``subscription`` number every connection."""

    logical_id: int
    method: str
    unsubscribe_method: str
    params: list[object]
    kind: Literal["logs", "account", "slot"]


@dataclass(slots=True)
class ConnectionState:
    """This client's single-connection, multi-subscription analogue of
    ``ws.py``'s ``ConnectionState``."""

    ws_state: str = "disconnected"
    reconnects: int = 0
    messages: int = 0
    dropped: int = 0
    malformed: int = 0


def store_subscription(
    spec: SubscriptionSpec,
    server_id: Any,
    specs: dict[int, SubscriptionSpec],
    server_id_of: dict[int, int],
    logical_of_server: dict[int, int],
) -> None:
    """Record a subscribe response's server-assigned id under ``spec``'s
    stable logical id, in all three of ``SolanaWsClient``'s maps at once."""
    if not isinstance(server_id, int) or isinstance(server_id, bool):
        raise MalformedMessage(
            f"{spec.method} did not return an integer subscription id: {server_id!r}",
            exchange="solana",
        )
    specs[spec.logical_id] = spec
    server_id_of[spec.logical_id] = server_id
    logical_of_server[server_id] = spec.logical_id


def parse_notification_envelope(payload: dict[str, Any]) -> tuple[str, dict[str, Any], int]:
    """The parts every notification frame shares: ``method``, ``params.result``,
    ``params.subscription`` (the server-assigned id) — validated once so
    ``rpc_ws.py``'s ``_parse_frame`` only has to dispatch on ``method``."""
    method, params = payload.get("method"), payload.get("params")
    if (
        not isinstance(method, str)
        or not method.endswith("Notification")
        or not isinstance(params, dict)
    ):
        raise MalformedMessage("solana ws frame has an unknown shape", exchange="solana")
    params = cast(dict[str, Any], params)
    server_id = params.get("subscription")
    if not isinstance(server_id, int) or isinstance(server_id, bool):
        raise MalformedMessage("solana ws notification missing subscription id", exchange="solana")
    result = params.get("result")
    if not isinstance(result, dict):
        raise MalformedMessage("solana ws notification missing result", exchange="solana")
    return method, cast(dict[str, Any], result), server_id


def parse_logs_result(logical_id: int, result: dict[str, Any], now: datetime) -> LogsNotification:
    """Body of a ``logsNotification`` -> :class:`LogsNotification`. Raises
    :class:`MalformedMessage` for anything that isn't the documented shape."""
    context, value = result.get("context"), result.get("value")
    if not isinstance(context, dict) or not isinstance(value, dict):
        raise MalformedMessage("logsNotification missing context/value", exchange="solana")
    context, value = cast(dict[str, Any], context), cast(dict[str, Any], value)
    slot, signature, logs = context.get("slot"), value.get("signature"), value.get("logs")
    if not isinstance(slot, int) or not isinstance(signature, str) or not isinstance(logs, list):
        raise MalformedMessage("logsNotification has an unexpected shape", exchange="solana")
    return LogsNotification(
        subscription_id=logical_id,
        kind="logs",
        slot=slot,
        signature=signature,
        err=value.get("err"),
        logs=tuple(str(line) for line in cast(list[Any], logs)),
        received_at=now,
    )


def parse_account_result(
    logical_id: int, result: dict[str, Any], now: datetime
) -> AccountNotification:
    """Body of an ``accountNotification`` -> :class:`AccountNotification`."""
    context, value = result.get("context"), result.get("value")
    if not isinstance(context, dict) or not isinstance(value, dict):
        raise MalformedMessage("accountNotification missing context/value", exchange="solana")
    context, value = cast(dict[str, Any], context), cast(dict[str, Any], value)
    slot, data = context.get("slot"), value.get("data")
    if (
        not isinstance(slot, int)
        or not isinstance(data, list)
        or not data
        or not isinstance(data[0], str)
    ):
        raise MalformedMessage("accountNotification has an unexpected shape", exchange="solana")
    data = cast(list[Any], data)
    return AccountNotification(
        subscription_id=logical_id,
        kind="account",
        slot=slot,
        data_base64=data[0],
        encoding=str(data[1]) if len(data) > 1 else "base64",
        owner=str(value.get("owner", "")),
        lamports=int(value.get("lamports", 0)),
        received_at=now,
    )


def parse_slot_result(logical_id: int, result: dict[str, Any], now: datetime) -> SlotNotification:
    """Body of a ``slotNotification`` -> :class:`SlotNotification`."""
    slot, parent, root = result.get("slot"), result.get("parent"), result.get("root")
    if not isinstance(slot, int) or not isinstance(parent, int) or not isinstance(root, int):
        raise MalformedMessage("slotNotification has an unexpected shape", exchange="solana")
    return SlotNotification(
        subscription_id=logical_id,
        kind="slot",
        slot=slot,
        parent=parent,
        root=root,
        received_at=now,
    )
