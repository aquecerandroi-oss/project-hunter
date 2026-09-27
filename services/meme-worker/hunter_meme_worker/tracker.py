"""The tracked set and the prioritiser — pure, no IO, no clock of its own.

The radar cannot watch ~40 000 new mints a day: the only free curve endpoint is
``frontend-api-v3.pump.fun`` at a **measured 60 requests per 60 s per IP**
(T4-MEME-RADAR.md §2, confirmed live in T4.1). So the collector keeps a *tracked
set* and the budget decides how much of it is polled each minute.

Membership, and every part of it is a declared choice: younger than
``track_window_minutes`` (24 h by default, the Mayhem agent's own window) or
with an ``active``/``paused`` Mayhem agent (a paused agent is not a finished
one); and the curve still moves — a finished or migrated curve leaves the set
after **one final read** (T4.2c: ``final_read_pending`` guards the poll that
stamps ``completed_at``, then it stops costing budget); and the quote is
native SOL (``quote_unsupported`` drops a USDC-quoted curve at once).

Priority, and the starvation is declared rather than hidden. Tiers, in order:
an open paper bet, a final read of a finished curve, the site's ``graduating``
board, its ``new`` board, the young tier (``young_minutes``), the rest —
least recently polled first inside each. What the budget cannot reach is
written as a ``meme_ingest_gaps`` row, never a silent hole.

**Since T4.2f the chain photographs every tracked curve once a minute**
(``chain.py``), so :meth:`MintTracker.plan` with ``chain_covered=True``
selects only what the REST mirror alone still teaches
(:meth:`MintTracker.needs_rest`); everything else is the chain's.

**Pinned, since T4.16b, is a membership fact stronger than any of the above.**
``prune``'s cap once evicted a mint with an open bet in 10–15 minutes, at
roughly one discovery every few seconds (five ``rug_no_snapshot`` closes on
12/09). :meth:`MintTracker.pin`/:meth:`unpin` name mints — an open bet, an
open live position or a pending proposal — that :meth:`prune` never drops for
the window or the cap: the cap narrows to ``cap − |pinned|`` (never below
:data:`MIN_EFFECTIVE_CAP`). Priority is untouched.

**I1/I2 (EXP-M26) add a second, separate budget** (``tracker_mature.py``):
:class:`PinnedMints` and ``prune``'s ``mature_top_k``, neither narrowing the
cap above.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_meme_worker.tracker_mature import MatureReport, PinnedMints, mature_report
from hunter_meme_worker.tracker_types import ACTIVE_MAYHEM_STATES, PollPlan, TrackedMint

__all__ = [
    "ACTIVE_MAYHEM_STATES",
    "MAYHEM_REFRESH",
    "MIN_EFFECTIVE_CAP",
    "REST_SOURCE",
    "TIER_FINAL_READ",
    "TIER_GRADUATING",
    "TIER_NEW",
    "TIER_OPEN_BET",
    "TIER_REST",
    "TIER_YOUNG",
    "MintTracker",
    "PollPlan",
    "TrackedMint",
]

TIER_OPEN_BET = 0
TIER_FINAL_READ = 1
TIER_GRADUATING = 2
TIER_NEW = 3
TIER_YOUNG = 4
TIER_REST = 5

REST_SOURCE = "pumpfun_rest"
MAYHEM_REFRESH = timedelta(minutes=5)
"""How often an ``active``/``paused`` agent's state is re-read from the mirror
when the chain carries the curve (``MEME_REST_MAYHEM_REFRESH_S``)."""

MIN_EFFECTIVE_CAP = 20
"""``prune``'s cap over the *un*-pinned mints never drops below this, however
many are pinned (T4.16b's brief): the radar still needs room to discover."""

EMPTY_MATURE_REPORT = MatureReport(kept=(), eligible=(), ranked_out=(), stale_mcap=())
"""Before :meth:`MintTracker.prune` ever ran once (I1)."""


class MintTracker:
    """The tracked set. Deterministic, ordered, and cheap to reason about."""

    def __init__(self, *, window_minutes: int, cap: int, young_minutes: int = 30) -> None:
        self._window = timedelta(minutes=window_minutes)
        self._cap = cap
        self._young = timedelta(minutes=young_minutes)
        self._mints: dict[str, TrackedMint] = {}
        # T4.16b/I2 (EXP-M26): the two pinned sets — ``PinnedMints``'s own
        # docstring (``tracker_mature.py``) says why they narrow the cap differently.
        self._pins = PinnedMints()
        # I1: :attr:`last_mature_report`, stamped by :meth:`prune` before its own
        # eviction — a later recompute would zero out ranked_out/stale_mcap.
        self._last_mature_report = EMPTY_MATURE_REPORT

    def __len__(self) -> int:
        return len(self._mints)

    def __contains__(self, mint: str) -> bool:
        return mint in self._mints

    @property
    def pinned(self) -> frozenset[str]:
        """Every mint :meth:`prune` may not evict — ordinary and EXP-M26-only."""
        return self._pins.all

    @property
    def pinned_exp_m26(self) -> frozenset[str]:
        return frozenset(self._pins.exp_m26)

    @property
    def last_mature_report(self) -> MatureReport:
        """The mature budget's breakdown from the *last* :meth:`prune`, before
        its own eviction — what the heartbeat reads, never a fresh recompute."""
        return self._last_mature_report

    def pin(self, mints: Iterable[str]) -> None:
        """Never evicted by :meth:`prune`'s cap or window while pinned (T4.16b)."""
        self._pins.pin(mints)

    def unpin(self, mints: Iterable[str]) -> None:
        self._pins.unpin(mints)

    def set_pinned(self, mints: Iterable[str]) -> None:
        """Replace the *ordinary* pinned set wholesale (``lab.py``'s every tick)."""
        self._pins.set_pinned(mints)

    def pin_exp_m26(self, mints: Iterable[str]) -> None:
        self._pins.pin_exp_m26(mints)

    def unpin_exp_m26(self, mints: Iterable[str]) -> None:
        self._pins.unpin_exp_m26(mints)

    def set_pinned_exp_m26(self, mints: Iterable[str]) -> None:
        self._pins.set_pinned_exp_m26(mints)

    def snapshot(self) -> tuple[TrackedMint, ...]:
        """Every tracked mint, newest first — the order the radar reads in."""
        return tuple(sorted(self._mints.values(), key=lambda m: m.age_anchor, reverse=True))

    def get(self, mint: str) -> TrackedMint | None:
        return self._mints.get(mint)

    def observe(self, candidate: TrackedMint) -> TrackedMint:
        """Add or merge. Known facts win over unknown ones, never the reverse
        (the same rule ``meme_tokens_identity_is_written_once`` enforces in the
        schema). Mutable state (``mayhem_state``, ``complete``, ``migrated``,
        ``mcap_sol`` with its own ``mcap_observed_at``, ``last_polled_at``,
        ``board``) is the opposite: the newest observation wins — and I1
        (EXP-M26) keeps the two market-cap fields stamped **together**, so a
        fresher ``mcap_sol`` never carries a stale ``mcap_observed_at``.
        ``final_read_pending`` is set by whoever reports the finish and
        cleared only by :meth:`mark_polled`."""
        existing = self._mints.get(candidate.mint)
        if existing is None:
            self._mints[candidate.mint] = candidate
            return candidate
        fresher_mcap = candidate.mcap_sol is not None
        merged = dataclasses.replace(
            existing,
            created_at=existing.created_at or candidate.created_at,
            creator=existing.creator or candidate.creator,
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
            final_read_pending=existing.final_read_pending or candidate.final_read_pending,
            quote_unsupported=existing.quote_unsupported or candidate.quote_unsupported,
            mcap_sol=candidate.mcap_sol if fresher_mcap else existing.mcap_sol,
            mcap_observed_at=candidate.mcap_observed_at
            if fresher_mcap
            else existing.mcap_observed_at,
            last_polled_at=candidate.last_polled_at or existing.last_polled_at,
            last_rest_polled_at=candidate.last_rest_polled_at or existing.last_rest_polled_at,
            board=candidate.board or existing.board,
        )
        self._mints[candidate.mint] = merged
        return merged

    def mark_polled(
        self,
        mint: str,
        at: datetime,
        *,
        mcap_sol: Decimal | None = None,
        source: str = REST_SOURCE,
    ) -> None:
        """A successful read from ``source``. On a finished curve it *is* the
        final read, whichever source made it. ``at`` is also stamped as
        ``mcap_observed_at`` when it taught a new ``mcap_sol`` (I1, EXP-M26)."""
        current = self._mints.get(mint)
        if current is None:
            return
        self._mints[mint] = dataclasses.replace(
            current,
            last_polled_at=at,
            last_rest_polled_at=at if source == REST_SOURCE else current.last_rest_polled_at,
            mcap_sol=mcap_sol if mcap_sol is not None else current.mcap_sol,
            mcap_observed_at=at if mcap_sol is not None else current.mcap_observed_at,
            final_read_pending=False,
        )

    def mark_quote_unsupported(self, mint: str) -> None:
        current = self._mints.get(mint)
        if current is not None:
            self._mints[mint] = dataclasses.replace(current, quote_unsupported=True)

    def prune(
        self, now: datetime, *, mature_top_k: int = 0
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        """Drop what left the window, then cap the rest. Returns ``(aged_out,
        capped, pinned_kept)``. The cap narrows only to the *ordinary*-pinned
        mints (``cap − |ordinary pinned|``, never below :data:`MIN_EFFECTIVE_CAP`);
        EXP-M26-only pins never narrow it (T4.16b/I2).

        ``mature_top_k`` (I1, EXP-M26 §1.6; 0 = off): the largest-by-``mcap_sol``
        eligible, unpinned mints this also protects from the cap, likewise
        without narrowing ``effective_cap``.
        """
        all_pinned = self._pins.all
        aged_out = tuple(
            sorted(
                mint
                for mint, tracked in self._mints.items()
                if mint not in all_pinned and not tracked.is_trackable(now, self._window)
            )
        )
        for mint in aged_out:
            del self._mints[mint]

        pinned_kept = tuple(sorted(mint for mint in self._mints if mint in all_pinned))
        ordinary_kept = [mint for mint in pinned_kept if mint in self._pins.ordinary]
        # ``min(cap, …)`` matters exactly when ``cap`` itself is small (every
        # test in this module, and nobody pinned): the floor must never *grow*
        # a deliberately small cap back past the ceiling the caller configured.
        effective_cap = min(self._cap, max(MIN_EFFECTIVE_CAP, self._cap - len(ordinary_kept)))
        capped: tuple[str, ...] = ()
        unpinned = [m for m in self.snapshot() if m.mint not in all_pinned]
        report = mature_report(unpinned, now, mature_top_k)
        self._last_mature_report = report
        mature_kept = frozenset(report.kept)
        young_candidates = [m for m in unpinned if m.mint not in mature_kept]
        if len(young_candidates) > effective_cap:
            evicted = young_candidates[effective_cap:]
            capped = tuple(sorted(m.mint for m in evicted))
            for mint in capped:
                del self._mints[mint]
        return aged_out, capped, pinned_kept

    def tier(self, tracked: TrackedMint, now: datetime, boosted: Mapping[str, int]) -> int:
        """The declared priority of one mint (lower polls first)."""
        if tracked.mint in boosted and boosted[tracked.mint] == TIER_OPEN_BET:
            return TIER_OPEN_BET
        if tracked.finished and tracked.final_read_pending:
            return TIER_FINAL_READ
        if tracked.mint in boosted:
            return boosted[tracked.mint]
        if tracked.board == "graduating":
            return TIER_GRADUATING
        if tracked.board == "new":
            return TIER_NEW
        return TIER_YOUNG if now - tracked.age_anchor <= self._young else TIER_REST

    def needs_rest(
        self,
        tracked: TrackedMint,
        now: datetime,
        boosted: Mapping[str, int],
        mayhem_refresh: timedelta = MAYHEM_REFRESH,
    ) -> bool:
        """With the chain carrying the curve (T4.2f), what the mirror alone still
        teaches about this mint — and therefore what a REST request buys."""
        if boosted.get(tracked.mint) == TIER_OPEN_BET:
            return True
        if tracked.finished and tracked.final_read_pending:
            return True
        if tracked.last_rest_polled_at is None:
            return True
        if tracked.mayhem_state in ACTIVE_MAYHEM_STATES:
            return now - tracked.last_rest_polled_at >= mayhem_refresh
        return False

    def plan(
        self,
        now: datetime,
        budget: int,
        *,
        boosted: Mapping[str, int] | None = None,
        chain_covered: bool = False,
        mayhem_refresh: timedelta = MAYHEM_REFRESH,
    ) -> PollPlan:
        """Pick up to ``budget`` mints: by tier, least recently polled first inside
        each. ``boosted`` names mints whose tier comes from outside the tracker —
        an open paper bet (``TIER_OPEN_BET``) or a board listing the tracker has
        not seen itself. With ``chain_covered`` only the mints :meth:`needs_rest`
        names are candidates, ordered by their last **REST** read; the rest is
        the chain's and is not ``skipped``."""
        boost = boosted or {}
        candidates = [
            m
            for m in self._mints.values()
            if not chain_covered or self.needs_rest(m, now, boost, mayhem_refresh)
        ]
        if budget <= 0:
            return PollPlan(selected=(), skipped=tuple(sorted(m.mint for m in candidates)))

        def stamp(m: TrackedMint) -> datetime | None:
            return m.last_rest_polled_at if chain_covered else m.last_polled_at

        ordered = sorted(
            candidates,
            key=lambda m: (
                self.tier(m, now, boost),
                stamp(m) is not None,
                stamp(m) or datetime.min.replace(tzinfo=m.first_seen_at.tzinfo),
                m.mint,
            ),
        )
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
