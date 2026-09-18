"""T4.55 — the priority fee a real transaction pays, chosen per send instead of
fixed at 10 000 µL/CU (0,000004 SOL with 400 000 CU).

R56 §2.1: three of ~23 real sends in 30 h never landed, every one at the
moment the same curve was being fought over (PS: ~5 SOL/s of buys and sells;
FAMILY: 42 buys/23 sells in the minute). A minimum-priority transaction a busy
leader drops disappears without an error. The fix is not a bigger number, it
is the *right* number, bounded:

- **p75** of ``getRecentPrioritizationFees`` for the pump program **and the
  mint's bonding curve** (the RPC answers per slot the fee needed to lock all
  of those accounts — contention on *this* curve, not the cluster's average),
  over the most recent ``window_slots`` slots;
- **floored** at ``MEME_PRIORITY_FEE_FLOOR_MICRO_LAMPORTS`` (default 100 000 —
  0,00004 SOL with 400 000 CU, 0,08 % of a 0,05 SOL trade);
- **capped** by total cost: ``MEME_PRIORITY_FEE_MAX_SOL`` (default 0,002 SOL,
  the doctrine's ``max_priority_fee_sol``) spread over the compute-unit limit;
- **the floor whenever the read fails** (timeout, error, malformed) — never a
  wait on the entry path, never a guess above the floor.

The read is bounded three ways: at most one RPC call per ``min_read_interval_s``
(one tick), ``read_timeout_s`` (1,5 s) per call, and a ``cache_ttl_s`` (10 s)
per address set. The choice is logged with every number that made it
(``PriorityFeeChoice.as_json``) into the order's ``intent`` and the heartbeat.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, cast

__all__ = [
    "DEFAULT_FLOOR_MICRO_LAMPORTS",
    "DEFAULT_MAX_SOL",
    "DEFAULT_WINDOW_SLOTS",
    "PriorityFeeChoice",
    "PriorityFeeReader",
    "cap_micro_lamports",
    "choose_priority_fee",
    "percentile_nearest_rank",
]

DEFAULT_FLOOR_MICRO_LAMPORTS = 100_000
DEFAULT_MAX_SOL = Decimal("0.002")
DEFAULT_WINDOW_SLOTS = 50
"""≈ 20 s of slots: recent enough to see the fight for *this* curve, wide enough
that one slot does not set the price."""
DEFAULT_PERCENTILE = 75
LAMPORTS_PER_SOL = 1_000_000_000
MICRO = 1_000_000


def cap_micro_lamports(max_sol: Decimal, compute_unit_limit: int) -> int:
    """The per-CU price at which the whole ``compute_unit_limit`` costs ``max_sol``."""
    if compute_unit_limit <= 0:
        raise ValueError("compute_unit_limit must be positive")
    return int(max_sol * LAMPORTS_PER_SOL * MICRO // compute_unit_limit)


def percentile_nearest_rank(samples: Sequence[int], percentile: int) -> int:
    ordered = sorted(samples)
    if not ordered:
        raise ValueError("no samples")
    rank = -(-percentile * len(ordered) // 100)  # ceil
    return ordered[max(0, min(len(ordered), rank) - 1)]


@dataclass(frozen=True, slots=True)
class PriorityFeeChoice:
    micro_lamports: int
    source: str
    """``p75`` | ``floor`` | ``cap`` | ``floor:read_failed`` | ``floor:no_samples``
    | ``floor:throttled`` | ``static`` — which bound (or failure) set the price."""
    p75_micro_lamports: int | None
    floor_micro_lamports: int
    cap_micro_lamports: int
    samples: int

    @classmethod
    def static(cls, micro_lamports: int) -> PriorityFeeChoice:
        """The pre-T4.55 fixed price (a context without a reader — tests)."""
        return cls(micro_lamports, "static", None, micro_lamports, micro_lamports, 0)

    def fee_sol(self, compute_unit_limit: int) -> Decimal:
        lamports = compute_unit_limit * self.micro_lamports // MICRO
        return Decimal(lamports) / Decimal(LAMPORTS_PER_SOL)

    def as_json(self, compute_unit_limit: int) -> dict[str, Any]:
        return {
            "micro_lamports": self.micro_lamports,
            "source": self.source,
            "p75_micro_lamports": self.p75_micro_lamports,
            "floor_micro_lamports": self.floor_micro_lamports,
            "cap_micro_lamports": self.cap_micro_lamports,
            "samples": self.samples,
            "fee_sol": str(self.fee_sol(compute_unit_limit)),
        }


def choose_priority_fee(
    samples: Sequence[int] | None,
    *,
    floor: int,
    cap: int,
    percentile: int = DEFAULT_PERCENTILE,
    failure: str = "read_failed",
) -> PriorityFeeChoice:
    """Pure: ``min(max(p75, floor), cap)`` with the winning bound named. ``None``
    samples is a failed read; an empty list is a read that saw nothing."""
    if samples is None:
        p75, source = None, f"floor:{failure}"
    elif not samples:
        p75, source = None, "floor:no_samples"
    else:
        p75 = percentile_nearest_rank(samples, percentile)
        source = "p75"
    chosen = floor if p75 is None else max(p75, floor)
    if p75 is not None and chosen == floor and p75 <= floor:
        source = "floor"
    if chosen >= cap:
        chosen, source = cap, "cap"
    return PriorityFeeChoice(
        chosen, source, p75, floor, cap, 0 if samples is None else len(samples)
    )


class _RpcCall(Protocol):
    def call(self, method: str, params: list[Any]) -> Any: ...


class PriorityFeeReader:
    """Bounded ``getRecentPrioritizationFees`` with the selection above."""

    def __init__(
        self,
        rpc: _RpcCall,
        *,
        floor: int = DEFAULT_FLOOR_MICRO_LAMPORTS,
        max_sol: Decimal = DEFAULT_MAX_SOL,
        window_slots: int = DEFAULT_WINDOW_SLOTS,
        cache_ttl_s: float = 10.0,
        read_timeout_s: float = 1.5,
        min_read_interval_s: float = 1.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rpc = rpc
        self._floor = floor
        self._max_sol = max_sol
        self._window = window_slots
        self._ttl = cache_ttl_s
        self._timeout = read_timeout_s
        self._min_interval = min_read_interval_s
        self._monotonic = monotonic
        self._cache: dict[tuple[str, ...], tuple[float, list[int]]] = {}
        self._last_read_at: float | None = None
        self.last_error: str | None = None
        self.last_choice: PriorityFeeChoice | None = None
        self.reads: int = 0
        self.read_failures: int = 0

    @property
    def floor(self) -> int:
        return self._floor

    @property
    def max_sol(self) -> Decimal:
        return self._max_sol

    async def choose(
        self, addresses: Sequence[str], *, compute_unit_limit: int
    ) -> PriorityFeeChoice:
        cap = cap_micro_lamports(self._max_sol, compute_unit_limit)
        key = tuple(addresses)
        now = self._monotonic()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] < self._ttl:
            choice = choose_priority_fee(cached[1], floor=self._floor, cap=cap)
        elif self._last_read_at is not None and now - self._last_read_at < self._min_interval:
            choice = choose_priority_fee(None, floor=self._floor, cap=cap, failure="throttled")
        else:
            samples = await self._read(key)
            if samples is not None:
                self._cache[key] = (now, samples)
            choice = choose_priority_fee(samples, floor=self._floor, cap=cap)
        self.last_choice = choice
        return choice

    async def _read(self, key: tuple[str, ...]) -> list[int] | None:
        self._last_read_at = self._monotonic()
        self.reads += 1
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(self._rpc.call, "getRecentPrioritizationFees", [list(key)]),
                timeout=self._timeout,
            )
            samples = _samples(raw, self._window)
        except Exception as exc:
            self.read_failures += 1
            self.last_error = type(exc).__name__
            return None
        self.last_error = None
        return samples


def _samples(raw: Any, window_slots: int) -> list[int]:
    """The ``prioritizationFee`` of the ``window_slots`` most recent slots."""
    if not isinstance(raw, list):
        raise ValueError("getRecentPrioritizationFees did not return a list")
    by_slot: list[tuple[int, int]] = []
    for row in cast(list[Any], raw):
        if not isinstance(row, dict):
            continue
        entry = cast(dict[str, Any], row)
        by_slot.append((int(str(entry["slot"])), int(str(entry["prioritizationFee"]))))
    by_slot.sort()
    return [fee for _slot, fee in by_slot[-window_slots:]]
