"""The reads ``close_empty_token_accounts.py`` decides on, each failure a
named refusal (never "assume fine"): the kill switch, the in-flight buys,
the chain listing and the executor's recognized set — plus the run's
bookkeeping (:class:`RunLog`, :class:`SignTracker`). Split out of the CLI
for the 350-line budget; every side effect is a :class:`Deps` field so the
tests replace it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import close_empty_token_accounts_rules as rules
from meme_close_atas_plan import Plan, TokenAccountRow
from meme_close_atas_send import BatchResult, run_batch
from meme_spot_swap_kill import read_effective_kill_switch_state
from obsidian_note_gate import NoteProof

from hunter_core.domain.enums import KillSwitchState
from hunter_core.domain.types import utcnow
from hunter_meme_executor.wallet_holdings import RECOGNIZED_GRACE_S

# fmt: off
__all__ = [
    "Deps", "RunLog", "SignTracker", "balance_text", "db_counts", "in_flight_counts", "preflight",
    "rollback_quietly",
    "snapshot",
]
# fmt: on


@dataclass(frozen=True, slots=True)
class Deps:
    """Every side effect, injected (the tests replace each one)."""

    load_signer: Callable[[], Any]
    kill_state: Callable[[Any, Any], Awaitable[KillSwitchState]] = read_effective_kill_switch_state
    in_flight: Callable[[Any], Awaitable[dict[str, int]]] = rules.in_flight_buys
    recognized: Callable[..., Awaitable[frozenset[str]]] = rules.read_recognized
    list_accounts: Callable[[Any, str], tuple[TokenAccountRow, ...]] = rules.list_accounts
    run_batch: Callable[..., Awaitable[BatchResult]] = run_batch
    now: Callable[[], datetime] = utcnow
    repo_root: Path | None = None
    open_positions: Callable[[Any], Awaitable[dict[str, int]]] = rules.open_positions
    balance: Callable[[Any, str], int] = rules.wallet_balance


@dataclass(slots=True)
class RunLog:
    """What the ``…run`` audit row sums up, refusals and crashes included."""

    run_id: str
    wallet: str
    outcome: str = "started"
    kill_switch_state: str | None = None
    proof: NoteProof | None = None
    batch_in_progress: int | None = None
    """Set when the runner has **signed** a batch, cleared when its result is known."""
    batches: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])


class SignTracker:
    """The signer, handed to ``run_batch`` with one fact recorded: whether it
    was asked to sign. An exception before that is a named refusal (nothing
    can have left); after it, the batch may have been broadcast (Astra, diff
    review). ``signed`` is set **before** delegating — the conservative side."""

    def __init__(self, signer: Any) -> None:
        self._signer = signer
        self.signed = False

    @property
    def pubkey(self) -> str:
        return str(self._signer.pubkey)

    def sign(self, message: bytes, /) -> bytes:
        self.signed = True
        return self._signer.sign(message)


async def rollback_quietly(session: Any) -> None:
    """Ends an aborted transaction; its own failure never masks the caller's."""
    try:
        await session.rollback()
    except Exception:  # the refusal/audit that follows is the message that matters
        return


_rollback = rollback_quietly


async def snapshot(session: Any, rpc: Any, wallet: str, deps: Deps) -> Plan:
    """Chain first, then the recognized set, graced from **before** the chain
    read (Astra: a close that lands during a slow read stays inside the grace)."""
    since = deps.now() - timedelta(seconds=RECOGNIZED_GRACE_S)
    listed = deps.list_accounts(rpc, wallet)
    try:
        recognized = await deps.recognized(session, since=since)
        await session.commit()
    except Exception as exc:
        await _rollback(session)
        raise rules.Refused(f"db_read_failed:{type(exc).__name__}") from exc
    return rules.judge(listed, wallet=wallet, recognized=recognized)


async def in_flight_counts(session: Any, deps: Deps) -> dict[str, int]:
    return await db_counts(session, deps.in_flight)


async def db_counts(
    session: Any, read: Callable[[Any], Awaitable[dict[str, int]]]
) -> dict[str, int]:
    try:
        counts = await read(session)
        await session.commit()
    except Exception as exc:
        await _rollback(session)
        raise rules.Refused(f"db_read_failed:{type(exc).__name__}") from exc
    return counts


def balance_text(rpc: Any, wallet: str, deps: Deps) -> tuple[str, bool]:
    """The dry run's balance line and whether it was read; an unreadable
    balance is said, never invented (the caller exits 65 after the list)."""
    try:
        lamports = deps.balance(rpc, wallet)
    except Exception as exc:
        return f"wallet_balance_lamports=unreadable:{type(exc).__name__}", False
    sol = Decimal(lamports) / Decimal(1_000_000_000)
    return f"wallet_balance_lamports={lamports} wallet_balance_sol={sol:.9f}", True


async def preflight(session: Any, redis: Any, deps: Deps) -> KillSwitchState:
    """Only ``EMERGENCY`` (or an unreadable state — the reader already turns a
    dead Redis or a missing durable row into ``EMERGENCY``) refuses: rent
    recovery is not an entry, and ``TRADING_DISABLED`` is the safest moment
    for it (Astra, design review). Then: no meme/spot buy in flight."""
    try:
        state = await deps.kill_state(session, redis)
        await session.commit()
    except Exception as exc:
        await _rollback(session)
        raise rules.Refused(f"kill_switch_unreadable:{type(exc).__name__}") from exc
    if state == KillSwitchState.EMERGENCY:
        raise rules.Refused("kill_switch_emergency")
    counts = await in_flight_counts(session, deps)
    if sum(counts.values()):
        raise rules.Refused(f"buy_in_flight:meme={counts['meme']},spot={counts['spot']}")
    return state
