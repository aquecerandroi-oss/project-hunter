"""Recompose a wallet's trades in an interval from chain history (H-037, the copy lane's recomposition hook).

The lane asks this after a coverage gap, to learn what a leader did while the source was not looking:
``recompose(wallet, start, end) -> Recomposition``. The answer is **complete or explicitly not**:

* signatures are listed newest first (``getSignaturesForAddress``, pages of 100) until one is older than
  ``start`` or the history ends; the listing is capped at :data:`SIGNATURE_CAP` (1 000). Reaching the cap
  while still inside the interval is ``signature_cap`` — never silently truncated;
* every signature inside ``[start, end)`` is fetched (bounded concurrency) and read with the same
  attributed-swap rule as the live fallback (:func:`leader_events_from_transaction`): buys, sells and
  position-decreasing transfers, ``confirmed=True``, ``source="chain"``;
* anything that could hide a trade makes it incomplete with a named reason: ``list_failed``,
  ``tx_not_found:<n>``, ``logs_partial:<n>``, ``tx_unreadable:<n>``, ``rpc_refused`` (the node said no:
  fetching stops at once, no loop).

``first_seen_at``/``fields_complete_at`` of the events are the recomposition time (when WE learned it);
``block_time`` is the chain's. Pure of IO except the two injected callables.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.leader_events import LeaderEvent
from hunter_exchanges.pumpfun.leader_source_chain_derive import leader_events_from_transaction
from hunter_exchanges.pumpfun.leader_source_rpc_guard import RpcRefused
from hunter_exchanges.pumpfun.leader_source_wallets import validate_wallets
from hunter_exchanges.pumpfun.rpc_wallet import SignatureInfo

logger = get_logger(__name__)

SIGNATURE_CAP = 1000
PAGE = 100
CONCURRENCY = 8

__all__ = ["SIGNATURE_CAP", "Recomposition", "recompose"]

ListSignatures = Callable[[str, str | None, int, str | None], Awaitable[Sequence[SignatureInfo]]]
FetchTx = Callable[[str], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True, slots=True)
class Recomposition:
    wallet: str
    start: datetime
    end: datetime
    events: tuple[LeaderEvent, ...]
    """Oldest first (slot, signature, mint); only events whose ``block_time`` is in ``[start, end)``."""
    positions_after: dict[str, int]
    """Per mint: the position after the newest event of the interval (absent = no event for the mint)."""
    complete: bool
    reasons: tuple[str, ...]
    """Why it is not complete (empty when it is)."""
    signatures_seen: int
    """Signatures listed (the one that proved the start was reached included)."""


def _inside(when: datetime | None, start: datetime, end: datetime) -> bool:
    return when is None or start <= when < end  # unknown time: fetch it, the transaction decides


async def _list(
    wallet: str, start: datetime, end: datetime, lister: ListSignatures, cap: int
) -> tuple[list[SignatureInfo], int, list[str]]:
    """The signatures of the interval, newest first; ``(inside, seen, reasons)``."""
    inside: list[SignatureInfo] = []
    seen = 0
    cursor: str | None = None
    reasons: list[str] = []
    while seen < cap:
        try:
            page = await lister(wallet, None, min(PAGE, cap - seen), cursor)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("leader_recompose_list_failed", error=type(exc).__name__)
            reasons.append("list_failed")
            break
        seen += len(page)
        inside += [s for s in page if not s.failed and _inside(s.block_time, start, end)]
        oldest = page[-1].block_time if page else None
        if len(page) < min(PAGE, cap - seen + len(page)) or not page:
            break  # the history ended
        if oldest is not None and oldest < start:
            break  # reached the start of the interval
        cursor = page[-1].signature
    else:
        last = inside[-1].block_time if inside else None
        if last is None or last >= start:
            reasons.append("signature_cap")
    return inside, seen, reasons


async def recompose(
    wallet: str,
    start: datetime,
    end: datetime,
    *,
    list_signatures: ListSignatures,
    fetch_tx: FetchTx,
    cap: int = SIGNATURE_CAP,
    concurrency: int = CONCURRENCY,
    wall: Callable[[], datetime] = utcnow,
) -> Recomposition:
    validate_wallets([wallet])
    for name, value in (("start", start), ("end", end)):
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:  # type: ignore[union-attr]
            raise ValueError(f"{name} must be UTC-aware")
    if end <= start:
        raise ValueError("the interval must end after it starts (start < end, no empty interval)")
    if cap < 1:
        raise ValueError("cap must be at least 1")
    inside, seen, reasons = await _list(wallet, start, end, list_signatures, cap)
    now = wall()
    sem = asyncio.Semaphore(max(1, concurrency))
    refused = asyncio.Event()
    counts = {"tx_not_found": 0, "logs_partial": 0, "tx_unreadable": 0}
    events: list[LeaderEvent] = []

    async def one(info: SignatureInfo) -> None:
        async with sem:
            if refused.is_set():
                return
            try:
                tx = await fetch_tx(info.signature)
            except asyncio.CancelledError:
                raise
            except (RpcRefused, RateLimited):
                refused.set()
                return
            except Exception as exc:
                logger.warning("leader_recompose_fetch_failed", error=type(exc).__name__)
                counts["tx_unreadable"] += 1
                return
        if tx is None:
            counts["tx_not_found"] += 1
            return
        read = leader_events_from_transaction(
            tx, wallet=wallet, signature=info.signature, first_seen_at=now, fields_complete_at=now
        )
        if read.partial:
            counts["logs_partial"] += 1
        if not read.events and read.reason in (
            "logs_unreadable",
            "mint_unresolved",
            "sign_mismatch",
            "balances_unreadable",
        ):
            counts["tx_unreadable"] += 1
        events.extend(e for e in read.events if _inside(e.block_time, start, end))

    await asyncio.gather(*(one(info) for info in inside))
    if refused.is_set():
        reasons.append("rpc_refused")
    reasons += [f"{name}:{n}" for name, n in counts.items() if n]
    # oldest first: the slot, then the LISTING order (newest first there, so reversed) — a signature is
    # not a clock, and the final position is the newest transaction's
    listed = {info.signature: i for i, info in enumerate(inside)}
    events.sort(key=lambda e: (e.slot, -listed.get(e.signature, 0), e.mint))
    positions = {e.mint: e.position_after_atoms for e in events}  # oldest first: the newest wins
    return Recomposition(
        wallet=wallet,
        start=start,
        end=end,
        events=tuple(events),
        positions_after=positions,
        complete=not reasons,
        reasons=tuple(reasons),
        signatures_seen=seen,
    )
