"""What every loop of the executor runs on: the config, the mode, the signer (or
none), the chain reader, the durable journal, the kill switch and the counters.

Built once by ``main.py``; every loop step receives it. The signer is the only
object in the process that can sign, and it is ``None`` whenever the live flag
is off — a paper executor has nothing to sign with, by construction.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_exchanges.jupiter import JupiterClient
from hunter_meme_executor.creator_flow import CreatorSoldMemory
from hunter_meme_executor.event_exits_stats import EventExitsStats
from hunter_meme_executor.launch_stats import LaunchStats
from hunter_meme_executor.treasury_inflow import TreasuryInflowReader

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.execution.meme.gates import MemeExecutionMode
    from hunter_core.execution.meme.signer import MemeSigner
    from hunter_meme_executor.chain import ChainReader
    from hunter_meme_executor.config import ExecutorConfig
    from hunter_meme_executor.journal_db import PostgresOrderJournal
    from hunter_meme_executor.kill_switch import KillSwitchReader
    from hunter_meme_executor.priority_fee import PriorityFeeReader
    from hunter_meme_executor.risk_read import RiskSource

HeartbeatWriter = "Callable[[dict[str, str]], Awaitable[None]]"


@dataclass(slots=True)
class ExecutorState:
    last_entries_tick_at: datetime | None = None
    last_exits_tick_at: datetime | None = None
    last_signature: str | None = None
    last_refusal: str | None = None
    entries_seen: int = 0
    entries_refused: int = 0
    entries_confirmed: int = 0
    exits_confirmed: int = 0
    exits_blocked: int = 0
    ata_closed: int = 0
    """T4.46: full sells whose landed fill confirmed an SPL Token ``CloseAccount``
    refund of the mint's ATA rent — the desk's count of rent actually recovered,
    not merely attempted."""
    rpc_errors: int = 0
    wallet_lamports: int | None = None
    wallet_read_at: datetime | None = None
    blocked_exits: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    program_idl_hash: str | None = None
    program_last_deploy_slot: int | None = None
    program_divergence: str | None = None
    """T4.8b: set when the chain's program identity differs from the fixtures' —
    every entry is refused ``program_upgraded`` while it is set."""
    auto_approved: int = 0
    """T4.28: proposals this process opened as live on its own (stage 1)."""
    auto_rejected: int = 0
    """T4.28: auto-opened proposals the admission then refused (marked ``rejected``)."""
    auto_skipped: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    """T4.28: why a ``proposed`` row was left to the human, by name."""
    gates_mtime_ns: int | None = None
    """T4.28d: the gates file's mtime as last seen (the cheap stat the reload
    compares); ``None`` until the boot primes it."""
    gates_mtime: datetime | None = None
    gates_reloaded_at: datetime | None = None
    """When the effective policy was last swapped by a runtime reload (never at boot)."""
    gates_invalid: str | None = None
    """T4.28d: the named refusal of the last gates file that failed to validate —
    the kill switch is latched ``gates_invalid:<reason>`` while it is set."""
    gates_deferred_failure: str | None = None
    """T4.28f: a **parse** failure (``gates_file_invalid``/``gates_file_missing``)
    seen on the last tick and not latched yet — the one tick of grace a
    non-atomic edit (``nano``) needs. The next tick either clears it (the file
    parses) or latches it."""
    gates_deferred_mtime_ns: int | None = None
    """The mtime the deferred failure was read at, for the log line."""
    risk_reads_on_demand: int = 0
    """T4.45: ``/in-memory-coin`` reads this process made itself because the
    admission needed a rug number the radar had not written yet."""
    risk_reads_on_demand_failed: int = 0
    """Of those, the ones that answered nothing usable (timeout, HTTP error, or a
    reading without ``bundled_share``). The admission refused by name each time -
    this counter is how the desk sees the endpoint degrading instead of guessing
    from a drop in entries."""
    risk_read_attempts: dict[str, datetime] = field(default_factory=lambda: dict[str, datetime]())
    """When this process last **attempted** an on-demand read per mint - failures
    included, which the persisted row cannot bound. Pruned to its own window."""
    pickup_lags: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    """T4.52a: ``received_at - proposal.proposed_at`` in seconds, one sample per
    live candidate ``entries_once`` sees for the first time — exactly what R55
    measured as "Proposal->Received". p50/max of this ride the heartbeat
    (``proposal_pickup_lag_s_p50``/``_max``, ``heartbeat.py``) so the same
    number can be re-read after the wake-up (``wake.py``) ships."""
    creator_sold_on_chain: CreatorSoldMemory = field(default_factory=CreatorSoldMemory)
    """T4.56: per mint, the instant a chain read showed the creator sold (30
    min, bounded). A later ``creator_sold = false`` from the lagging tape never
    re-opens a mint this process saw dumped — COVER, 17/09/2026."""
    treasury_last_swap_at: datetime | None = None
    """T4.54: when a treasury swap last reached ``confirmed``."""
    treasury_last_attempt_reason: str | None = None
    """T4.54: the last tick's outcome, published verbatim in the heartbeat —
    ``ok:<signature>``, a refusal reason, or ``""`` when the wallet is above
    the floor and nothing was attempted."""
    treasury_wallet_usdc: Decimal | None = None
    """T4.54: the USDC ATA balance as last read, for the heartbeat only."""
    resends_total: int = 0
    """T4.55: re-sends of already-signed bytes across every attempt of this
    process (``submit.py``'s confirmation loop) — same signature each time."""
    resend_errors_total: int = 0
    last_resends: int = 0
    """The re-send count of the last settled attempt."""
    last_priority_fee: dict[str, Any] | None = None
    """T4.55: the last ``PriorityFeeChoice.as_json`` — price, source, p75,
    floor, cap, samples, fee in SOL — as published in the heartbeat."""
    priority_fee_read_failures: int = 0
    """T4.55: sends that paid the floor because ``getRecentPrioritizationFees``
    failed or answered nothing (the desk's signal that the RPC is degrading)."""
    exit_locks: dict[str, asyncio.Lock] = field(default_factory=lambda: dict[str, asyncio.Lock]())
    """T4.63: one lock per open position (``exit_common.exit_lock``) — the tick
    and the event path never both sell it; pruned by the event runtime's sync."""


@dataclass(slots=True)
class ExecutorContext:
    config: ExecutorConfig
    mode: MemeExecutionMode
    signer: MemeSigner | None
    session_factory: async_sessionmaker[AsyncSession]
    chain: ChainReader
    journal: PostgresOrderJournal
    kill: KillSwitchReader
    heartbeat: Callable[[dict[str, str]], Awaitable[None]]
    loop: asyncio.AbstractEventLoop
    state: ExecutorState = field(default_factory=ExecutorState)
    risk_client: RiskSource | None = None
    """T4.45 - the pump.fun indexer client used **only** on the admission path,
    to read a mint's rug numbers when the radar's row has not landed. ``None``
    disables the on-demand read entirely and restores the T4.28g behaviour
    (wait, and refuse by name); no other behaviour depends on it."""
    wake_event: asyncio.Event = field(default_factory=asyncio.Event)
    """T4.52a: set by ``wake.ProposalWakeListener`` on every ``meme:proposals:wake``
    message; ``main.py`` hands this same event to the entries loop's ``forever(...,
    wake_event=...)`` so a fresh proposal wakes it instead of waiting for
    ``config.loop_s``. Never read directly by test code that does not also run
    the listener — a stray ``set()`` is harmless (the next tick just runs early)."""
    treasury_client: JupiterClient = field(default_factory=JupiterClient)
    """T4.54: the public Jupiter quote/swap client the treasury top-up drives.
    No key, no ``sendTransaction`` — it only ever returns an unsigned
    transaction (``hunter_meme_executor.treasury`` verifies, simulates, signs
    and sends). A short-lived ``httpx.Client`` per process; not explicitly
    closed at shutdown (a process exit reclaims the socket)."""
    priority_fees: PriorityFeeReader | None = None
    """T4.55: the bounded ``getRecentPrioritizationFees`` reader every send
    prices itself with (``send_path.priority_fee_for``). ``None`` keeps the
    configured static ``compute_unit_price_micro_lamports`` (tests)."""
    event_exits: EventExitsStats = field(default_factory=EventExitsStats)
    """T4.63: the counters of the event-driven exits (``event_exits.py``),
    published by the heartbeat whether or not the flag is on."""
    event_exits_wake: asyncio.Event = field(default_factory=asyncio.Event)
    """T4.63: set by the entries loop right after a fill opened a position, so
    the event runtime subscribes to its curve now instead of on its next 2 s sync."""
    treasury_inflow: TreasuryInflowReader = field(default_factory=TreasuryInflowReader)
    """T4.60: the SOL the treasury put into the wallet since the Sao Paulo day
    start (``meme_treasury_swaps``), cached 10 s, the last known value on a
    failed read — the input that keeps the daily-loss brake from being refilled
    by USDC top-ups (``daily_loss = day_start + inflow - equity``)."""
    launch: LaunchStats = field(default_factory=LaunchStats)
    """T4.67b: the launch lane's counters and its blockhash cache
    (``launch_stats.py``, ``launch_send.py``), published by the heartbeat in every mode."""
