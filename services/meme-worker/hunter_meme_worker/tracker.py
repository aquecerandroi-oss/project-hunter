"""The tracked set and the prioritiser — pure, no IO, no clock of its own.

The radar cannot watch ~40 000 new mints a day: the only free curve endpoint is
``frontend-api-v3.pump.fun`` at a **measured 60 requests per 60 s per IP**
(T4-MEME-RADAR.md §2, confirmed live in T4.1). So the collector keeps a *tracked
set* and the budget decides how much of it is polled each minute.

Membership, and every part of it is a declared choice:

- **younger than ``track_window_minutes``** (24 h by default) — the window the
  Mayhem agent itself lives in (A4.1b §2), and the window in which a curve either
  moves or dies;
- **or the Mayhem agent is ``active``/``paused``** — a paused agent is not a
  finished one, and dropping it would lose the transition H-P28 is about;
- **and the curve still moves**: a mint whose curve is complete or already
  migrated leaves the set, because its reserves are static and every request
  spent on it is a request not spent on a curve that is moving. It keeps its row
  and its history; it just stops costing budget.

Priority, and the starvation is declared rather than hidden: mints younger than
``young_minutes`` are polled first (that is where the curve moves fastest), and
inside each tier the **least recently polled** goes first, so the older tier is
served with whatever budget the young tier leaves. When the young tier alone
exceeds the budget the rest is genuinely skipped — and the collector writes that
as a ``meme_ingest_gaps`` row instead of leaving a silent hole, which is the whole
difference between a gap and a lie.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

ACTIVE_MAYHEM_STATES = frozenset({"active", "paused"})
"""``paused`` means liquidity is insufficient right now, not that the agent is
done (A4.1b §2) — so it keeps the mint in the set."""


@dataclass(frozen=True, slots=True)
class TrackedMint:
    """One mint the collector is watching, with everything the poller needs."""

    mint: str
    first_seen_at: datetime
    created_at: datetime | None = None
    bonding_curve: str | None = None
    mayhem_state: str | None = None
    initial_real_token_reserves: Decimal | None = None
    last_polled_at: datetime | None = None
    mcap_sol: Decimal | None = None
    complete: bool = False
    migrated: bool = False

    @property
    def age_anchor(self) -> datetime:
        """``created_at`` when we know it, else when we first saw the mint.

        Never a fabricated creation time: a mint discovered by its *migration*
        genuinely has no creation time (the PumpPortal migration frame carries
        none), and ranking it by ``first_seen_at`` says "as old as our knowledge
        of it" instead of claiming it was born when we noticed it.
        """
        return self.created_at or self.first_seen_at

    def is_trackable(self, now: datetime, window: timedelta) -> bool:
        if self.complete or self.migrated:
            return False
        if self.mayhem_state in ACTIVE_MAYHEM_STATES:
            return True
        return now - self.age_anchor <= window


@dataclass(frozen=True, slots=True)
class PollPlan:
    """What this cycle polls, and what it could not reach."""

    selected: tuple[str, ...]
    skipped: tuple[str, ...]

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


class MintTracker:
    """The tracked set. Deterministic, ordered, and cheap to reason about."""

    def __init__(self, *, window_minutes: int, cap: int, young_minutes: int = 30) -> None:
        self._window = timedelta(minutes=window_minutes)
        self._cap = cap
        self._young = timedelta(minutes=young_minutes)
        self._mints: dict[str, TrackedMint] = {}

    def __len__(self) -> int:
        return len(self._mints)

    def __contains__(self, mint: str) -> bool:
        return mint in self._mints

    def snapshot(self) -> tuple[TrackedMint, ...]:
        """Every tracked mint, newest first — the order the radar reads in."""
        return tuple(sorted(self._mints.values(), key=lambda m: m.age_anchor, reverse=True))

    def get(self, mint: str) -> TrackedMint | None:
        return self._mints.get(mint)

    def observe(self, candidate: TrackedMint) -> TrackedMint:
        """Add or merge. Known facts win over unknown ones, never the reverse.

        The same rule the schema enforces on ``meme_tokens``
        (``meme_tokens_identity_is_written_once``): a later, poorer observation —
        a migration frame with no creation time, a REST read with no bonding curve
        — may fill a hole and may never blank a value. Mutable state
        (``mayhem_state``, ``complete``, ``migrated``, ``mcap_sol``,
        ``last_polled_at``) is the opposite: the newest observation wins, because
        that is what "state" means.
        """
        existing = self._mints.get(candidate.mint)
        if existing is None:
            self._mints[candidate.mint] = candidate
            return candidate
        merged = dataclasses.replace(
            existing,
            created_at=existing.created_at or candidate.created_at,
            bonding_curve=existing.bonding_curve or candidate.bonding_curve,
            initial_real_token_reserves=(
                existing.initial_real_token_reserves
                if existing.initial_real_token_reserves is not None
                else candidate.initial_real_token_reserves
            ),
            first_seen_at=min(existing.first_seen_at, candidate.first_seen_at),
            mayhem_state=candidate.mayhem_state or existing.mayhem_state,
            complete=existing.complete or candidate.complete,
            migrated=existing.migrated or candidate.migrated,
            mcap_sol=candidate.mcap_sol if candidate.mcap_sol is not None else existing.mcap_sol,
            last_polled_at=candidate.last_polled_at or existing.last_polled_at,
        )
        self._mints[candidate.mint] = merged
        return merged

    def mark_polled(self, mint: str, at: datetime, *, mcap_sol: Decimal | None = None) -> None:
        current = self._mints.get(mint)
        if current is None:
            return
        self._mints[mint] = dataclasses.replace(
            current,
            last_polled_at=at,
            mcap_sol=mcap_sol if mcap_sol is not None else current.mcap_sol,
        )

    def prune(self, now: datetime) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Drop what left the window, then cap. Returns ``(aged_out, capped)``.

        Two return values, not one, because they are two different operator
        facts: a mint that aged out was watched for its whole eligible life, and a
        mint dropped by the cap **was not** — the second is the one that belongs in
        the gap ledger.
        """
        aged_out = tuple(
            sorted(
                mint
                for mint, tracked in self._mints.items()
                if not tracked.is_trackable(now, self._window)
            )
        )
        for mint in aged_out:
            del self._mints[mint]

        capped: tuple[str, ...] = ()
        if len(self._mints) > self._cap:
            ordered = self.snapshot()
            evicted = ordered[self._cap :]
            capped = tuple(sorted(m.mint for m in evicted))
            for mint in capped:
                del self._mints[mint]
        return aged_out, capped

    def plan(self, now: datetime, budget: int) -> PollPlan:
        """Pick up to ``budget`` mints: young tier first, least recently polled first."""
        if budget <= 0:
            return PollPlan(selected=(), skipped=tuple(sorted(self._mints)))
        young: list[TrackedMint] = []
        older: list[TrackedMint] = []
        for tracked in self._mints.values():
            (young if now - tracked.age_anchor <= self._young else older).append(tracked)
        ordered = _by_poll_debt(young) + _by_poll_debt(older)
        selected = tuple(tracked.mint for tracked in ordered[:budget])
        skipped = tuple(sorted(tracked.mint for tracked in ordered[budget:]))
        return PollPlan(selected=selected, skipped=skipped)

    def top_by_mcap(self, k: int) -> tuple[str, ...]:
        """The ``k`` largest tracked mints by last known market cap.

        Which is what the RPC reconciliation spends its ~10 req/s on: the REST
        mirror is best-effort and undocumented (T4-MEME-RADAR.md §2), so the
        mints where being wrong costs the most are the ones checked against the
        chain. A mint with no market cap yet sorts last — it has never been
        polled, so there is nothing to reconcile.
        """
        if k <= 0:
            return ()
        ranked = sorted(
            self._mints.values(),
            key=lambda m: (m.mcap_sol is not None, m.mcap_sol or Decimal(0), m.mint),
            reverse=True,
        )
        return tuple(m.mint for m in ranked[:k] if m.mcap_sol is not None)


def _by_poll_debt(mints: list[TrackedMint]) -> list[TrackedMint]:
    """Never polled first, then oldest poll first, then by mint for determinism."""
    return sorted(
        mints,
        key=lambda m: (
            m.last_polled_at is not None,
            m.last_polled_at or datetime.min.replace(tzinfo=m.first_seen_at.tzinfo),
            m.mint,
        ),
    )
