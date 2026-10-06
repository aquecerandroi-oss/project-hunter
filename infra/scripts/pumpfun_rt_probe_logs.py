"""pump.fun realtime latency probe (2026-10-06) — one ``logsSubscribe`` notification to the few facts the
comparison needs: the signature, the slot, whether the tx **creates** a coin, completes a curve, and which
mints its ``TradeEvent``s name. Reuses the committed decoders through ``wallet_tape_probe_core`` (no new
decoding logic). Pure: no IO, no clock."""

from __future__ import annotations

from typing import Any

from wallet_tape_probe_core import PUMP, decode_event, event_name, parse_logs

_CREATE_IX = frozenset({"Create", "CreateV2"})


def logs_fact(
    signature: str, slot: int, err: object, logs: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    facts = parse_logs(logs)
    names = [event_name(e.program, e.disc) for e in facts.events if e.program == PUMP]
    mints: list[str] = []
    for e in facts.events:
        if e.program == PUMP and event_name(e.program, e.disc) == "TradeEvent":
            got = decode_event(e)
            if got.ok and got.key and got.key not in mints:
                mints.append(got.key)
    create_ix = any(p == PUMP and n in _CREATE_IX for p, n in facts.instructions)
    return {
        "id": signature,
        "slot": slot,
        "err": err is not None,
        "create": "CreateEvent" in names or create_ix,
        "complete": "CompleteEvent" in names,
        "mints": mints,
    }
