"""§3.2's ``wallet_unrecognized_holdings``, fed from the chain (KB-0165).

Defect (27/09/2026, Astra's review of KB-0165): the engine's check 17 refuses
an entry when ``MemeWalletState.unrecognized_holdings`` is non-empty, but the
three builders (``entries``, ``launch_entries``, ``spot_entries``) always
passed ``()``. An LST from staking, an airdrop or the leftover of a failed sell
was neither seen nor counted — and converting SOL into it would have read as
the day's loss (``daily_loss = day_start + inflow − equity``).

What this module does, and only this:

- **reads** every token account the wallet owns (``ChainReader.token_holdings``:
  SPL Token and Token-2022, ``jsonParsed``, ``confirmed``), **then** the set the
  engine can account for from Postgres (``recognized_mints``) — chain first, so
  a mint the engine bought is already in a row when the scan saw it;
- **recognizes** the quote mints (WSOL, which Jupiter/PumpSwap wrap and close,
  and the treasury's USDC, §16) and every mint of an open position, an
  in-flight buy, or a position/buy that closed/confirmed within
  :data:`RECOGNIZED_GRACE_S` of the scan (the scan may predate the close);
- **names** every other mint whose total over its accounts is above dust (one
  millionth of a token, compared in integers) or whose balance is opaque
  (a Token-2022 confidential-transfer extension) — the engine refuses by name.

Recognition is by **mint**, not by quantity: extra units of a mint the engine
holds (a manual swap into the same token) are not detected here.

F1 (Everton, 28/09/2026): a mint named above that the owner excepted through the
audited CLI (``wallet_exceptions.py``, read in the recognized set's transaction)
leaves ``unrecognized`` and is reported apart (``excepted``) — never recognized.

Failure discipline (§8.1 "o padrão é rejeitar", §8.2 "RPC ilegível adia a
entrada"): a verdict is published only when both RPCs **and** the SELECT
answered, with **both** programs' slots past the last verdict's (a regressed or
frozen snapshot is not news); a failure never renews the
stamp; a verdict older than :data:`MAX_AGE_S` is worthless and the admission
**defers** (no row, the approval keeps its TTL and expires by name if the read
never comes back). One read at a time; a timed-out RPC thread blocks the next
read instead of piling up; after a failure every caller backs off (guardian F3,
:data:`BACKOFF_BASE_S`) — the RPC client is the exits' too. Exits never read any
of this.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.treasury_rules import USDC_MINT
from hunter_meme_executor.wallet_exceptions import active_exceptions, split_excepted

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_executor.chain import HoldingsRead, TokenHolding
    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.wallet_exceptions import HoldingException

# fmt: off
__all__ = [
    "BACKOFF_BASE_S", "BACKOFF_MAX_S", "DUST_INVERSE", "MAX_AGE_S", "QUOTE_MINTS", "RECOGNIZED_GRACE_S", "HoldingsVerdict",
    "WalletHoldingsReader", "admission_holdings", "holdings_once", "recognized_mints",
    "unrecognized_mints",
]
# fmt: on

logger = get_logger(__name__)

QUOTE_MINTS: Final = frozenset({WRAPPED_SOL_MINT, USDC_MINT})
DUST_INVERSE: Final = 1_000_000
"""A mint is dust when its total is ≤ 1/DUST_INVERSE of one token
(``atoms × 1 000 000 ≤ 10^decimals``). Price-blind by design: no price is read."""
RECOGNIZED_GRACE_S: Final = 60
MAX_AGE_S: Final = 30.0
BACKOFF_BASE_S: Final = 10.0
"""After ``n`` consecutive failures nobody reads for ``min(10 × 2^(n−1), 60)`` s:
the first costs nothing over the 10 s tick, a dead RPC gets one call a minute."""
BACKOFF_MAX_S: Final = 60.0
SAMPLE: Final = 5

_RECOGNIZED = text(
    "SELECT mint FROM meme_live_positions "
    "WHERE status = 'open' OR exit_at >= :since OR updated_at >= :since "
    "UNION SELECT p.mint FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id "
    "WHERE o.side = 'buy' AND (o.status IN ('admitted', 'simulated', 'submitted_unconfirmed') "
    "  OR (o.status = 'confirmed' AND o.settled_at >= :since)) "
    "UNION SELECT mint FROM spot_positions "
    "WHERE status = 'open' OR exit_at >= :since OR updated_at >= :since "
    "UNION SELECT mint FROM spot_orders "
    "WHERE side = 'buy' AND (status IN ('admitted', 'simulated', 'submitted_unconfirmed') "
    "  OR (status = 'confirmed' AND settled_at >= :since))"
)
"""Every lane the executor trades — pump.fun, PumpSwap (migrated) and launch
positions live in ``meme_live_positions``; ``spot/1`` in ``spot_positions``."""


async def recognized_mints(session: AsyncSession, *, since: datetime) -> frozenset[str]:
    rows = await session.execute(_RECOGNIZED, {"since": since})
    return frozenset(str(r[0]) for r in rows)


def unrecognized_mints(
    holdings: Iterable[TokenHolding], recognized: frozenset[str]
) -> tuple[str, ...]:
    """Mints outside ``recognized`` whose total is above dust, or opaque, sorted.
    Two accounts of one mint that disagree on decimals are named (never guessed)."""
    totals: dict[str, int] = {}
    decimals: dict[str, int] = {}
    named: set[str] = set()
    for h in holdings:
        if h.mint in recognized:
            continue
        if decimals.setdefault(h.mint, h.decimals) != h.decimals or h.opaque:
            named.add(h.mint)
        totals[h.mint] = totals.get(h.mint, 0) + h.amount
    for mint, atoms in totals.items():
        if atoms * DUST_INVERSE > 10 ** decimals[mint]:
            named.add(mint)
    return tuple(sorted(named))


@dataclass(frozen=True, slots=True)
class HoldingsVerdict:
    unrecognized: tuple[str, ...]
    accounts: int
    slots: tuple[int, ...]
    """Per program (SPL Token, Token-2022); each must **advance** for a read to be published."""
    read_at: datetime
    """When the chain was read — the verdict's age is measured from here."""
    excepted: tuple[HoldingException, ...] = ()
    """F1: the owner's audited exceptions that took a named mint off
    ``unrecognized`` — the rows themselves, so the admission records their ids."""

    def as_json(self) -> dict[str, Any]:
        """What an admission records (approved or not): the verdict it decided on."""
        return {
            "unrecognized": list(self.unrecognized[:SAMPLE]),
            "unrecognized_count": len(self.unrecognized),
            "excepted": [e.as_json() for e in self.excepted],
            "excepted_count": len(self.excepted),
            "accounts": self.accounts,
            "slots": list(self.slots),
            "read_at": self.read_at.isoformat(),
        }


