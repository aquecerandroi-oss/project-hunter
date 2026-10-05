"""Wave 0 of "seguir carteiras que ganham de verdade" — the small numeric helpers of the probe:
a counter-backed histogram, the Heaps'-law fit for distinct wallets, and the row-size estimate."""

from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any

from wallet_tape_probe_core import AMM, PUMP, Decoded

_PROG = {PUMP: "pump", AMM: "pAMM"}


class Hist:
    """Counter-backed histogram: bounded memory, exact percentiles on the quantised value."""

    def __init__(self, step: float = 1.0) -> None:
        self.step = step
        self.c: Counter[int] = Counter()
        self.n = 0

    def add(self, x: float) -> None:
        self.c[round(x / self.step)] += 1
        self.n += 1

    def pct(self, p: float) -> float | None:
        if not self.n:
            return None
        need = math.ceil(self.n * p / 100)
        seen = 0
        for key in sorted(self.c):
            seen += self.c[key]
            if seen >= need:
                return key * self.step
        return None

    def summary(self) -> dict[str, Any]:
        top = max(self.c) * self.step if self.c else None
        return {
            "n": self.n,
            "p50": self.pct(50),
            "p90": self.pct(90),
            "p99": self.pct(99),
            "max": top,
        }


def heaps_fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Least squares on log-log: distinct = k * events ** beta (Heaps' law). Returns (k, beta)."""
    xs = [math.log(n) for n, d in points if n > 0 and d > 0]
    ys = [math.log(d) for n, d in points if n > 0 and d > 0]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sum(
        (x - mx) ** 2 for x in xs
    )
    return math.exp(my - beta * mx), beta


_FIXED_COLUMNS = {
    "block_time": 8,
    "received_at": 8,
    "program": 2,
    "event_ordinal": 2,
    "venue": 2,
    "side": 1,
}


def row_estimates(row: dict[str, Any]) -> dict[str, int]:
    """Size of one ``meme_wallet_fills`` row as JSON (measured) and in Postgres (ESTIMATE by column
    type: 24 B tuple header; timestamptz/smallint/enum columns at their physical width, each ONCE;
    1 B varlena header per text; 8 B per bigint; three btree entries: pk, wallet+time, mint-or-pool+slot).
    Not a measured table: padding, TOAST, WAL and fillfactor are not in it."""
    json_bytes = len(json.dumps(row, separators=(",", ":")))
    heap = 24
    for key, value in row.items():
        if key in _FIXED_COLUMNS:
            heap += _FIXED_COLUMNS[key]
        elif isinstance(value, str):
            heap += 1 + len(value)
        else:
            heap += 8
    sig = len(str(row.get("signature", "")))
    wallet = len(str(row.get("wallet", "")))
    key = len(str(row.get("mint") or row.get("pool") or ""))
    indexes = (16 + 1 + sig + 4) + (16 + 1 + wallet + 8) + (16 + 1 + key + 8)
    return {
        "json_bytes": json_bytes,
        "pg_heap_bytes": heap,
        "pg_with_indexes_bytes": heap + 4 + indexes,
    }


def swap_row(program: str, slot: int, sig: str, ordinal: int, d: Decoded) -> dict[str, Any]:
    row: dict[str, Any] = {
        "block_time": d.event_ts, "slot": slot, "signature": sig, "program": _PROG[program],
        "event_ordinal": ordinal, "wallet": d.wallet or d.inferred_wallet,
        "mint" if program == PUMP else "pool": d.key or d.inferred_pool,
        "venue": _PROG[program], "side": d.side, "sol_lamports": d.sol_lamports,
        "token_amount": d.token_amount, "fee_lamports": d.fee_lamports,
    }  # fmt: skip
    for i, r in enumerate(d.reserves):
        row[f"r{i}"] = r
    row["received_at"] = "2026-10-05T18:30:00.123456+00:00"
    return row


def per_sec_summary(c: Counter[int]) -> dict[str, Any]:
    h = Hist()
    for count in c.values():
        h.add(count)
    return {"seconds_with_events": len(c), **h.summary()}
