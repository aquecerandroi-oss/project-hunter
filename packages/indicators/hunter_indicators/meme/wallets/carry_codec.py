"""JSON form of the carry (wave 1c-bis): what a night writes and the next one reads back.

Only to prove the carry is plain data that survives a restart bit for bit (the differential
tests resume from it); storage itself — tables, partitions, upserts of the changed rows — is the
database wave's (design §9.6). Integers stay integers (lamports, atoms, slots), instants are
ISO-8601 UTC, and an unknown lot cost stays ``null`` (never 0).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from types import MappingProxyType
from typing import Any

from hunter_indicators.meme.wallets.carry import Carry, Evidence, Flow, MintCarry
from hunter_indicators.meme.wallets.entities import Link
from hunter_indicators.meme.wallets.lots import Lot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Reserves

__all__ = ["carry_from_json", "carry_to_json"]

_VERSION = 1


def _t(value: datetime) -> str:
    return value.isoformat()


def _at(value: Any) -> datetime:
    return datetime.fromisoformat(str(value))


def _fill(f: Fill) -> dict[str, object]:
    r = f.reserves
    return {
        "signature": f.signature, "program": f.program, "ordinal": f.event_ordinal,
        "slot": f.slot, "block_time": _t(f.block_time), "received_at": _t(f.received_at),
        "wallet": f.wallet, "mint": f.mint, "venue": f.venue, "side": f.side,
        "sol": f.sol_lamports, "atoms": f.token_atoms, "fee": f.fee_lamports,
        "fee_bps": f.fee_bps, "lp_fee": f.lp_fee_lamports,
        "reserves": [r.venue, r.sol_lamports, r.token_atoms, r.real_sol_lamports, r.complete,
                     r.virtual_quote_lamports],
    }  # fmt: skip


def _unfill(d: Any) -> Fill:
    venue, sol, atoms, real, complete, virtual = d["reserves"]
    return Fill(
        d["signature"], d["program"], int(d["ordinal"]), int(d["slot"]), _at(d["block_time"]),
        _at(d["received_at"]), d["wallet"], d["mint"], d["venue"], d["side"], int(d["sol"]),
        int(d["atoms"]), int(d["fee"]), int(d["fee_bps"]),
        Reserves(venue, int(sol), int(atoms), None if real is None else int(real), bool(complete),
                 int(virtual)),
        int(d["lp_fee"]),
    )  # fmt: skip


def _lot(lot: Lot) -> list[object]:
    return [lot.owner, lot.mint, lot.atoms, lot.cost_lamports, lot.opened_slot, _t(lot.opened_at)]


def _unlot(d: Any) -> Lot:
    owner, mint, atoms, cost, slot, at = d
    return Lot(owner, mint, int(atoms), None if cost is None else int(cost), int(slot), _at(at))


def _create(c: CreateEvent | None) -> list[object] | None:
    if c is None:
        return None
    return [c.mint, c.creator, c.slot, _t(c.block_time), _t(c.received_at)]


def _uncreate(d: Any) -> CreateEvent | None:
    if d is None:
        return None
    mint, creator, slot, block_time, received_at = d
    return CreateEvent(mint, creator, int(slot), _at(block_time), _at(received_at))


def _mint(m: MintCarry) -> dict[str, object]:
    return {
        "mint": m.mint,
        "frontier": [_fill(f) for f in m.frontier],
        "lots": [_lot(lot) for lot in m.lots],
        "flows": [[f.wallet, f.bought_atoms, f.sold_atoms] for f in m.flows],
        "create": _create(m.create),
    }


def _unmint(d: Any) -> MintCarry:
    return MintCarry(
        d["mint"],
        tuple(_unfill(f) for f in d["frontier"]),
        tuple(_unlot(lot) for lot in d["lots"]),
        tuple(Flow(w, int(b), int(s)) for w, b, s in d["flows"]),
        _uncreate(d["create"]),
    )


def _evidence(d: Any) -> Evidence:
    return tuple((_at(known), str(mint)) for known, mint in d)


def carry_to_json(carry: Carry, mints: Iterable[MintCarry]) -> str:
    body = {
        "version": _VERSION,
        "boundary": _t(carry.boundary),
        "sealed_until": _t(carry.sealed_until),
        "window_days": carry.window_days,
        "max_slot": carry.max_slot,
        "weak_links": [[x.a, x.b, x.kind, _t(x.known_at), x.evidence] for x in carry.weak_links],
        "pending": [[a, b, [[_t(k), m] for k, m in ev]] for (a, b), ev in carry.pending.items()],
        "mints": [_mint(m) for m in mints],
    }
    return json.dumps(body, separators=(",", ":"))


def carry_from_json(text: str) -> tuple[Carry, tuple[MintCarry, ...]]:
    body: Any = json.loads(text)
    if body["version"] != _VERSION:
        raise ValueError(f"unknown carry version {body['version']}")
    links = tuple(Link(a, b, kind, _at(known), ev) for a, b, kind, known, ev in body["weak_links"])
    pending = {(str(a), str(b)): _evidence(ev) for a, b, ev in body["pending"]}
    carry = Carry(
        _at(body["boundary"]),
        _at(body["sealed_until"]),
        int(body["window_days"]),
        int(body["max_slot"]),
        links,
        MappingProxyType(pending),
    )
    return carry, tuple(_unmint(m) for m in body["mints"])