class _Unavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _consume(future: asyncio.Future[Any]) -> None:
    """An abandoned read's outcome is retrieved (and dropped), never logged as lost."""
    if not future.cancelled():
        future.exception()


@dataclass(slots=True)
class WalletHoldingsReader:
    max_age_s: float = MAX_AGE_S
    last: HoldingsVerdict | None = None
    """The last **published** verdict; ``None`` until the first complete read."""
    failures: int = 0
    deferrals: int = 0
    last_error: str | None = None
    streak: int = 0
    """Consecutive failed reads; a published verdict resets it."""
    retry_at: datetime | None = None
    """Guardian F3: no read (tick or admission) before this; ``None`` after a success."""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    inflight: asyncio.Future[Any] | None = None

    def valid(self, now: datetime) -> HoldingsVerdict | None:
        last = self.last
        if last is None or (now - last.read_at).total_seconds() > self.max_age_s:
            return None
        return last

    def held(self, now: datetime) -> bool:
        """Guardian F3: after a failure nobody reads until ``retry_at``."""
        return self.retry_at is not None and now < self.retry_at

    async def refresh(self, ctx: ExecutorContext, *, force: bool) -> HoldingsVerdict | None:
        """``force`` (the tick) always reads unless backing off; otherwise a valid
        verdict is reused without I/O. The collector's own deadline
        (``wallet_holdings_timeout_s``, never the SOL balance's) covers the wait for
        the lock, both RPCs and the SELECT. Returns the verdict valid **now**
        (re-checked after the awaits, with the clock read then), or ``None``.
        Never raises."""
        if ctx.signer is None:
            return None
        now = utcnow()
        if not force and (young := self.valid(now)) is not None:
            return young
        if self.held(now):
            return self.valid(now)  # no I/O: the RPC client is the exits' too
        read = [False]
        try:
            await asyncio.wait_for(
                self._locked(ctx, ctx.signer.pubkey, force=force, read=read),
                timeout=ctx.config.wallet_holdings_timeout_s,
            )
        except Exception as exc:
            self.last_error = exc.reason if isinstance(exc, _Unavailable) else type(exc).__name__
            logger.warning("meme_wallet_holdings_read_failed", error=self.last_error)
            if read[0]:  # Astra: a waiter's deadline is not one more failed read
                self.failures, self.streak = self.failures + 1, self.streak + 1
                wait_s = min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** min(self.streak - 1, 6))
                self.retry_at = utcnow() + timedelta(seconds=wait_s)
        return self.valid(utcnow())

    async def _locked(
        self, ctx: ExecutorContext, pubkey: str, *, force: bool, read: list[bool]
    ) -> None:
        async with self.lock:
            now = utcnow()
            if not force and self.valid(now) is not None:
                return  # another caller published while this one waited
            if self.held(now):
                return  # a caller queued behind a failed read does not retry it
            read[0] = True  # from here a failure is this caller's, and backs everyone off
            verdict = await self._read(ctx, pubkey)
            last = self.last
            if last is not None and not all(
                new > old for new, old in zip(verdict.slots, last.slots, strict=True)
            ):
                # Astra: a regressed **or frozen** answer (a lagging RPC repeating an
                # old snapshot) must never get a fresh stamp.
                raise _Unavailable("slot_not_advanced")
            self.last, self.last_error, self.streak, self.retry_at = verdict, None, 0, None

    async def _read(self, ctx: ExecutorContext, pubkey: str) -> HoldingsVerdict:
        pending = self.inflight
        if pending is not None and not pending.done():
            raise _Unavailable("holdings_read_in_flight")
        future = asyncio.ensure_future(asyncio.to_thread(ctx.chain.token_holdings, pubkey))
        future.add_done_callback(_consume)
        self.inflight = future
        read: HoldingsRead = await asyncio.shield(future)
        since = read.observed_at - timedelta(seconds=RECOGNIZED_GRACE_S)
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            recognized = await recognized_mints(session, since=since)
            exceptions = await active_exceptions(session, wallet=pubkey)  # F1: same transaction
        named = unrecognized_mints(read.holdings, recognized | QUOTE_MINTS)
        unrecognized, excepted = split_excepted(named, read.holdings, exceptions)
        used = {e.mint: e for e in exceptions}
        return HoldingsVerdict(
            unrecognized=unrecognized,
            accounts=len(read.holdings),
            slots=read.slots,
            read_at=read.observed_at,
            excepted=tuple(used[mint] for mint in excepted),
        )

    def describe(self, now: datetime) -> dict[str, str]:
        """The heartbeat's fields: state, provenance, a five-mint sample and the count."""
        last = self.last
        state = "unread" if last is None else ("valid" if self.valid(now) else "stale")
        return {
            "wallet_holdings_state": state,
            "wallet_holdings_read_at": "" if last is None else last.read_at.isoformat(),
            "wallet_holdings_slots": "" if last is None else ",".join(map(str, last.slots)),
            "wallet_unrecognized_count": "" if last is None else str(len(last.unrecognized)),
            "wallet_unrecognized_mints": ""
            if last is None
            else ",".join(last.unrecognized[:SAMPLE]),
            "wallet_excepted_count": "" if last is None else str(len(last.excepted)),
            "wallet_excepted_mints": ""
            if last is None
            else ",".join(e.mint for e in last.excepted[:SAMPLE]),
            "wallet_holdings_failures": str(self.failures),
            "wallet_holdings_deferrals": str(self.deferrals),
            "wallet_holdings_error": self.last_error or "",
            "wallet_holdings_retry_at": "" if self.retry_at is None else self.retry_at.isoformat(),
        }


async def holdings_once(ctx: ExecutorContext) -> None:
    """The kill-switch tick's read (10 s), with or without a candidate."""
    await ctx.holdings.refresh(ctx, force=True)


async def admission_holdings(ctx: ExecutorContext) -> HoldingsVerdict | None:
    """The verdict an entry decides on, or ``None``: the caller **defers**."""
    verdict = await ctx.holdings.refresh(ctx, force=False)
    if verdict is None:
        ctx.holdings.deferrals += 1
        logger.warning(
            "meme_live_entry_deferred",
            reason="wallet_holdings_unavailable",
            error=ctx.holdings.last_error or "",
        )
    return verdict
