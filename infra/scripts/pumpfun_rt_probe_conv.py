"""pump.fun realtime latency probe (2026-10-06) — wire message -> ``(kind, id, extra)``, no IO, no clock.

``id`` is the join key between sources: the transaction **signature** wherever the source carries one
(NATS ``tx``/``txSignature``, PumpPortal ``signature``, ``logsSubscribe`` signature) and the **mint** for the
board feeds (trenches), which carry no signature. The caller stamps the local arrival time ``t`` *before*
calling anything here, so parsing cost never leaks into a latency.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from pumpfun_rt_probe_logs import logs_fact
from pumpfun_rt_probe_nats import slot_of
from pumpfun_rt_probe_sel import BALANCE, LITE, PROCESSED

Conv = tuple[str, str, dict[str, Any]]
CREATION_SUBJECT = "unifiedCoinCreationEvent"


def as_obj(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def iso_to_epoch(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:  # a naive stamp would be read in the machine's zone: refuse it
        return None
    return parsed.astimezone(UTC).timestamp()


def conv_unified(subject: str, d: dict[str, Any]) -> Conv | None:
    if subject == CREATION_SUBJECT:
        tx = d.get("tx")
        if not isinstance(tx, str):
            return None
        return "create", tx, {
            "mint": d.get("mint"), "slot": slot_of(d.get("slot_index_id")),
            "bt": iso_to_epoch(d.get("created_timestamp")), "program": d.get("program"),
            "has_name": bool(d.get("name")), "creator": d.get("creator"),
        }  # fmt: skip
    kind = (
        "trade"
        if subject.startswith(PROCESSED + ".")
        else "lite"
        if subject.startswith(LITE + ".")
        else None
    )
    tx = d.get("tx")
    if kind is None or not isinstance(tx, str):
        return None
    return kind, tx, {
        "mint": d.get("mintAddress") or d.get("mint"), "slot": slot_of(d.get("slotIndexId")),
        "bt": iso_to_epoch(d.get("timestamp")), "user": d.get("userAddress"), "side": d.get("type"),
        "program": d.get("program"), "sol": d.get("amountSol"),
    }  # fmt: skip


def conv_core(subject: str, d: dict[str, Any]) -> Conv | None:
    tx = d.get("txSignature")
    if not subject.startswith(BALANCE + ".") or not isinstance(tx, str):
        return None
    return "balance", tx, {
        "wallet": d.get("walletAddress"), "mint": d.get("tokenMint"), "slot": d.get("slot"),
        "srv_ts": iso_to_epoch(d.get("timestamp")),
    }  # fmt: skip


def conv_pumpportal(d: dict[str, Any]) -> Conv | None:
    sig, tx_type = d.get("signature"), d.get("txType")
    if not isinstance(sig, str) or not isinstance(tx_type, str):
        return None  # the subscription acks carry only ``message``
    kind = "create" if tx_type == "create" else "migration"
    return kind, sig, {"mint": d.get("mint"), "pool": d.get("pool")}


def conv_trenches(board: str, msg: dict[str, Any]) -> list[Conv]:
    server_ts = msg.get("serverTs")
    st = server_ts / 1000 if isinstance(server_ts, (int, float)) else None
    if msg.get("type") == "snapshot":
        entries = msg.get("entries")
        return [
            (
                "snapshot",
                board,
                {"n": len(as_list(entries)), "server_ts": st},
            )
        ]
    out: list[Conv] = []
    for raw in as_list(msg.get("patches")):
        p = as_obj(raw)
        op, mint = p.get("op"), p.get("mint")
        if not isinstance(mint, str):
            continue
        fields = as_obj(p.get("fields"))
        if op == "add":
            out.append(("add", mint, {"server_ts": st, "idx": p.get("idx"), "entry": fields}))
        elif op == "remove":
            out.append(("remove", mint, {"server_ts": st}))
        elif op == "update" and "kol" in fields:
            out.append(("kol", mint, {"server_ts": st, "kol": fields["kol"]}))
    return out


def parse_block_time(body: object) -> tuple[int | None, str | None]:
    """``getBlockTime`` answer -> ``(value, None)`` or ``(None, why)``: a JSON-RPC ``error`` (the public
    endpoint answers HTTP 200 with ``{"error": {"code": 413, "message": "You have used your data
    allowance"}}`` once its allowance is gone) is a refusal to record, not a missing block."""
    obj = as_obj(body)
    if not obj:
        return None, "unreadable answer"
    err = as_obj(obj.get("error"))
    if err:
        return None, f"{err.get('code')}: {str(err.get('message'))[:120]}"
    result = obj.get("result")
    return (result, None) if isinstance(result, int) else (None, "no block time")


def conv_rpc_logs(msg: dict[str, Any]) -> dict[str, Any] | None:
    if msg.get("method") != "logsNotification":
        return None
    result = as_obj(as_obj(msg.get("params")).get("result"))
    value = as_obj(result.get("value"))
    sig, slot = value.get("signature"), as_obj(result.get("context")).get("slot")
    if not isinstance(sig, str) or not isinstance(slot, int):
        return None
    logs = [x for x in as_list(value.get("logs")) if isinstance(x, str)]
    return logs_fact(sig, slot, value.get("err"), logs)
